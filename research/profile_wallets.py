"""Deeper profile on shortlisted outcome leaders.

For each wallet, analyzes:
  - Fill cadence (MM-style high-freq vs sparse directional)
  - Position-holding pattern (buy-and-hold-to-expiry vs scalp)
  - Per-outcome lifecycle (open size, holding time, settlement)
  - Distribution of single-trade notionals (consistent sizing vs noise)
"""

from __future__ import annotations

import statistics
import sys
import time
from collections import defaultdict

import requests

HL_URL = "https://api.hyperliquid.xyz/info"
LOOKBACK_DAYS = 30

WALLETS = [
    ("0xbdfa4f4492dd7b7cf211209c4791af8d52bf5c50", "borderline top: $84k / 75% / 6fpc / 21h"),
    ("0x224d6f8b2d6510ca76ef9a747733077b25b3f59f", "borderline: $32k / 100% / 5.5fpc / 44h"),
    ("0x166866a2845506f6b4c817482fe53b4985882ea6", "borderline: $28k / 71% / 6fpc / 20h"),
    ("0xf212ba250bd0939d60532141da56329f8524ba67", "borderline: $10k / 100% / 8fpc / 9h / $2.9k med"),
    ("0x569870903c3ef9768427135f907cb80376d1a3e0", "strict pass: $38k / 100% / 4fpc / 124h / huge med"),
]


def fetch_fills(addr: str, since_ms: int) -> list[dict]:
    payload = {"type": "userFillsByTime", "user": addr.lower(), "startTime": since_ms}
    r = requests.post(HL_URL, json=payload, timeout=30)
    r.raise_for_status()
    return r.json() or []


def is_outcome(coin: str) -> bool:
    return coin.startswith("#") or coin.startswith("+")


def profile(addr: str, label: str, since_ms: int) -> None:
    print(f"\n========= {addr} =========")
    print(f"  {label}")
    fills = fetch_fills(addr, since_ms)
    oc = [f for f in fills if is_outcome(f.get("coin", ""))]
    if not oc:
        print("  no outcome fills in window")
        return

    # group by outcome coin
    by_coin: dict[str, list[dict]] = defaultdict(list)
    for f in oc:
        by_coin[f.get("coin", "")].append(f)
    for coin in by_coin:
        by_coin[coin].sort(key=lambda f: f.get("time", 0))

    # cadence: median inter-fill seconds across ALL outcome fills
    times = sorted(f.get("time", 0) for f in oc)
    deltas = [(times[i + 1] - times[i]) / 1000.0 for i in range(len(times) - 1)]
    med_delta = statistics.median(deltas) if deltas else 0
    p95_delta = statistics.quantiles(deltas, n=20)[18] if len(deltas) >= 20 else max(deltas, default=0)

    notionals = [abs(float(f.get("sz", 0))) * abs(float(f.get("px", 0))) for f in oc]
    med_ntl = statistics.median(notionals) if notionals else 0
    max_ntl = max(notionals) if notionals else 0

    # per-coin lifecycle: opening fill -> last fill or settlement
    holding_times_s: list[float] = []
    open_sizes: list[float] = []
    closed_pnls: list[float] = []
    avg_fill_count_per_coin = []
    fills_at_zero_px = 0  # settlement-style fills

    for coin, flist in by_coin.items():
        avg_fill_count_per_coin.append(len(flist))
        first = flist[0]
        last = flist[-1]
        ht = (last.get("time", 0) - first.get("time", 0)) / 1000.0
        if ht > 0:
            holding_times_s.append(ht)
        open_sizes.append(abs(float(first.get("sz", 0))) * abs(float(first.get("px", 0))))
        for f in flist:
            cp = float(f.get("closedPnl", 0) or 0)
            if cp != 0:
                closed_pnls.append(cp)
            if float(f.get("px", 1)) == 0:
                fills_at_zero_px += 1

    med_hold_h = (statistics.median(holding_times_s) / 3600.0) if holding_times_s else 0
    med_open = statistics.median(open_sizes) if open_sizes else 0
    med_fills_per_coin = statistics.median(avg_fill_count_per_coin) if avg_fill_count_per_coin else 0

    print(f"  outcome fills (30d): {len(oc)}  distinct coins: {len(by_coin)}")
    print(f"  cadence:   median inter-fill = {med_delta:>8.1f}s   p95 = {p95_delta:>8.1f}s")
    print(f"  notional:  median $ {med_ntl:>10,.0f}   max $ {max_ntl:>12,.0f}")
    print(f"  per-coin:  median fills/coin = {med_fills_per_coin:.1f}   median holding = {med_hold_h:.1f}h   median open notional $ {med_open:,.0f}")
    print(f"  settled:   {len(closed_pnls)} fills with closedPnl != 0  ({fills_at_zero_px} at px=0 → likely settlement dust)")
    if closed_pnls:
        wins = [p for p in closed_pnls if p > 0]
        losses = [p for p in closed_pnls if p < 0]
        print(f"             wins {len(wins)} (median ${statistics.median(wins):.0f})  losses {len(losses)} (median ${statistics.median(losses) if losses else 0:.0f})")

    # MM tell: very high fills/coin + very short inter-fill cadence
    mm_score = 0
    if med_delta < 60:
        mm_score += 1
    if med_fills_per_coin > 5:
        mm_score += 1
    if med_hold_h < 1:
        mm_score += 1
    verdict = ["directional", "mixed", "leaning MM", "almost certainly MM"][min(mm_score, 3)]
    print(f"  PROFILE: {verdict}  (mm_score {mm_score}/3)")


def main() -> int:
    since_ms = int((time.time() - LOOKBACK_DAYS * 86400) * 1000)
    for addr, label in WALLETS:
        try:
            profile(addr, label, since_ms)
        except Exception as e:
            print(f"\n{addr}: ERROR {e}", file=sys.stderr)
        time.sleep(0.3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
