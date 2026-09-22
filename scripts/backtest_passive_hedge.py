#!/usr/bin/env python3
"""Backtest the passive hedge against crossing.

QUESTION: when a leg fills and we hold it one-sided, is it better to cross the
spread immediately (what we did) or to rest a bid at a price that still clears
a profit (what hedge_decision now does)?

Crossing is certain but costs the spread. Resting is profitable but may never
fill, and an unfilled hedge leaves us naked into the event — the risk the
minder exists to remove. This measures the trade-off on real price paths.

METHOD. For each outcome leg with history, take every hourly bar as a
hypothetical one-sided fill at that bar's close. Compute the passive hedge
price hedge_decision would post on the complementary leg, then walk forward
through the complement's candles and ask whether its LOW ever reached that
price before the horizon. A limit buy at P fills when the market trades at or
below P, so low <= P is the fill test.

    ./scripts/backtest_passive_hedge.py --hours 24
"""
from __future__ import annotations

import argparse
import importlib.util
import statistics as st
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pair_minder", ROOT / "scripts" / "pair_minder.py")
pm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm)

INFO = "https://api.hyperliquid.xyz/info"


def post(body: dict, tries: int = 4):
    for k in range(tries):
        try:
            r = requests.post(INFO, json=body, timeout=25)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(0.8 * (k + 1))
    return None


def candles(coin: str, days: int):
    now = int(time.time() * 1000)
    c = post({"type": "candleSnapshot",
              "req": {"coin": coin, "interval": "1h",
                      "startTime": now - days * 86400 * 1000, "endTime": now}})
    return c if isinstance(c, list) else []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24, help="passive fill horizon")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--max-markets", type=int, default=40)
    args = ap.parse_args()

    meta = post({"type": "outcomeMeta"}) or {}
    oids = [o["outcome"] for o in meta.get("outcomes", [])][: args.max_markets]

    filled = unfilled = crossed_better = 0
    passive_edges, cross_edges, deadline_edges = [], [], []
    n_paths = 0

    for oid in oids:
        a = candles(f"#{oid * 10}", args.days)
        b = candles(f"#{oid * 10 + 1}", args.days)
        time.sleep(0.05)
        if len(a) < args.hours + 2 or len(b) < args.hours + 2:
            continue
        n_paths += 1
        for i in range(0, len(a) - args.hours - 1, 3):     # sample every 3h
            paid = float(a[i]["c"])
            if not (0.05 < paid < 0.95):
                continue
            # complement's book at that moment, approximated by its close
            comp_px = float(b[i]["c"])
            ask = comp_px * 1.01                            # ~1% spread, conservative
            d = pm.hedge_decision(paid=paid, bid=comp_px * 0.99, ask=ask,
                                  hours_to_event=args.hours * 2,   # no clock pressure
                                  position_age_h=0.1, resting_px=None)
            if d["action"] != "REST":
                continue
            target = d["px"]
            window = b[i + 1: i + 1 + args.hours]
            hit = any(float(x["l"]) <= target for x in window)
            if hit:
                filled += 1
                passive_edges.append(1.0 - (paid + target))
                deadline_edges.append(1.0 - (paid + target))
            else:
                unfilled += 1
                # An unfilled passive hedge does NOT sit naked forever —
                # hedge_decision crosses at the deadline. Score it at what
                # crossing then actually costs, which is the honest comparison.
                end_ask = float(window[-1]["c"]) * 1.01
                deadline_edges.append(1.0 - (paid + end_ask))
                if paid + end_ask < paid + ask:
                    crossed_better += 1
            cross_edges.append(1.0 - (paid + ask))          # crossing immediately

    tot = filled + unfilled
    if not tot:
        print("no usable paths")
        return 1
    print(f"paths from {n_paths} markets, {args.hours}h horizon, n={tot} simulated one-sided fills\n")
    print(f"  passive hedge FILLED    : {filled:>5}  ({filled/tot*100:.1f}%)")
    print(f"  passive hedge UNFILLED  : {unfilled:>5}  ({unfilled/tot*100:.1f}%)")
    print()
    if passive_edges:
        print(f"  edge when it filled     : {st.mean(passive_edges)*100:+.2f}% "
              f"(median {st.median(passive_edges)*100:+.2f}%)")
    print(f"  edge crossing immediately: {st.mean(cross_edges)*100:+.2f}% "
          f"(median {st.median(cross_edges)*100:+.2f}%)")
    print()
    ev_cross = st.mean(cross_edges)
    ev_real = st.mean(deadline_edges)
    print(f"  EV cross immediately     : {ev_cross*100:+.2f}%   <- what we did")
    print(f"  EV passive-then-deadline : {ev_real*100:+.2f}%   <- what we now do")
    print(f"  improvement              : {(ev_real-ev_cross)*100:+.2f} pp")
    print()
    print(f"  Every path is accounted for: filled ones take the passive price,")
    print(f"  unfilled ones cross at the deadline. Nothing is scored as zero and")
    print(f"  no leg is left naked — hedge_decision crosses at T-{pm.CROSS_DEADLINE_H:.0f}h.")
    if crossed_better:
        print(f"  waiting IMPROVED the cross price on {crossed_better} of {unfilled} unfilled "
              f"({crossed_better/unfilled*100:.0f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
