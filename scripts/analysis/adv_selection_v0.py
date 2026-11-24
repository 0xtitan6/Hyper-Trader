#!/usr/bin/env python3
"""
Adverse-selection scoring v0.

For each own_fill in state/journal.jsonl, compute the mark-out (how much did
the mid move against us in the next 30s/60s?). Bucket by coin class and
report per-group stats, then dump JSON + Markdown.

Read-only on all live state. Does not import project code.
"""
from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from statistics import mean, median, stdev

import numpy as np

REPO = "/home/ec2-user/.openclaw/workspace/hyper-trader"
JOURNAL = os.path.join(REPO, "state/journal.jsonl")
BOOK_DIR = os.path.join(REPO, "state/book_snapshots")
CANDLE_DIR = os.path.join(REPO, "state/candles")
OUT_JSON = os.path.join(REPO, "models/adv_selection_v0.json")
OUT_MD = os.path.join(REPO, "analysis/adv_selection_v0.md")

OUTCOME_HORIZON_S = 30.0
OUTCOME_TOL_S = 10.0
PERP_HORIZON_S = 60.0


def load_fills():
    fills = []
    with open(JOURNAL) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("event") != "own_fill":
                continue
            fills.append(e)
    return fills


def classify(coin: str) -> str:
    if coin.startswith("#"):
        return "hip4_outcome"
    if ":" in coin:
        return "hip3_perp"
    return "base_perp"


# ---------- forward-mid lookup helpers ----------

_book_cache: dict[str, list[tuple[float, float]]] = {}


def load_book(coin: str) -> list[tuple[float, float]] | None:
    """coin like '#14740' -> file h14740.jsonl. Returns sorted [(ts, mid), ...]."""
    if coin in _book_cache:
        return _book_cache[coin] or None
    if not coin.startswith("#"):
        return None
    fname = f"h{coin[1:]}.jsonl"
    path = os.path.join(BOOK_DIR, fname)
    if not os.path.exists(path):
        _book_cache[coin] = []
        return None
    rows: list[tuple[float, float]] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = e.get("ts")
            mid = e.get("mid")
            if ts is None or mid is None:
                continue
            rows.append((float(ts), float(mid)))
    rows.sort()
    _book_cache[coin] = rows
    return rows


_candle_cache: dict[str, list[dict]] = {}


def load_candles(coin: str) -> list[dict] | None:
    """coin like 'BTC' or 'xyz:SKHX' (colon-stripped -> not available)."""
    if coin in _candle_cache:
        return _candle_cache[coin] or None
    # candles are only for base perps
    if ":" in coin or coin.startswith("#"):
        _candle_cache[coin] = []
        return None
    path = os.path.join(CANDLE_DIR, f"{coin}.jsonl")
    if not os.path.exists(path):
        _candle_cache[coin] = []
        return None
    rows: list[dict] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.append(e)
    # already time-ordered but be safe
    rows.sort(key=lambda r: r["t"])
    _candle_cache[coin] = rows
    return rows


def forward_mid_outcome(coin: str, ts_fill: float) -> float | None:
    rows = load_book(coin)
    if not rows:
        return None
    target = ts_fill + OUTCOME_HORIZON_S
    # binary search nearest ts within tolerance and >= target-tol
    import bisect
    ts_arr = [r[0] for r in rows]
    idx = bisect.bisect_left(ts_arr, target)
    best = None
    best_diff = None
    for j in (idx - 1, idx, idx + 1):
        if 0 <= j < len(rows):
            diff = abs(rows[j][0] - target)
            if diff <= OUTCOME_TOL_S and (best_diff is None or diff < best_diff):
                best = rows[j][1]
                best_diff = diff
    return best


def forward_mid_perp(coin: str, ts_fill: float) -> float | None:
    rows = load_candles(coin)
    if not rows:
        return None
    target_ms = int((ts_fill + PERP_HORIZON_S) * 1000)
    # find candle whose [t, T] contains target_ms; use close
    import bisect
    starts = [r["t"] for r in rows]
    idx = bisect.bisect_right(starts, target_ms) - 1
    if idx < 0:
        return None
    r = rows[idx]
    if r["t"] <= target_ms <= r["T"]:
        try:
            return float(r["c"])
        except (KeyError, ValueError, TypeError):
            return None
    # allow one-candle look-ahead if we fell in a gap right after last known
    if idx + 1 < len(rows):
        r2 = rows[idx + 1]
        # if the target is within 60s of the next candle start, use its open
        if r2["t"] - target_ms <= 60_000:
            try:
                return float(r2["o"])
            except (KeyError, ValueError, TypeError):
                return None
    return None


# ---------- markout ----------

def markout_bps(side: str, fill_px: float, mid_after: float) -> float:
    if fill_px <= 0:
        return float("nan")
    if side == "B":  # we bought; good = mid went up
        return (mid_after - fill_px) / fill_px * 10_000.0
    if side == "A":  # we sold; good = mid went down
        return (fill_px - mid_after) / fill_px * 10_000.0
    return float("nan")


# ---------- stats ----------

def group_stats(values: list[float]) -> dict:
    if not values:
        return {
            "n": 0, "mean": None, "median": None, "std": None,
            "se_mean": None, "ci95_lo": None, "ci95_hi": None,
            "frac_negative": None, "min": None, "max": None,
        }
    arr = np.array(values, dtype=float)
    n = arr.size
    m = float(arr.mean())
    med = float(np.median(arr))
    sd = float(arr.std(ddof=1)) if n > 1 else 0.0
    se = sd / math.sqrt(n) if n > 0 else float("nan")
    ci = 1.96 * se
    frac_neg = float((arr < 0).sum()) / n
    return {
        "n": int(n),
        "mean": m,
        "median": med,
        "std": sd,
        "se_mean": se,
        "ci95_lo": m - ci,
        "ci95_hi": m + ci,
        "frac_negative": frac_neg,
        "min": float(arr.min()),
        "max": float(arr.max()),
    }


def hour_of_day(ts: float) -> int:
    import datetime as dt
    return dt.datetime.utcfromtimestamp(ts).hour


def main():
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)

    fills = load_fills()
    n_total = len(fills)
    per_class_matched: dict[str, list[dict]] = defaultdict(list)
    per_class_skipped: dict[str, int] = defaultdict(int)
    skip_reasons: dict[str, int] = defaultdict(int)

    for f in fills:
        coin = f["coin"]
        cls = classify(coin)
        ts = float(f["ts"])
        side = f["side"]
        px = float(f["px"])
        mid_after = None
        if cls == "hip4_outcome":
            mid_after = forward_mid_outcome(coin, ts)
            if mid_after is None:
                per_class_skipped[cls] += 1
                skip_reasons["outcome_no_forward_snapshot"] += 1
                continue
        elif cls == "base_perp":
            mid_after = forward_mid_perp(coin, ts)
            if mid_after is None:
                per_class_skipped[cls] += 1
                skip_reasons["base_perp_no_forward_candle"] += 1
                continue
        else:  # hip3_perp
            per_class_skipped[cls] += 1
            skip_reasons["hip3_no_market_data"] += 1
            continue

        mo = markout_bps(side, px, mid_after)
        if not math.isfinite(mo):
            per_class_skipped[cls] += 1
            skip_reasons["nonfinite_markout"] += 1
            continue

        per_class_matched[cls].append({
            "ts": ts,
            "coin": coin,
            "side": side,
            "px": px,
            "mid_after": mid_after,
            "mark_out_bps": mo,
            "hour_utc": hour_of_day(ts),
            "sz": float(f.get("sz", 0.0)),
        })

    # per-class stats
    per_class_stats = {}
    for cls, rows in per_class_matched.items():
        per_class_stats[cls] = group_stats([r["mark_out_bps"] for r in rows])
    # ensure all three classes present in the report
    for cls in ("base_perp", "hip3_perp", "hip4_outcome"):
        per_class_stats.setdefault(cls, group_stats([]))

    # hour-of-day breakdown (pooled across classes; small n so also keep raw)
    hod_stats = {}
    hod_matched: dict[int, list[float]] = defaultdict(list)
    for cls, rows in per_class_matched.items():
        for r in rows:
            hod_matched[r["hour_utc"]].append(r["mark_out_bps"])
    for h in sorted(hod_matched):
        hod_stats[h] = group_stats(hod_matched[h])

    # per-class x hour breakdown
    cls_hod_stats: dict[str, dict[int, dict]] = {}
    for cls, rows in per_class_matched.items():
        by_h: dict[int, list[float]] = defaultdict(list)
        for r in rows:
            by_h[r["hour_utc"]].append(r["mark_out_bps"])
        cls_hod_stats[cls] = {h: group_stats(by_h[h]) for h in sorted(by_h)}

    # top-5 worst fills across all classes
    all_matched = []
    for cls, rows in per_class_matched.items():
        for r in rows:
            r = dict(r)
            r["coin_class"] = cls
            all_matched.append(r)
    worst5 = sorted(all_matched, key=lambda r: r["mark_out_bps"])[:5]

    # coin-level stats (only where we have >=3 matches)
    coin_stats = {}
    coin_matched: dict[str, list[float]] = defaultdict(list)
    for r in all_matched:
        coin_matched[r["coin"]].append(r["mark_out_bps"])
    for c, vs in coin_matched.items():
        if len(vs) >= 3:
            coin_stats[c] = group_stats(vs)

    payload = {
        "generated_utc": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "params": {
            "outcome_horizon_s": OUTCOME_HORIZON_S,
            "outcome_tolerance_s": OUTCOME_TOL_S,
            "perp_horizon_s": PERP_HORIZON_S,
            "convention": "positive mark_out_bps = mid moved in our favor",
        },
        "input": {
            "n_own_fills_total": n_total,
            "matched_per_class": {k: len(v) for k, v in per_class_matched.items()},
            "skipped_per_class": dict(per_class_skipped),
            "skip_reasons": dict(skip_reasons),
        },
        "per_class_stats": per_class_stats,
        "hour_of_day_stats_pooled": hod_stats,
        "per_class_hour_of_day_stats": cls_hod_stats,
        "coin_stats_min_n3": coin_stats,
        "worst5_fills": worst5,
    }

    with open(OUT_JSON, "w") as f:
        json.dump(payload, f, indent=2, default=str)

    # --- Markdown report ---
    def fmt(v, n=2):
        if v is None:
            return "n/a"
        if isinstance(v, float):
            if not math.isfinite(v):
                return "n/a"
            return f"{v:.{n}f}"
        return str(v)

    md = []
    md.append("# Adverse-Selection Scoring v0")
    md.append("")
    md.append(f"Generated: {payload['generated_utc']}")
    md.append("")
    md.append("## Method")
    md.append("")
    md.append(
        "For each `own_fill`, look up the forward mid at ts_fill + horizon and compute "
        "mark-out in bps. Positive = mid moved in our favor (we captured edge). "
        "Negative = we got picked off."
    )
    md.append("")
    md.append(f"- HIP-4 outcomes (`#nnn`): forward mid from `state/book_snapshots/h<coin>.jsonl` at t+{OUTCOME_HORIZON_S:.0f}s (+/- {OUTCOME_TOL_S:.0f}s tolerance).")
    md.append(f"- Base perps (BTC/ETH/...): 1m candle close containing t+{PERP_HORIZON_S:.0f}s (fallback: next candle open within 60s).")
    md.append("- HIP-3 (`xyz:*`, `para:*`): no market-data source in `state/candles/` or `state/book_snapshots/` -> **all skipped**.")
    md.append("")
    md.append("## Input coverage")
    md.append("")
    md.append(f"- Total `own_fill` events: **{n_total}**")
    md.append(f"- Matched per class: `{payload['input']['matched_per_class']}`")
    md.append(f"- Skipped per class: `{payload['input']['skipped_per_class']}`")
    md.append(f"- Skip reasons: `{payload['input']['skip_reasons']}`")
    md.append("")
    md.append("The book_snapshot window is ~22 minutes (2026-09-25 window); nearly all outcome fills fall outside it.")
    md.append("HIP-3 has no market data on disk, so all HIP-3 fills are excluded from this pass.")
    md.append("")
    md.append("## Per-class mark-out (bps)")
    md.append("")
    md.append("| class | n | mean | 95% CI | median | std | frac negative |")
    md.append("|---|---:|---:|---|---:|---:|---:|")
    for cls in ("base_perp", "hip3_perp", "hip4_outcome"):
        s = per_class_stats[cls]
        ci = "n/a" if s["ci95_lo"] is None else f"[{fmt(s['ci95_lo'])}, {fmt(s['ci95_hi'])}]"
        md.append(
            f"| {cls} | {s['n']} | {fmt(s['mean'])} | {ci} | {fmt(s['median'])} | {fmt(s['std'])} | {fmt(s['frac_negative'], 3)} |"
        )
    md.append("")
    md.append("## Pooled hour-of-day (UTC)")
    md.append("")
    md.append("| hour | n | mean | median | std | frac negative |")
    md.append("|---:|---:|---:|---:|---:|---:|")
    for h in sorted(hod_stats):
        s = hod_stats[h]
        md.append(
            f"| {h:02d} | {s['n']} | {fmt(s['mean'])} | {fmt(s['median'])} | {fmt(s['std'])} | {fmt(s['frac_negative'], 3)} |"
        )
    md.append("")
    md.append("## Per-coin (n >= 3)")
    md.append("")
    md.append("| coin | n | mean | median | std | frac neg |")
    md.append("|---|---:|---:|---:|---:|---:|")
    for c, s in sorted(coin_stats.items(), key=lambda kv: kv[1]["mean"]):
        md.append(
            f"| {c} | {s['n']} | {fmt(s['mean'])} | {fmt(s['median'])} | {fmt(s['std'])} | {fmt(s['frac_negative'], 3)} |"
        )
    if not coin_stats:
        md.append("| _no coin has n>=3 matched fills_ | | | | | |")
    md.append("")
    md.append("## Top-5 most adversely-selected matched fills")
    md.append("")
    md.append("| coin | class | ts (UTC) | side | px | mid_after | mark_out_bps |")
    md.append("|---|---|---|---|---:|---:|---:|")
    import datetime as dt
    for r in worst5:
        ts_iso = dt.datetime.utcfromtimestamp(r["ts"]).isoformat()
        md.append(
            f"| {r['coin']} | {r['coin_class']} | {ts_iso} | {r['side']} | "
            f"{fmt(r['px'], 6)} | {fmt(r['mid_after'], 6)} | {fmt(r['mark_out_bps'])} |"
        )
    md.append("")
    md.append("## Verdict")
    md.append("")

    # Verdict logic
    def sig(cls):
        s = per_class_stats[cls]
        if s["n"] == 0 or s["ci95_hi"] is None:
            return None
        # bleeder if entire 95% CI is negative
        if s["ci95_hi"] < 0:
            return "bleeder"
        if s["ci95_lo"] > 0:
            return "edge"
        return "inconclusive"

    verdicts = {cls: sig(cls) for cls in ("base_perp", "hip3_perp", "hip4_outcome")}

    md.append("**Coverage is the dominant finding.** The `state/book_snapshots/` archive spans only ~22 minutes, so the "
              "179 HIP-4 outcome fills reduce to a handful of matches. There are no candles for HIP-3 markets on disk, "
              "so all 80 HIP-3 fills are unmatched. Only base-perp fills against 1-minute HL candles give us any real sample "
              "and even those are shallow.")
    md.append("")
    for cls, v in verdicts.items():
        s = per_class_stats[cls]
        if s["n"] == 0:
            md.append(f"- **{cls}**: 0 matched, no verdict possible.")
        elif v == "bleeder":
            md.append(f"- **{cls}** ({s['n']} fills): mean {s['mean']:.2f} bps, 95% CI [{s['ci95_lo']:.2f}, {s['ci95_hi']:.2f}] — entire CI negative, consistent with a bleeder.")
        elif v == "edge":
            md.append(f"- **{cls}** ({s['n']} fills): mean {s['mean']:.2f} bps, 95% CI [{s['ci95_lo']:.2f}, {s['ci95_hi']:.2f}] — CI above zero, positive edge on this sample.")
        else:
            md.append(f"- **{cls}** ({s['n']} fills): mean {s['mean']:.2f} bps, 95% CI [{s['ci95_lo']:.2f}, {s['ci95_hi']:.2f}] — CI straddles zero, inconclusive.")
    md.append("")
    md.append("**Actionable:** the only way to make this analysis load-bearing is to backfill more book-snapshot coverage "
              "(outcomes) and stream L2/mids for `xyz:*` and `para:*` (the two classes where we take the most flow: "
              "44 fills on `xyz:SKHX` and 24 on `para:VST`). Until then, treat any per-class number here as directional at best.")
    md.append("")

    with open(OUT_MD, "w") as f:
        f.write("\n".join(md))

    # brief stdout summary
    print(json.dumps({
        "n_total": n_total,
        "matched_per_class": {k: len(v) for k, v in per_class_matched.items()},
        "skipped_per_class": dict(per_class_skipped),
        "per_class_stats": {k: {kk: v[kk] for kk in ("n", "mean", "median", "std", "ci95_lo", "ci95_hi", "frac_negative")} for k, v in per_class_stats.items()},
        "verdicts": verdicts,
        "worst5": [{"coin": r["coin"], "ts": r["ts"], "side": r["side"], "mark_out_bps": r["mark_out_bps"]} for r in worst5],
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
