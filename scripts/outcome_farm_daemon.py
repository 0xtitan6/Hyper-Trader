#!/usr/bin/env python3
"""Continuously farm Outcome (outcome.xyz / Monarch) LP rewards.

Reward score is `notional x distance_multiplier x SECONDS_RESTING`, so uptime is
a linear multiplier on everything earned — a 2h burst on a 40h window collects
~5% of what continuous quoting collects. Hence a daemon rather than one-shot runs.

What it does each cycle:
  1. Pull the live scored markets from Monarch (`current-incentives`).
  2. Measure competing in-band depth on each leg from the Hyperliquid book.
  3. Allocate capital greedily by MARGINAL reward per dollar. Reward share is
     `ours / (competing + ours)`, so value-per-dollar is ~`pool / depth`, and that
     ratio varies ~3x across markets — spreading evenly is measurably worse than
     concentrating on the best surfaces.
  4. Start a maker per leg for whatever changed; reap makers whose window ended.

Safety:
  - HARD_CAP_USD bounds total deployment. Spot USDC is unified collateral for the
    perp book, so over-deploying here silently drains the copy-trader's margin
    buffer (observed: withdrawable went $130 -> $0 on a $147 farm).
  - ./KILL stops everything, and every child maker checks it independently.
  - Legs are spot-like (no shorting), so a YES+NO pair is what makes us two-sided
    on the scored surface. Always launched as a pair, never one side.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import jev  # noqa: E402

MONARCH = "https://api.monarch.fast/marina/frontend/outcome-markets/current-incentives"
HL = "https://api.hyperliquid.xyz/info"
ROOT = Path(__file__).resolve().parent.parent
KILL = ROOT / "KILL"

log = logging.getLogger("farm")

# Filled by in_band_depth() for the most recent surface, consumed by the Jev
# shadow call so we do not re-fetch books we just read.
LEG_DETAIL: dict[str, dict[str, float]] = {}
SHADOW = Path("state/jev_shadow.jsonl")

# A surface needs genuine two-sided liquidity near mid before it is worth quoting.
# Below this, the book is empty rather than cheap — see the skip logic in main().
MIN_COMPETING_DEPTH_USD = 300.0


def _hl(body: dict, tries: int = 6):
    for k in range(tries):
        try:
            r = requests.post(HL, json=body, timeout=25)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(1.5 * (k + 1))
    return None


def live_markets() -> list[dict]:
    """Scored markets with a reward and a window that has not closed."""
    try:
        r = requests.get(MONARCH, headers={"Origin": "https://monarch.fast"}, timeout=30)
        r.raise_for_status()
        markets = r.json().get("markets", [])
    except (requests.RequestException, ValueError):
        log.exception("monarch fetch failed")
        return []

    now = time.time()
    out = []
    for m in markets:
        try:
            reward = float(m.get("total_reward_amount_usdc") or 0)
        except (TypeError, ValueError):
            continue
        if reward <= 0:
            continue
        end = m.get("incentive_end_time")
        if end:
            end_ts = time.mktime(time.strptime(end[:19], "%Y-%m-%dT%H:%M:%S"))
            if end_ts <= now:
                continue
        out.append(m)
    return out


def in_band_depth(outcome_id: int, band: float) -> tuple[float, float]:
    """(competing in-band notional, mid) summed across both legs of a surface."""
    depth = 0.0
    mids = []
    LEG_DETAIL.clear()
    for side in (0, 1):
        book = _hl({"type": "l2Book", "coin": f"#{10 * outcome_id + side}"})
        time.sleep(0.35)
        lv = (book or {}).get("levels") or []
        if len(lv) < 2 or not lv[0] or not lv[1]:
            continue
        bid, ask = float(lv[0][0]["px"]), float(lv[1][0]["px"])
        mid = (bid + ask) / 2
        mids.append(mid)
        LEG_DETAIL["YES" if side == 0 else "NO"] = {
            "mid": mid,
            "depth": sum(float(x["px"]) * float(x["sz"]) for x in lv[0][:5]),
            "spread_bp": (ask - bid) / mid * 1e4 if mid else 0.0,
        }
        depth += sum(float(x["px"]) * float(x["sz"]) for x in lv[0]
                     if mid - float(x["px"]) <= band)
        depth += sum(float(x["px"]) * float(x["sz"]) for x in lv[1]
                     if float(x["px"]) - mid <= band)
    return depth, (sum(mids) / len(mids) if mids else 0.0)


def allocate(surfaces: list[dict], budget: float, minimum: float) -> dict[int, float]:
    """Greedy marginal allocation. `surfaces` = [{oid, pool, depth}]."""
    alloc = {s["oid"]: 0.0 for s in surfaces}
    spent = 0.0
    step = 10.0
    while spent + step <= budget:
        best, best_gain, best_step = None, 0.0, step
        for s in surfaces:
            x = alloc[s["oid"]]
            this_step = minimum if x == 0 else step
            if spent + this_step > budget:
                continue
            def r(v: float, s=s) -> float:
                return s["pool"] * v / (s["depth"] + v) if v > 0 else 0.0
            gain = (r(x + this_step) - r(x)) / this_step
            if gain > best_gain:
                best, best_gain, best_step = s["oid"], gain, this_step
        if best is None:
            break
        alloc[best] += best_step
        spent += best_step
    return {k: v for k, v in alloc.items() if v > 0}


def running_legs() -> dict[str, int]:
    """coin -> pid for live maker children."""
    out = {}
    try:
        ps = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True, timeout=20)
    except (subprocess.SubprocessError, OSError):
        return out
    for line in ps.stdout.splitlines():
        if "run_outcome_maker.py" not in line or "--coin" not in line:
            continue
        parts = line.split()
        try:
            out[parts[parts.index("--coin") + 1]] = int(parts[0])
        except (ValueError, IndexError):
            continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=180.0,
                    help="hard cap on total deployed USD (protects the perp margin buffer)")
    ap.add_argument("--min-per-surface", type=float, default=50.0,
                    help="programme scores nothing below $50 in-band bid+ask")
    ap.add_argument("--cycle-s", type=float, default=600.0)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    os.chdir(ROOT)

    while True:
        if KILL.exists():
            log.warning("KILL present — reaping makers and idling")
            for coin, pid in running_legs().items():
                os.kill(pid, 15)
                log.info("stopped %s (pid %s)", coin, pid)
            if args.once:
                return 0
            time.sleep(args.cycle_s)
            continue

        markets = live_markets()
        surfaces = []
        for m in markets:
            band = 0.01 * float(m.get("scoring_params", {}).get("settlement_band_multiplier") or 1.0)
            for o in (m.get("outcomes") or []):
                oid = o.get("hyperliquid_outcome_id")
                try:
                    pool = float(o.get("reward_amount_usdc") or 0) * 0.40
                except (TypeError, ValueError):
                    continue
                if oid is None or pool <= 0:
                    continue
                depth, mid = in_band_depth(oid, band)
                if mid <= 0:
                    continue
                # 2026-09-19: near-zero in-band depth is a TRAP, not a bargain.
                # The allocator ranks by pool/depth, so an empty book scores as
                # infinitely attractive — but it is empty because nobody can quote
                # there. Observed live: Q305 Aston Villa legs showed a 12,697bp
                # spread, our best-bid quotes landed 25x OUTSIDE the scored band
                # (distance multiplier 0.00x of 5.00x) and earned exactly nothing
                # on $180 deployed. Require a real two-sided book near mid.
                legs = dict(LEG_DETAIL)
                widest = max((d.get("spread_bp", 1e9) for d in legs.values()), default=1e9)
                band_bp = band / mid * 1e4
                if depth < MIN_COMPETING_DEPTH_USD or widest > band_bp:
                    log.debug("skip oid=%s depth=$%.0f spread=%.0fbp band=%.0fbp",
                              oid, depth, widest, band_bp)
                    continue
                end = m.get("incentive_end_time")
                ends_in_h = None
                if end:
                    ends_in_h = (time.mktime(time.strptime(end[:19], "%Y-%m-%dT%H:%M:%S"))
                                 - time.time()) / 3600
                surfaces.append({"oid": oid, "pool": pool, "depth": depth, "mid": mid,
                                 "market": m["market_id"], "name": o.get("market_name", "?"),
                                 "legs": legs, "ends_in_h": ends_in_h})

        if not surfaces:
            log.info("no scored surfaces with a readable book; idling")
        else:
            alloc = allocate(surfaces, args.budget, args.min_per_surface)
            want = {}
            for s in surfaces:
                usd = alloc.get(s["oid"], 0.0)
                if usd <= 0:
                    continue
                for side in (0, 1):      # both legs — this is what makes us two-sided
                    want[f"#{10 * s['oid'] + side}"] = usd / 2

            live = running_legs()
            for coin, pid in live.items():
                if coin not in want:
                    os.kill(pid, 15)     # SIGTERM so cancel-on-exit runs
                    log.info("reaped %s (pid %s) — window closed or reallocated", coin, pid)
            for coin, usd in want.items():
                if coin in live:
                    continue
                oid = coin.lstrip("#")[:-1]
                subprocess.Popen(
                    [".venv/bin/python", "scripts/run_outcome_maker.py",
                     "--coin", coin, "--minutes", str(int(args.cycle_s / 60 * 3)),
                     "--usd-per-side", f"{usd:.2f}",
                     "--max-inventory-usd", f"{usd + 5:.2f}", "--execute"],
                    stdout=open(f"state/maker_{oid}.log", "a"),
                    stderr=subprocess.STDOUT,
                )
                log.info("started %s at $%.2f/side", coin, usd)
                time.sleep(2)
            # --- Jev SHADOW ---------------------------------------------------
            # Observation only. Allocation above is already final; we record what
            # Jev would have said so it can be scored against which fills actually
            # went one-sided. Enabling the gate before that evidence exists would
            # be exactly the unverified-plausible-signal trap we avoid elsewhere.
            key = jev.api_key()
            if key:
                for s_ in surfaces:
                    if s_["oid"] not in alloc:
                        continue
                    trades = _hl({"type": "recentTrades", "coin": f"#{10 * s_['oid']}"})
                    state_txt = jev.build_state(
                        market_name=s_["market"], outcome_name=s_.get("name", "?"),
                        legs=s_.get("legs", {}), trades=(trades or [])[:20],
                        ends_in_h=s_.get("ends_in_h"),
                    )
                    answers = jev.evaluate(state_txt, key)
                    if answers:
                        jev.log_shadow(SHADOW, s_["market"], s_["oid"], state_txt,
                                       answers, alloc[s_["oid"]])
                        log.info("jev shadow %s oid=%s informed_flow=%.2f",
                                 s_["market"], s_["oid"],
                                 (answers.get("informed_flow") or {}).get("noul") or -1)
                    time.sleep(0.5)

            log.info("cycle done: %d surfaces scored, %d legs targeted, $%.0f allocated",
                     len(surfaces), len(want), sum(alloc.values()))

        if args.once:
            return 0
        time.sleep(args.cycle_s)


if __name__ == "__main__":
    sys.exit(main())
