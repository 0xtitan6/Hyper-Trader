"""Parallel measurement to research/leader-511e60d3-reachable-flow-2026-11-05.md,
but on 0x9551e7d4. Fetches 30d of fills, classifies each by reachability under
engine config (base + register_hip3_dexes), buckets leader closedPnl, then
replays copysim.simulate() on the reachable-only subset to get copy-PnL.

READ ONLY. No wallet material. 0.35s between pages.
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.copysim import fetch_fills, simulate, market_type  # noqa: E402

LEADER = "0x9551e7d4cd963558bb9882aecc74f549262e217f"
DAYS = 30
CLIP = 30.0
FEE_BPS = 4.5
SLIP_BPS = 5.0
CAP = 800.0  # same mid cap used elsewhere; blocking comes from clip size here


def reachable_set() -> set[str]:
    from hyperliquid.info import Info
    from src.hl_hip3 import register_hip3_dexes
    info = Info("https://api.hyperliquid.xyz", skip_ws=True)
    register_hip3_dexes(info)
    return set(info.coin_to_asset.keys())


def main() -> int:
    reachable = reachable_set()
    print(f"reachable coins: {len(reachable)}")

    now = int(time.time() * 1000)
    start = now - DAYS * 86400_000
    cache_dir = Path("state/copysim_fills")
    cache_dir.mkdir(exist_ok=True)
    cf = cache_dir / f"{LEADER[:10]}_{DAYS}d_1106.json"
    if cf.exists():
        fills = json.load(cf.open())
        src = "cache"
    else:
        fills = fetch_fills(LEADER, start, now)
        cf.write_text(json.dumps(fills))
        src = "api"
    print(f"fills={len(fills)} src={src}")

    # --- classify
    buckets: dict[str, list[dict]] = defaultdict(list)
    for f in fills:
        c = f["coin"]
        if market_type(c) == "outcome":
            bucket = "outcome"
        elif market_type(c) == "spot":
            bucket = "spot"
        elif c in reachable:
            bucket = "reachable_perp"
        else:
            bucket = "unreachable_perp"
        buckets[bucket].append(f)

    print("\n=== LEADER FILL BUCKETS (30d) ===")
    for b in ("reachable_perp", "unreachable_perp", "outcome", "spot"):
        bf = buckets[b]
        notional = sum(float(f["px"]) * float(f["sz"]) for f in bf)
        closed = sum(float(f.get("closedPnl") or 0.0) for f in bf)
        print(f"  {b:>20} n={len(bf):>5}  notional=${notional:>14,.2f}  closedPnL=${closed:>+12,.2f}")

    # --- top reachable coins
    rp = buckets["reachable_perp"]
    by_coin = defaultdict(lambda: {"n": 0, "notional": 0.0, "closed": 0.0})
    for f in rp:
        s = by_coin[f["coin"]]
        s["n"] += 1
        s["notional"] += float(f["px"]) * float(f["sz"])
        s["closed"] += float(f.get("closedPnl") or 0.0)
    print("\n=== TOP REACHABLE COINS ===")
    for coin, s in sorted(by_coin.items(), key=lambda kv: -kv[1]["n"])[:20]:
        print(f"  {coin:>14} n={s['n']:>4}  notional=${s['notional']:>12,.2f}  closedPnL=${s['closed']:>+10,.2f}")

    # --- Settlement-only slice on outcomes (to mirror 11-05 observation that
    # most "loss" is HIP-4 Settlement expiry, not discretionary trading)
    out = buckets["outcome"]
    settle = [f for f in out if str(f.get("dir", "")).lower() == "settlement"]
    disc = [f for f in out if str(f.get("dir", "")).lower() != "settlement"]
    s_closed = sum(float(f.get("closedPnl") or 0.0) for f in settle)
    d_closed = sum(float(f.get("closedPnl") or 0.0) for f in disc)
    print(f"\n  outcome Settlement n={len(settle)}  closedPnL=${s_closed:+,.2f}")
    print(f"  outcome discretionary n={len(disc)}  closedPnL=${d_closed:+,.2f}")

    # --- run copysim.simulate on reachable_perp only
    st, pc, _ = simulate(sorted(rp, key=lambda f: f["time"]),
                         CLIP, CAP, FEE_BPS, SLIP_BPS)
    print("\n=== COPYSIM REACHABLE-PERP ONLY (clip=$30, cap=$800, fee+slip=9.5bps) ===")
    print(f"  net={st['net']:+.2f}  gross={st['gross']:+.2f}  fees={st['fees']:.2f}")
    print(f"  taken={st['taken']}  opens={st['opens']}  blocked_cap={st['blocked_cap']}  blocked_min={st['blocked_min']}")
    print("\n  per-coin (sorted by |net|):")
    for c, v in sorted(pc.items(), key=lambda kv: -abs(kv[1]))[:20]:
        print(f"    {c:>14}  {v:+.2f}")

    # --- 511 comparison reproduce
    st2, _, _ = simulate(
        [f for f in fills if market_type(f["coin"]) == "perp"],
        CLIP, CAP, FEE_BPS, SLIP_BPS,
    )
    print(f"\n  all-perp (no reachability filter): net={st2['net']:+.2f} taken={st2['taken']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
