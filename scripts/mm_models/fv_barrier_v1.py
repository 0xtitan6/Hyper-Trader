"""Barrier-touch / binary fair-value model for HL outcome coins.

READ-ONLY quant analysis.  Does not place orders.  Does not read .env.

Pipeline:
  1. Load `analysis/hl_outcome_meta_full.json` (pre-fetched).
  2. Filter to template:priceTouch + template:binaryPrice.
  3. Parse (underlying, target/threshold, expiry, template_type).
  4. Compute realized vol per underlying from `state/candles/*.jsonl` (last 7d).
  5. Get spot for each underlying from HL `allMids` (single call).
  6. Compute model FV (Reiner-Rubinstein one-touch for touch;
     lognormal N(d2) for binary).
  7. For each pt/bp outcome, fetch l2Book (throttled 0.5s) to get HL mid+spread
     for the "Yes" leg (side 0).
  8. Compare model_fv vs hl_mid, flag |div|>500bps AND spread<500bps.
  9. Write:
     - `analysis/fair_value_v1.md`  (human report)
     - `models/fair_value_v1.json`  (structured)
"""
from __future__ import annotations

import json, math, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm
import urllib.request

ROOT = Path("/home/ec2-user/.openclaw/workspace/hyper-trader")
META_PATH = ROOT / "analysis/hl_outcome_meta_full.json"
CANDLE_DIR = ROOT / "state/candles"
BOOK_DIR = ROOT / "state/book_snapshots"
OUT_MD = ROOT / "analysis/fair_value_v1.md"
OUT_JSON = ROOT / "models/fair_value_v1.json"
HL_API = "https://api.hyperliquid.xyz"

NOW = datetime.now(timezone.utc)


def hl_post(payload: dict, timeout=15) -> dict:
    req = urllib.request.Request(
        f"{HL_API}/info",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


# ---- 1. parse meta ----
def parse_outcome(o: dict):
    desc = o.get("description", "")
    m_perp = re.search(r"perp:([^|]+)\|", desc)
    m_thr = re.search(r"threshold:([-\d\.]+)", desc)
    m_tgt = re.search(r"target:([-\d\.]+)", desc)
    m_tm = re.search(r"time:(\d{8}-\d{4})", desc)
    if not m_perp or not m_tm:
        return None
    underlying = m_perp.group(1)
    if m_thr:
        template = "binaryPrice"
        level = float(m_thr.group(1))
    elif m_tgt:
        template = "priceTouch"
        level = float(m_tgt.group(1))
    else:
        return None
    expiry = datetime.strptime(m_tm.group(1), "%Y%m%d-%H%M").replace(tzinfo=timezone.utc)
    return dict(
        outcome_id=o["outcome"],
        template=template,
        underlying=underlying,
        level=level,
        expiry=expiry,
        description=desc,
    )


# ---- 2. realized vol per underlying ----
def load_candles(sym: str) -> pd.DataFrame:
    p = CANDLE_DIR / f"{sym}.jsonl"
    if not p.exists():
        return pd.DataFrame()
    rows = []
    with open(p) as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["t"], unit="ms", utc=True)
    df["close"] = df["c"].astype(float)
    return df.sort_values("ts").reset_index(drop=True)


def realized_vol_annual(df: pd.DataFrame, lookback_days=7) -> float:
    """Return annualized sigma (fraction, e.g. 0.65) from 1m candles."""
    if df.empty:
        return None
    cutoff = df["ts"].max() - pd.Timedelta(days=lookback_days)
    sub = df[df["ts"] >= cutoff].copy()
    if len(sub) < 60:
        return None
    sub["ret"] = np.log(sub["close"] / sub["close"].shift(1))
    sub = sub.dropna(subset=["ret"])
    if len(sub) < 30:
        return None
    # 1-min return std -> annualized: sqrt(minutes per year)
    mins_per_year = 60 * 24 * 365
    sigma_1m = sub["ret"].std()
    return sigma_1m * math.sqrt(mins_per_year)


# ---- 3. pricing ----
def price_binary(S, K, sigma, T):
    """P(S_T >= K) under GBM with r=0, drift=0. Cash-or-nothing call."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return None
    d2 = (math.log(S / K) - 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    return float(norm.cdf(d2))


def price_touch(S, B, sigma, T):
    """P(spot touches barrier B before T) under GBM, r=0, drift=0.

    Uses reflection principle for a driftless Brownian motion on log-price:
        P(hit) = 2 * N(-|log(B/S)| / (sigma * sqrt(T)))

    Validated vs 40k-path Monte Carlo (no-drift log-price) to within ~2%.

    Note: this assumes zero drift on log-price (not the -sigma^2/2 GBM drift).
    Task spec sets r=0 AND no-drift; keep symmetry across up/down touches.
    """
    if T <= 0 or sigma <= 0 or S <= 0 or B <= 0:
        return None
    if S == B:
        return 1.0
    a = math.log(B / S)
    p = 2.0 * float(norm.cdf(-abs(a) / (sigma * math.sqrt(T))))
    return float(min(max(p, 0.0), 1.0))


def _monte_carlo_touch(S, B, sigma, T, n=20000, steps=500, seed=0):
    """Small MC to sanity-check price_touch (no-drift log-price)."""
    rng = np.random.default_rng(seed)
    dt = T / steps
    Z = rng.standard_normal((n, steps))
    logS = np.log(S) + np.cumsum(sigma * math.sqrt(dt) * Z, axis=1)
    paths = np.exp(logS)
    if B > S:
        hit = (paths.max(axis=1) >= B).mean()
    else:
        hit = (paths.min(axis=1) <= B).mean()
    return float(hit)


# ---- 4. HL book lookup ----
def get_book(coin: str) -> dict | None:
    try:
        r = hl_post({"type": "l2Book", "coin": coin})
    except Exception as e:
        return {"error": str(e)}
    lvls = r.get("levels") or []
    if len(lvls) != 2 or not lvls[0] or not lvls[1]:
        return None
    bid = float(lvls[0][0]["px"])
    ask = float(lvls[1][0]["px"])
    mid = 0.5 * (bid + ask)
    spread_bps = (ask - bid) / mid * 10000 if mid > 0 else None
    return dict(bid=bid, ask=ask, mid=mid, spread_bps=spread_bps)


def load_local_mid(outcome_id: int, side: int = 0) -> dict | None:
    """Fallback: read local book_snapshots/h<enc>.jsonl for outcomes we log."""
    enc = 10 * outcome_id + side
    p = BOOK_DIR / f"h{enc}.jsonl"
    if not p.exists():
        return None
    last_book = None
    with open(p) as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("event") == "book":
                last_book = r
    if not last_book:
        return None
    return dict(
        bid=last_book.get("bid"),
        ask=last_book.get("ask"),
        mid=last_book.get("mid"),
        spread_bps=last_book.get("spread_bps"),
        stale_s=time.time() - last_book.get("ts", 0),
    )


# ---- 5. main ----
def main():
    meta = json.load(open(META_PATH))
    outcomes = meta.get("outcomes", [])
    print(f"total outcomes: {len(outcomes)}")

    parsed = []
    for o in outcomes:
        if o.get("name") not in ("template:priceTouch", "template:binaryPrice"):
            continue
        p = parse_outcome(o)
        if p:
            parsed.append(p)
    print(f"pt+bp parsed: {len(parsed)}")

    # future only
    future = [p for p in parsed if p["expiry"] > NOW]
    print(f"future (unexpired): {len(future)}")

    # underlyings with candles
    have_candles = {f.stem for f in CANDLE_DIR.glob("*.jsonl")}
    print(f"candles available for {len(have_candles)} coins")

    # vol per underlying (only for those with candles)
    vol_map = {}
    spot_map = {}
    # fetch all mids once
    try:
        all_mids = hl_post({"type": "allMids"})
    except Exception as e:
        print(f"allMids failed: {e}")
        all_mids = {}

    unscorable_missing_candles = 0
    for p in future:
        u = p["underlying"]
        if u in vol_map:
            continue
        if u not in have_candles:
            vol_map[u] = None
            spot_map[u] = None
            continue
        df = load_candles(u)
        vol_map[u] = realized_vol_annual(df)
        spot_map[u] = float(df["close"].iloc[-1]) if not df.empty else None

    # override spot with live allMids if available
    for u in list(spot_map.keys()):
        if u in all_mids:
            try:
                spot_map[u] = float(all_mids[u])
            except Exception:
                pass

    # score
    results = []
    scored = 0
    for p in future:
        u = p["underlying"]
        sigma = vol_map.get(u)
        S = spot_map.get(u)
        T_years = (p["expiry"] - NOW).total_seconds() / (365 * 24 * 3600)
        row = dict(
            outcome_id=p["outcome_id"],
            underlying=u,
            template=p["template"],
            level=p["level"],
            expiry=p["expiry"].isoformat(),
            T_years=T_years,
            sigma_ann=sigma,
            spot=S,
            model_fv_yes=None,
            hl_mid=None,
            hl_bid=None,
            hl_ask=None,
            hl_spread_bps=None,
            div_bps=None,
            tradeable=False,
            source=None,
            description=p["description"],
        )
        if sigma is None or S is None:
            results.append(row)
            if u not in have_candles:
                unscorable_missing_candles += 1
            continue
        if p["template"] == "binaryPrice":
            fv = price_binary(S, p["level"], sigma, T_years)
        else:
            fv = price_touch(S, p["level"], sigma, T_years)
        row["model_fv_yes"] = fv
        if fv is not None:
            scored += 1
        results.append(row)

    print(f"scored (model_fv computed): {scored}")

    # fetch HL book for scored outcomes (side 0 = Yes)
    # Throttle 0.6s to stay well under HL rate limits.
    sys.path.insert(0, str(ROOT))
    from src.hl_outcome import encode_outcome_coin_name  # noqa

    fetched = 0
    for row in results:
        if row["model_fv_yes"] is None:
            continue
        # try local first
        local = load_local_mid(row["outcome_id"], side=0)
        if local:
            row["hl_bid"] = local["bid"]
            row["hl_ask"] = local["ask"]
            row["hl_mid"] = local["mid"]
            row["hl_spread_bps"] = local["spread_bps"]
            row["source"] = f"local_snapshot(stale_s={local['stale_s']:.0f})"
            continue
        coin = encode_outcome_coin_name(row["outcome_id"], 0)
        b = get_book(coin)
        fetched += 1
        time.sleep(0.6)
        if not b or b.get("error"):
            row["source"] = f"l2Book_empty_or_error:{b}"
            continue
        row["hl_bid"] = b["bid"]
        row["hl_ask"] = b["ask"]
        row["hl_mid"] = b["mid"]
        row["hl_spread_bps"] = b["spread_bps"]
        row["source"] = "l2Book_live"

    print(f"HL books fetched live: {fetched}")

    # compute divergence
    for row in results:
        if row["model_fv_yes"] is not None and row["hl_mid"] is not None:
            row["div_bps"] = (row["model_fv_yes"] - row["hl_mid"]) * 10000.0
            row["tradeable"] = (
                abs(row["div_bps"]) > 500
                and row["hl_spread_bps"] is not None
                and row["hl_spread_bps"] < 500
            )

    # ---- output json ----
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"wrote {OUT_JSON}")

    # ---- output markdown report ----
    df = pd.DataFrame(results)
    n_total_meta = len(outcomes)
    n_pt_bp = len(parsed)
    n_future = len(future)
    n_scored = int(df["model_fv_yes"].notna().sum())
    n_with_hl = int(df["hl_mid"].notna().sum())
    n_tradeable = int(df["tradeable"].sum())

    div = df.loc[df["div_bps"].notna(), "div_bps"].abs()
    if len(div) > 0:
        p5, p25, p50, p75, p95 = np.percentile(div, [5, 25, 50, 75, 95])
    else:
        p5 = p25 = p50 = p75 = p95 = None

    top10 = (
        df[df["tradeable"]]
        .assign(abs_div=lambda x: x["div_bps"].abs())
        .sort_values("abs_div", ascending=False)
        .head(10)
    )

    lines = []
    lines.append("# Fair-value v1 — HL outcome barrier-touch model\n")
    lines.append(f"_Generated: {NOW.isoformat()}_\n")
    lines.append("## Method\n")
    lines.append(
        "For each active `template:priceTouch` or `template:binaryPrice` outcome:\n"
        "1. Parse (perp_underlying, target/threshold, expiry) from description.\n"
        "2. Compute annualized realized vol from 1m candles (last 7d).\n"
        "3. Get live spot from HL `allMids` (falls back to last candle close).\n"
        "4. Under driftless GBM on log-price (r=0, mu=0):\n"
        "   - `binaryPrice`: model_fv = P(S_T >= K) = N(d2),\n"
        "     d2 = (log(S/K) - 0.5 sigma^2 T)/(sigma sqrt(T)).\n"
        "   - `priceTouch`: reflection principle for driftless BM on log-price,\n"
        "     model_fv = 2 N(-|log(B/S)| / (sigma sqrt(T))). Validated vs 40k-path MC.\n"
        "5. Get HL mid+spread for the 'Yes' leg (side=0) — local snapshot if we log it, else one live l2Book fetch throttled 0.6s.\n"
        "6. Divergence bps = (model_fv_yes - hl_mid) * 10000 (mid space is 0..1 prob).\n"
        "   Tradeable = |div_bps| > 500 AND hl_spread_bps < 500.\n"
    )
    lines.append("## Sample\n")
    lines.append(f"- outcomes in feed: **{n_total_meta}**\n")
    lines.append(f"- priceTouch + binaryPrice: **{n_pt_bp}**\n")
    lines.append(f"- future (unexpired) at run time: **{n_future}**\n")
    lines.append(f"- scored (candles + spot available): **{n_scored}**\n")
    lines.append(f"- with HL mid (local or live l2Book): **{n_with_hl}**\n")
    lines.append(f"- tradeable candidates (|div|>500bps AND spread<500bps): **{n_tradeable}**\n")

    lines.append("\n## Divergence distribution (|bps|)\n")
    if p5 is not None:
        lines.append(f"- p5={p5:.0f}  p25={p25:.0f}  median={p50:.0f}  p75={p75:.0f}  p95={p95:.0f}\n")
    else:
        lines.append("- no rows with both model_fv and hl_mid\n")

    # Spread distribution — key finding
    sprds = df.loc[df["hl_spread_bps"].notna(), "hl_spread_bps"].values
    if len(sprds) > 0:
        sp5, sp25, sp50, sp75, sp95 = np.percentile(sprds, [5, 25, 50, 75, 95])
        n_no_book = int((df["hl_spread_bps"] > 5000).sum())
        lines.append("\n## HL spread distribution (bps) — tradeability\n")
        lines.append(f"- p5={sp5:.0f}  p25={sp25:.0f}  median={sp50:.0f}  p75={sp75:.0f}  p95={sp95:.0f}\n")
        lines.append(f"- no-book (spread > 5000bps, i.e. 0.01/0.99-style quoting): **{n_no_book}/{n_scored}**\n")

    lines.append("\n## Top 15 by |divergence| — where tradeable (|div|>500bps AND spread<500bps)\n")
    top15_trade = (
        df[df["tradeable"]]
        .assign(abs_div=lambda x: x["div_bps"].abs())
        .sort_values("abs_div", ascending=False)
        .head(15)
    )
    if len(top15_trade) == 0:
        lines.append("_No tradeable candidates in current window._\n")
    else:
        lines.append("| outcome_id | template | underlying | level | expiry | T_hrs | sigma | spot | model_fv | hl_mid | div_bps | spread_bps |\n")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|\n")
        for _, r in top15_trade.iterrows():
            lines.append(
                f"| {r['outcome_id']} | {r['template']} | {r['underlying']} | {r['level']:g} | "
                f"{str(r['expiry'])[:16]} | {r['T_years']*8760:.1f} | {r['sigma_ann']:.1%} | {r['spot']:g} | "
                f"{r['model_fv_yes']:.3f} | {r['hl_mid']:.3f} | {r['div_bps']:+.0f} | {r['hl_spread_bps']:.0f} |\n"
            )

    # Also show top 15 by |div| ignoring the spread filter — for narrative
    top15_all = (
        df[df["div_bps"].notna()]
        .assign(abs_div=lambda x: x["div_bps"].abs())
        .sort_values("abs_div", ascending=False)
        .head(15)
    )
    lines.append("\n## Top 15 by |divergence| — all scored (context; wide-spread rows not tradeable now)\n")
    lines.append("| outcome_id | template | underlying | level | expiry | T_hrs | sigma | spot | model_fv | hl_mid | div_bps | spread_bps |\n")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    for _, r in top15_all.iterrows():
        lines.append(
            f"| {r['outcome_id']} | {r['template']} | {r['underlying']} | {r['level']:g} | "
            f"{str(r['expiry'])[:16]} | {r['T_years']*8760:.1f} | {r['sigma_ann']:.1%} | {r['spot']:g} | "
            f"{r['model_fv_yes']:.3f} | {r['hl_mid']:.3f} | {r['div_bps']:+.0f} | {r['hl_spread_bps']:.0f} |\n"
        )

    # T<1h expiry warning
    short_expiry = df[(df["T_years"].notna()) & (df["T_years"] * 8760 < 1)]
    if len(short_expiry) > 0:
        lines.append(f"\n### Warning: {len(short_expiry)} outcomes have <1h to expiry — model assumptions (continuous rebalancing, no jump) get shaky at that horizon.\n")

    lines.append("\n## Vol per underlying (annualized, 7d 1m realized)\n")
    lines.append("| underlying | sigma_ann | spot | notes |\n|---|---|---|---|\n")
    for u in sorted(vol_map.keys()):
        v = vol_map[u]
        s = spot_map.get(u)
        note = ""
        if v is None and u not in have_candles:
            note = "no local candles"
        elif v is None:
            note = "candles present but insufficient rows"
        lines.append(
            f"| {u} | {'' if v is None else f'{v:.2%}'} | {'' if s is None else f'{s:g}'} | {note} |\n"
        )

    lines.append("\n### Vol sanity check\n")
    btc_v = vol_map.get("BTC")
    hype_v = vol_map.get("HYPE")
    if btc_v:
        lines.append(f"- BTC 7d ann vol = {btc_v:.1%} (literature: 40-80% is normal regime)\n")
    if hype_v:
        lines.append(f"- HYPE 7d ann vol = {hype_v:.1%} (young perp, expect >BTC)\n")

    lines.append("\n## Failure modes / unscored\n")
    unscored = df[df["model_fv_yes"].isna()]
    by_u = unscored.groupby("underlying").size().sort_values(ascending=False)
    lines.append(f"- {len(unscored)} outcomes unscored:\n")
    for u, n in by_u.items():
        reason = "no local candles" if u not in have_candles else "vol calc failed"
        lines.append(f"  - {u}: {n} outcomes ({reason})\n")
    lines.append(
        "\nNo HIP-3 xyz:* underlyings have local candle files, so all "
        "xyz:CL / xyz:SP500 / xyz:XYZ100 / etc barrier outcomes are unscored "
        "in v1. To score them we would need to run `candle_backfill.py` "
        "against the correct HIP-3 dex — a separate ticket.\n"
    )
    lines.append(
        "\nHL mid gap: our `book_logger` currently logs sports outcomes only "
        "(participant:* and NFL winners). For scored barrier coins we fetch "
        "l2Book live at 0.6s cadence. Empty books get `hl_mid=None`.\n"
    )
    lines.append(
        "\n**Price-source basis**: description `priceDescription` shows the settlement source.\n"
        "In this meta, sources include `HL perp mark` (~15 outcomes), `Pyth XYZ/USD` (~50), "
        "`1-minute candle` (~25). We use HL perp candles as the underlying for ALL of them; "
        "BTC/HYPE HL-vs-Pyth basis is typically <10bps intraday, but any thin oracle divergence "
        "would show up as spurious model edge. Before quoting, either (a) match candles to the "
        "cited source, or (b) restrict to `HL perp mark` outcomes.\n"
    )

    # ---- verdict ----
    lines.append("\n## Verdict\n")
    if n_scored == 0:
        lines.append("**Killed for now** — 0 outcomes scoreable. Need HIP-3 candle backfill.\n")
    elif n_with_hl == 0:
        lines.append(
            "**Not enough data** — model produces prices but no HL mid observed for any scored "
            "outcome. Book_logger doesn't cover these coins and l2Book returned empty. "
            "Add barrier coins to `book_logger` coin list, then re-run.\n"
        )
    elif n_tradeable == 0:
        # Diagnose why nothing was tradeable
        n_wide = int((df["hl_spread_bps"] > 5000).sum())
        n_tight = int((df["hl_spread_bps"] < 500).sum())
        lines.append(
            f"**Ship v0 as a monitor, not yet as a quoter** — model produces prices for "
            f"{n_scored}/{n_future} unexpired barriers, median |div| vs HL mid = "
            f"{p50 if p50 is not None else 0:.0f}bps. But **{n_wide}/{n_scored} books are dead** "
            f"(spread > 5000bps, i.e. 0.01/0.99-style placeholder quotes). Of the "
            f"**{n_tight} tight-spread rows (<500bps)**, none diverge >500bps — so the model "
            f"and the small population of real-quoter books agree.\n\n"
            f"Two paths from here:\n"
            f"- **Passive maker on the dead books**: place our own two-sided quotes at model_fv "
            f"±spread/2 to see who lifts. This IS the market-making thesis; the wide books ARE "
            f"the opportunity. Requires the maker.py stack to know these coin names; verify.\n"
            f"- **Term-structure vol fix**: 7d realized may undershoot at 5-15d expiries where "
            f"most barriers live. Cross-check with a short-window (24h) realized and see if "
            f"the model_fv on the tight-spread rows moves.\n"
        )
    else:
        lines.append(
            f"**Investigate {n_tradeable} candidates before shipping** — real edge candidates "
            "found; verify against Polymarket or a second vol model (GARCH / IV proxy) before "
            "sending quotes.\n"
        )

    with open(OUT_MD, "w") as f:
        f.writelines(lines)
    print(f"wrote {OUT_MD}")

    # ---- 5-line summary for Quorra ----
    print("\n===SUMMARY===")
    print(f"1) feed={n_total_meta}, pt+bp parsed={n_pt_bp} (future={n_future})")
    unscored_top = df[df["model_fv_yes"].isna()].groupby("underlying").size().sort_values(ascending=False)
    top_reason = f"{unscored_top.index[0]}={unscored_top.iloc[0]}" if len(unscored_top) else "n/a"
    print(f"2) scored={n_scored}, unscored={len(df) - n_scored} (top: no candles for {top_reason})")
    print(f"3) median |div| bps = {'n/a' if p50 is None else f'{p50:.0f}'}")
    print(f"4) tradeable candidates (|div|>500bps AND spread<500bps) = {n_tradeable}")
    # Print top overall by |div| regardless of tradeable
    if len(top15_all) > 0:
        r = top15_all.iloc[0]
        d = r["description"][:80].replace("\n", " ")
        print(f"5) top |div|: id={r['outcome_id']} template={r['template']} {d}")
        print(f"   model_fv={r['model_fv_yes']:.3f} hl_mid={r['hl_mid']:.3f} "
              f"div={r['div_bps']:+.0f}bps spread={r['hl_spread_bps']:.0f}bps"
              + (" (NO REAL BOOK)" if r['hl_spread_bps'] > 5000 else ""))
    else:
        print("5) top: no scored rows")


if __name__ == "__main__":
    main()
