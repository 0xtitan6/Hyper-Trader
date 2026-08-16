#!/usr/bin/env python
"""Dry-run analysis: how does `discovery.min_trades` change the selected set?

BACKLOG P2. Read-only. Places no orders, writes no config, and imports nothing
that trades — run it whenever, including while the bot is live.

WHY THIS IS AN ANALYSIS AND NOT A ONE-LINE CONFIG CHANGE
--------------------------------------------------------
`discovery.min_trades: 50` filters on trade *frequency*, which is precisely the
property that makes a wallet unprofitable to copy at our fee tier (4.5 bps
taker, base dex). The 2026-08 screen of 466 wallets found every high-PnL name
failing on turnover or fee-tier edge, while a genuine low-frequency candidate
at 43 trades/30d was auto-rejected for being one trade a day short of 50.

So lowering the number is not obviously right either: it widens a filter that
was never measuring the thing we care about. This script measures the thing we
care about — `src/copy_econ.net_edge_bps`, the leader's pre-fee edge per dollar
of turnover minus what WE pay to trade it — and reports how the selected set
moves across `min_trades` in {20, 30, 50}, so the change can be argued from
numbers instead of intuition.

It recommends. It does not decide, and it does not write `config.yaml`.

NOTE ON `min_trades` BEING TWO FILTERS
--------------------------------------
`discover_leaders` applies the same config number twice, to two different
quantities, and this trips people up:

  1. coarse pass: `Trader.trades` from Liquidiction's leaderboard, over
     `discovery.period`;
  2. quality pass: `LeaderMetrics.trade_count` — fills read from HL over
     `discovery.score_lookback_hours`, and with `score_perp_only` set it counts
     perp fills only.

They disagree routinely. The report prints both so a threshold is never chosen
against the wrong one.

USAGE
    .venv/bin/python -m scripts.min_trades_analysis
    .venv/bin/python -m scripts.min_trades_analysis --min-trades 20 30 50 --json out.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any

from hyperliquid.info import Info

from src.config import Config, load_config
from src.copy_econ import DEFAULT_TAKER_BPS, CopyEcon, compute_copy_econ, passes_fee_tier
from src.leader_score import LeaderMetrics, _compute_metrics, meets_quality
from src.leaders import _perp_equity_usd, hip3_dex_names
from src.liquidiction import LiquidictionClient, Trader

DEFAULT_MIN_TRADES = (20, 30, 50)


@dataclass
class Candidate:
    """One leaderboard wallet with everything needed to screen it, fetched once."""

    trader: Trader
    metrics: LeaderMetrics | None
    econ: CopyEcon | None
    # None means the probe failed — UNKNOWN, not $0 (INV 4). `_perp_equity_usd`
    # in src/leaders.py takes the same stance and so must we, or a flaky call
    # silently disqualifies a good leader.
    equity_usd: float | None
    unrealized_pnl_usd: float | None
    leverage_notional_usd: float | None
    fetch_error: str = ""


def _fetch_fills(info: Info, address: str, lookback_hours: float) -> list[dict[str, Any]] | None:
    """`userFillsByTime` for one address. None on failure (never [] — INV 4)."""
    since_ms = int((time.time() - lookback_hours * 3600) * 1000)
    try:
        out = info.post(
            "/info",
            {"type": "userFillsByTime", "user": address.lower(), "startTime": since_ms},
        )
    except Exception as e:  # a probe failure must not abort the whole sweep
        print(
            f"  ! fills fetch failed for {address[:12]}: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return None
    return out if isinstance(out, list) else None


def _fetch_account(
    info: Info, address: str, min_equity_usd: float, dex_names: list[str] | None
) -> tuple[float | None, float | None, float | None]:
    """(equity, unrealized_pnl, position_notional) for a leader.

    `equity` comes from `src/leaders._perp_equity_usd`, deliberately imported
    rather than reimplemented: this script exists to predict which wallets the
    live gate selects, so a second copy of the rule is a way to be confidently
    wrong. `test_unreadable_equity_fails_OPEN_and_does_not_disqualify` pins the
    parity. It reads EVERY clearinghouse (P0c, 2026-08-15) — the earlier
    base-only read scored our own pinned incumbent at $0 (INV 1).

    Unrealized and notional are still BASE-dex only, so both understate a
    leader whose book is mostly HIP-3. They are printed, never screened on, and
    the report's caveats say so. Fixing them needs the per-dex position merge,
    which is out of scope here.

    Unrealized and notional are printed because INV 9 forbids judging a leader
    on realized fills alone — a martingale that closes only winners backtests
    perfectly while holding a catastrophic open loss.
    """
    equity = _perp_equity_usd(
        info, address.lower(), min_usd=min_equity_usd, dex_names=dex_names
    )
    try:
        st = info.user_state(address.lower()) or {}
    except Exception:
        return equity, None, None
    summary = st.get("marginSummary") or {}
    try:
        notional = float(summary.get("totalNtlPos", 0) or 0)
    except (TypeError, ValueError):
        return equity, None, None
    unrealized = 0.0
    for ap in st.get("assetPositions", []) or []:
        pos = ap.get("position") if isinstance(ap, dict) else None
        if not isinstance(pos, dict):
            continue
        try:
            unrealized += float(pos.get("unrealizedPnl", 0) or 0)
        except (TypeError, ValueError):
            continue
    return equity, unrealized, notional


def gather(cfg: Config, limit: int, our_taker_bps: float) -> list[Candidate]:
    """Fetch the leaderboard and everything each candidate is screened on."""
    liq = LiquidictionClient(cfg.network.liquidiction_base)
    info = Info(base_url="https://api.hyperliquid.xyz", skip_ws=True)
    traders = liq.top_traders(period=cfg.discovery.period, n=limit)
    print(f"leaderboard: {len(traders)} wallets (period={cfg.discovery.period})", file=sys.stderr)
    # Once for the sweep, like discover_leaders does per cycle — it describes
    # the exchange, not a wallet.
    dex_names = hip3_dex_names(info)
    print(f"HIP-3 clearinghouses: {dex_names}", file=sys.stderr)

    out: list[Candidate] = []
    for i, t in enumerate(traders, 1):
        print(f"  [{i}/{len(traders)}] {t.address[:12]}…", file=sys.stderr)
        fills = _fetch_fills(info, t.address, cfg.discovery.score_lookback_hours)
        if fills is None:
            out.append(Candidate(t, None, None, None, None, None, fetch_error="fills_unavailable"))
            continue
        metrics = _compute_metrics(
            address=t.address,
            lookback_hours=cfg.discovery.score_lookback_hours,
            fills=fills,
            perp_only=cfg.discovery.score_perp_only,
        )
        econ = compute_copy_econ(
            t.address,
            fills,
            lookback_hours=cfg.discovery.score_lookback_hours,
            our_taker_bps=our_taker_bps,
        )
        equity, unreal, notional = _fetch_account(
            info, t.address, cfg.discovery.min_leader_equity_usd, dex_names
        )
        out.append(Candidate(t, metrics, econ, equity, unreal, notional))
    return out


def screen(c: Candidate, cfg: Config, min_trades: int, min_net_edge_bps: float) -> tuple[bool, str]:
    """Apply every screen at a given `min_trades`, in `discover_leaders` order.

    Returns `(selected, reason)`. `reason` is the FIRST screen that rejected —
    one greppable reason per rejection, never a shared opaque "filter"
    (INV 5: 2,449,814 skips in 30d once shared a single reason string).
    """
    t = c.trader
    # 1. Coarse leaderboard pass, exactly as src/leaders.py does it.
    if t.trades < min_trades:
        return False, f"coarse_trades={t.trades} < {min_trades}"
    if t.volume < cfg.discovery.min_volume_usd:
        return False, f"coarse_volume=${t.volume:.0f} < ${cfg.discovery.min_volume_usd:.0f}"
    if t.pnl < cfg.discovery.min_pnl_usd:
        return False, f"coarse_pnl=${t.pnl:.0f} < ${cfg.discovery.min_pnl_usd:.0f}"
    if c.metrics is None:
        return False, "metrics_unavailable"

    # 2. Solvency (INV 9). Fail-OPEN on an unreadable probe: None means we did
    #    not measure their equity, not that they have none.
    if c.equity_usd is not None and c.equity_usd < cfg.discovery.min_leader_equity_usd:
        return False, (f"equity=${c.equity_usd:.0f} < ${cfg.discovery.min_leader_equity_usd:.0f}")

    # 3. Quality, including the turnover screen (`min_holding_time_s` against
    #    the p50 fill gap — a sub-2-minute median gap is a scalper we cannot
    #    mirror) and the perp-fraction screen.
    ok, reason = meets_quality(
        c.metrics,
        min_holding_s=cfg.discovery.min_holding_time_s,
        min_sharpe=cfg.discovery.min_sharpe,
        min_realized_pnl_usd=cfg.discovery.min_pnl_usd,
        min_direction_consistency=cfg.discovery.min_direction_consistency,
        min_trades=min_trades,
        min_perp_fraction=cfg.discovery.min_perp_fraction,
    )
    if not ok:
        return False, reason

    # 4. Fee tier. NOT currently in src/leaders.py — this is the screen the
    #    backlog item argues min_trades was standing in for, and the report
    #    shows what it would change if adopted.
    if c.econ is None:
        return False, "econ_unavailable"
    ok, reason = passes_fee_tier(c.econ, min_net_edge_bps=min_net_edge_bps)
    if not ok:
        return False, reason
    return True, ""


def _fmt_usd(v: float | None) -> str:
    if v is None:
        return "     n/a"
    if abs(v) >= 1_000_000:
        return f"{v / 1_000_000:>7.2f}M"
    if abs(v) >= 1_000:
        return f"{v / 1_000:>7.1f}k"
    return f"{v:>8.0f}"


def report(
    cands: list[Candidate],
    cfg: Config,
    thresholds: tuple[int, ...],
    min_net_edge_bps: float,
    our_taker_bps: float,
) -> dict[str, Any]:
    """Print the analysis and return it as a JSON-serialisable dict."""
    print("=" * 118)
    print("min_trades DRY-RUN ANALYSIS — BACKLOG P2. No config was changed by this run.")
    print("=" * 118)
    print(
        f"period={cfg.discovery.period}  lookback={cfg.discovery.score_lookback_hours:.0f}h  "
        f"top_n={cfg.discovery.top_n}  live min_trades={cfg.discovery.min_trades}  "
        f"our_taker={our_taker_bps:.2f}bps  min_net_edge={min_net_edge_bps:.2f}bps"
    )
    print(
        "net_edge_bps = (realized PnL + their fees) / turnover - our taker fee. "
        "Positive => copying their flow pays at OUR tier."
    )
    print(
        "Screens applied: coarse(trades/volume/pnl) -> solvency(INV 9) -> "
        "quality(turnover p50 gap, perp frac, sharpe, direction) -> fee-tier."
    )
    print()

    hdr = (
        f"{'address':<14}{'lb_trd':>7}{'fills':>7}{'turn/mo':>10}{'p50gap_s':>10}"
        f"{'perp%':>7}{'takr%':>7}{'ldrfee':>8}{'gross':>8}{'net_bps':>9}"
        f"{'net$@ours':>11}{'equity':>10}{'unreal':>10}"
    )
    print(hdr)
    print("-" * len(hdr))
    for c in sorted(
        cands,
        key=lambda x: x.econ.net_edge_bps if x.econ and x.econ.econ_known else -1e9,
        reverse=True,
    ):
        e, m = c.econ, c.metrics
        if e is None or m is None:
            print(f"{c.trader.address[:12]:<14}{'—  ' + (c.fetch_error or 'no data'):>60}")
            continue
        known = e.econ_known
        print(
            f"{c.trader.address[:12]:<14}"
            f"{c.trader.trades:>7}"
            f"{m.trade_count:>7}"
            f"{_fmt_usd(e.turnover_usd_per_mo):>10}"
            f"{m.time_between_fills_p50_s:>10.0f}"
            f"{m.perp_fill_fraction * 100:>7.0f}"
            f"{e.taker_fill_fraction * 100:>7.0f}"
            f"{(f'{e.leader_fee_bps:.2f}' if known else 'n/a'):>8}"
            f"{(f'{e.gross_edge_bps:.2f}' if known else 'n/a'):>8}"
            f"{(f'{e.net_edge_bps:.2f}' if known else 'n/a'):>9}"
            f"{_fmt_usd(e.net_pnl_at_our_tier_usd if known else None):>11}"
            f"{_fmt_usd(c.equity_usd):>10}"
            f"{_fmt_usd(c.unrealized_pnl_usd):>10}"
        )
    print()

    results: dict[str, Any] = {
        "generated_at": time.time(),
        "period": cfg.discovery.period,
        "lookback_hours": cfg.discovery.score_lookback_hours,
        "live_min_trades": cfg.discovery.min_trades,
        "our_taker_bps": our_taker_bps,
        "min_net_edge_bps": min_net_edge_bps,
        "candidates": len(cands),
        "by_min_trades": {},
    }

    for mt in thresholds:
        selected: list[tuple[Candidate, str]] = []
        rejected: list[tuple[Candidate, str]] = []
        for c in cands:
            ok, reason = screen(c, cfg, mt, min_net_edge_bps)
            (selected if ok else rejected).append((c, reason))
        # `discover_leaders` stops at top_n in leaderboard order, so the
        # ordering here must match or the "selected set" is not the live one.
        capped = selected[: cfg.discovery.top_n]

        print(f"--- min_trades = {mt} " + "-" * 60)
        print(
            f"    passes all screens: {len(selected)}   "
            f"taken (top_n={cfg.discovery.top_n}): {len(capped)}"
        )
        for c, _ in capped:
            e = c.econ
            net = f"{e.net_edge_bps:+.2f}bps" if e and e.econ_known else "unknown"
            print(
                f"      + {c.trader.address[:12]}  lb_trades={c.trader.trades:<6} "
                f"net_edge={net:<12} turn/mo={_fmt_usd(e.turnover_usd_per_mo if e else None)}"
            )
        # Only show rejections that this threshold itself caused; the rest are
        # noise that repeats identically at every threshold.
        by_trades = [(c, r) for c, r in rejected if r.startswith(("coarse_trades", "trades="))]
        if by_trades:
            print(f"    rejected BY THE TRADE COUNT ITSELF: {len(by_trades)}")
            for c, r in by_trades[:12]:
                e = c.econ
                net = f"{e.net_edge_bps:+.2f}bps" if e and e.econ_known else "unknown"
                print(f"      - {c.trader.address[:12]}  {r:<34} net_edge={net}")
        print()

        results["by_min_trades"][str(mt)] = {
            "passing": [c.trader.address for c, _ in selected],
            "taken": [c.trader.address for c, _ in capped],
            "rejected_by_trade_count": [
                {
                    "address": c.trader.address,
                    "reason": r,
                    "net_edge_bps": (c.econ.net_edge_bps if c.econ and c.econ.econ_known else None),
                    "turnover_usd_per_mo": (c.econ.turnover_usd_per_mo if c.econ else None),
                }
                for c, r in by_trades
            ],
            "rejections": [{"address": c.trader.address, "reason": r} for c, r in rejected],
        }

    _recommend(cands, results, thresholds, cfg, min_net_edge_bps)
    results["detail"] = [
        {
            "address": c.trader.address,
            "leaderboard_trades": c.trader.trades,
            "leaderboard_pnl": c.trader.pnl,
            "leaderboard_volume": c.trader.volume,
            "equity_usd": c.equity_usd,
            "unrealized_pnl_usd": c.unrealized_pnl_usd,
            "metrics": asdict(c.metrics) if c.metrics else None,
            "econ": asdict(c.econ) if c.econ else None,
            "fetch_error": c.fetch_error,
        }
        for c in cands
    ]
    return results


def _recommend(
    cands: list[Candidate],
    results: dict[str, Any],
    thresholds: tuple[int, ...],
    cfg: Config,
    min_net_edge_bps: float,
) -> None:
    """Print the written recommendation. Numbers only — no config is written."""
    print("=" * 118)
    print("RECOMMENDATION")
    print("=" * 118)

    taken = {mt: results["by_min_trades"][str(mt)]["taken"] for mt in thresholds}
    identical = len({tuple(v) for v in taken.values()}) == 1

    measured = [c for c in cands if c.econ and c.econ.econ_known]
    positive = [c for c in measured if c.econ and c.econ.net_edge_bps >= min_net_edge_bps]

    for mt in thresholds:
        print(
            f"  min_trades={mt:<3} -> {len(taken[mt])} selected: "
            f"{', '.join(a[:12] for a in taken[mt]) or '(none)'}"
        )
    print()
    print(f"  candidates with measurable perp economics: {len(measured)}/{len(cands)}")
    print(
        f"  of those, net edge >= {min_net_edge_bps:.2f}bps at our tier: {len(positive)} "
        f"({', '.join(c.trader.address[:12] for c in positive) or 'none'})"
    )
    print()

    if identical:
        print("  min_trades is NOT the binding constraint on this leaderboard: the selected")
        print("  set is IDENTICAL at every threshold tested. Moving it changes nothing, so")
        print("  changing it cannot be justified from this data — and lowering a filter that")
        print("  is not binding only widens the pool the moment the leaderboard rotates.")
    else:
        print("  min_trades DOES change the selected set here. Compare the net_edge column")
        print("  of the wallets it adds or removes: admit a threshold change only if the")
        print("  wallets it admits have positive net edge at our tier.")
    print()

    # The real point of the exercise (INV 5: the number that actually binds).
    all_rej: list[str] = []
    for mt in thresholds:
        all_rej += [r["reason"] for r in results["by_min_trades"][str(mt)]["rejections"]]
    buckets: dict[str, int] = {}
    for r in all_rej:
        buckets[r.split("=")[0].split(" ")[0]] = buckets.get(r.split("=")[0].split(" ")[0], 0) + 1
    print("  rejection reasons across all thresholds (which screen actually binds):")
    for k, v in sorted(buckets.items(), key=lambda kv: -kv[1]):
        print(f"    {k:<28} {v}")
    print()
    print("  CAVEATS — read before acting on any of the above:")
    print("   - Every PnL figure is REALIZED (INV 10). The `unreal` column is the open")
    print("     opinion; a leader can show a clean net_edge while sitting on a large open")
    print("     loss (INV 9 — realized-fill stats alone have produced five false positives).")
    print("   - `equity` reads EVERY clearinghouse and is the best SINGLE dex, never a")
    print("     sum (INV 2 — each dex settles against its own collateral).")
    print("   - `unreal` is still BASE-dex only (INV 1), so it understates a leader whose")
    print("     book is mostly HIP-3. It is printed, never screened on.")
    print(f"   - One leaderboard snapshot of {len(cands)} wallets, period={cfg.discovery.period}.")
    print("     A single snapshot is not a distribution: re-run across several days before")
    print("     concluding that a threshold is or is not binding.")
    print("   - net_edge assumes we fill at the leader's price. We do not: we cross the")
    print("     spread after them, so realised copy edge is strictly WORSE than this.")
    print("     Treat net_edge as an upper bound, which makes a marginal pass a fail.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--min-trades", type=int, nargs="+", default=list(DEFAULT_MIN_TRADES))
    ap.add_argument("--limit", type=int, default=60, help="leaderboard wallets to screen")
    ap.add_argument("--our-taker-bps", type=float, default=DEFAULT_TAKER_BPS)
    ap.add_argument(
        "--min-net-edge-bps",
        type=float,
        default=0.0,
        help="fee-tier screen floor; 0.0 = must merely break even at our tier",
    )
    ap.add_argument("--json", default="", help="also write the full result set here")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    cands = gather(cfg, args.limit, args.our_taker_bps)
    results = report(cands, cfg, tuple(args.min_trades), args.min_net_edge_bps, args.our_taker_bps)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=1, default=str)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
