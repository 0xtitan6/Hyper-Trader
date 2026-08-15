"""Re-run outcome leader research with DIRECTIONAL filtering.

Insight from profile_wallets.py: ranking top HL leaderboard wallets by raw
outcome PnL surfaces market-makers, not directional bettors. We can't
effectively mirror MM activity — by the time we see their fill, the spread
they captured is gone.

This script filters for the directional signature:
  - ≤ 5 fills per outcome (no quote-and-flip)
  - ≥ 6h median holding time on the outcomes they touch
  - ≥ $100 median per-fill notional (real conviction, not micro-rebate)
  - settled PnL ≥ $5k (still need real money)

Output: ranked directional-bettor shortlist.
"""

from __future__ import annotations

import csv
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass

import requests

LB_URL = "https://liquidiction.xyz/api/leaderboard"
HL_URL = "https://api.hyperliquid.xyz/info"
LOOKBACK_DAYS = 30
TOP_N = 120  # widen the pool — directional bettors won't dominate raw PnL ranks
MIN_SETTLED_PNL = 5_000
MAX_FILLS_PER_COIN = 5
MIN_HOLDING_H = 6.0
MIN_MEDIAN_NTL = 100.0


@dataclass
class DirStats:
    address: str
    rank: int
    overall_pnl_30d: float
    outcome_fills: int
    distinct_outcomes: int
    settled_pnl: float
    win_rate: float
    median_fills_per_coin: float
    median_holding_h: float
    median_ntl: float
    max_single_loss: float
    fills_per_day: float
    quality_score: float


def fetch_leaderboard(n: int) -> list[dict]:
    out: list[dict] = []
    offset = 0
    while len(out) < n:
        r = requests.get(LB_URL, params={"period": "month", "offset": offset, "limit": 50}, timeout=15)
        r.raise_for_status()
        data = r.json()
        rows = data.get("traders", []) or []
        if not rows:
            break
        out.extend(rows)
        offset += len(rows)
        if offset >= data.get("totalTraders", 0):
            break
    return out[:n]


def fetch_fills(addr: str, since_ms: int, retries: int = 3) -> list[dict]:
    payload = {"type": "userFillsByTime", "user": addr.lower(), "startTime": since_ms}
    delay = 1.0
    for attempt in range(retries):
        try:
            r = requests.post(HL_URL, json=payload, timeout=30)
            if r.status_code == 429:
                time.sleep(delay)
                delay *= 2
                continue
            r.raise_for_status()
            return r.json() or []
        except requests.RequestException:
            if attempt == retries - 1:
                return []
            time.sleep(delay)
            delay *= 2
    return []


def is_outcome(coin: str) -> bool:
    return coin.startswith("#") or coin.startswith("+")


def compute(addr: str, rank: int, pnl_30d: float, fills: list[dict]) -> DirStats | None:
    oc = [f for f in fills if is_outcome(f.get("coin", ""))]
    if len(oc) < 4:
        return None

    by_coin: dict[str, list[dict]] = defaultdict(list)
    for f in oc:
        by_coin[f.get("coin", "")].append(f)
    for c in by_coin:
        by_coin[c].sort(key=lambda f: f.get("time", 0))

    fills_per_coin = [len(v) for v in by_coin.values()]
    holding_times_h: list[float] = []
    for c, flist in by_coin.items():
        if len(flist) >= 2:
            ht = (flist[-1].get("time", 0) - flist[0].get("time", 0)) / 1000.0 / 3600.0
            holding_times_h.append(ht)

    notionals = [abs(float(f.get("sz", 0))) * abs(float(f.get("px", 0))) for f in oc]
    settled_pnls = [float(f.get("closedPnl", 0) or 0) for f in oc if float(f.get("closedPnl", 0) or 0) != 0]

    if not settled_pnls:
        return None

    wins = sum(1 for p in settled_pnls if p > 0)
    win_rate = wins / len(settled_pnls)
    net = sum(settled_pnls)
    max_loss = min(settled_pnls)
    med_fills_per_coin = statistics.median(fills_per_coin)
    med_hold_h = statistics.median(holding_times_h) if holding_times_h else 0
    med_ntl = statistics.median(notionals) if notionals else 0
    fills_per_day = len(oc) / LOOKBACK_DAYS

    # Composite score favors directional shape: positive PnL × win-rate, gated by sample/holding
    score = net * (0.5 + win_rate) if len(settled_pnls) >= 5 else 0

    return DirStats(
        address=addr,
        rank=rank,
        overall_pnl_30d=pnl_30d,
        outcome_fills=len(oc),
        distinct_outcomes=len(by_coin),
        settled_pnl=round(net, 2),
        win_rate=round(win_rate, 3),
        median_fills_per_coin=round(med_fills_per_coin, 1),
        median_holding_h=round(med_hold_h, 2),
        median_ntl=round(med_ntl, 0),
        max_single_loss=round(max_loss, 2),
        fills_per_day=round(fills_per_day, 1),
        quality_score=round(score, 0),
    )


def passes_directional(s: DirStats) -> bool:
    return (
        s.settled_pnl >= MIN_SETTLED_PNL
        and s.median_fills_per_coin <= MAX_FILLS_PER_COIN
        and s.median_holding_h >= MIN_HOLDING_H
        and s.median_ntl >= MIN_MEDIAN_NTL
    )


def main() -> int:
    print(f"Pulling top {TOP_N} traders (30d)…", file=sys.stderr, flush=True)
    leaders = fetch_leaderboard(TOP_N)
    print(f"Got {len(leaders)} leaders", file=sys.stderr, flush=True)
    since_ms = int((time.time() - LOOKBACK_DAYS * 86400) * 1000)
    results: list[DirStats] = []
    for i, row in enumerate(leaders):
        addr = row["address"].lower()
        rank = row.get("rank", -1)
        pnl_30d = float(row.get("pnl", 0))
        fills = fetch_fills(addr, since_ms)
        s = compute(addr, rank, pnl_30d, fills)
        if s:
            results.append(s)
        if (i + 1) % 10 == 0:
            print(f"  …{i + 1}/{len(leaders)}", file=sys.stderr, flush=True)
        time.sleep(0.15)

    # All results to CSV
    csv_path = "research/outcome_leaders_directional_full.csv"
    with open(csv_path, "w", newline="") as fh:
        w = csv.writer(fh)
        rows = sorted(results, key=lambda s: s.quality_score, reverse=True)
        if rows:
            w.writerow(list(asdict(rows[0]).keys()))
            for s in rows:
                w.writerow(list(asdict(s).values()))
    print(f"wrote {csv_path} ({len(results)} rows)", file=sys.stderr)

    # Filter to directional shape
    directional = [s for s in results if passes_directional(s)]
    directional.sort(key=lambda s: s.quality_score, reverse=True)
    print(f"\n=== DIRECTIONAL OUTCOME BETTORS ({len(directional)} of {len(results)} passed filter) ===")
    print(f"  filter: settled_pnl ≥ ${MIN_SETTLED_PNL}, ≤ {MAX_FILLS_PER_COIN} fills/coin, ≥ {MIN_HOLDING_H}h holding, ≥ ${MIN_MEDIAN_NTL} median ntl")
    print()
    if not directional:
        print("  *** NONE PASS ***  — top HL outcome PnL is entirely MM flow.")
        print("  Implication: directional outcome edge isn't visible at the leaderboard level.")
        return 0

    print(f"{'rk':>3}  {'address':<44}  {'pnl':>9}  {'wr':>5}  {'fpc':>4}  {'hold(h)':>8}  {'med$':>6}  {'maxL':>9}  {'score':>9}")
    for s in directional[:20]:
        print(
            f"{s.rank:>3}  {s.address:<44}  ${s.settled_pnl:>8,.0f}  {s.win_rate:>5.0%}  {s.median_fills_per_coin:>4.1f}  {s.median_holding_h:>8.1f}  ${s.median_ntl:>5.0f}  ${s.max_single_loss:>8,.0f}  {s.quality_score:>9,.0f}"
        )

    # Borderline candidates: meet 2-3 of 4 directional criteria
    border = [
        s for s in results if not passes_directional(s)
        and s.settled_pnl >= MIN_SETTLED_PNL
        and sum([
            s.median_fills_per_coin <= MAX_FILLS_PER_COIN,
            s.median_holding_h >= MIN_HOLDING_H,
            s.median_ntl >= MIN_MEDIAN_NTL,
        ]) >= 2
    ]
    border.sort(key=lambda s: s.quality_score, reverse=True)
    if border:
        print(f"\n=== borderline (meet PnL + 2/3 other filters) — {len(border)} ===")
        for s in border[:10]:
            print(
                f"{s.rank:>3}  {s.address:<44}  ${s.settled_pnl:>8,.0f}  {s.win_rate:>5.0%}  {s.median_fills_per_coin:>4.1f}  {s.median_holding_h:>8.1f}  ${s.median_ntl:>5.0f}  {s.quality_score:>9,.0f}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
