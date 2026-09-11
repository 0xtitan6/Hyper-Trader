"""Research script — find quality outcome traders from the HL leaderboard.

Not committed; lives under research/ for ad-hoc analysis.

Pipeline:
  1. Pull top N traders by 30d PnL from Liquidiction
  2. For each, fetch their HL fills over the lookback window
  3. Compute outcome-only stats: fills, settled PnL, win rate, max loss, holdings
  4. Rank and print a shortlist for operator review
"""

from __future__ import annotations

import csv
import json
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass

import requests

LB_URL = "https://liquidiction.xyz/api/leaderboard"
HL_URL = "https://api.hyperliquid.xyz/info"
LOOKBACK_DAYS = 30
TOP_N = 80
MIN_OUTCOME_FILLS = 10  # require some sample size before scoring


@dataclass
class OutcomeStats:
    address: str
    rank: int
    overall_pnl_30d: float
    overall_trades_30d: int
    outcome_fills: int
    outcome_buys: int
    outcome_sells: int
    settled_pnl: float
    gross_win: float
    gross_loss: float
    win_rate_settled: float
    max_single_loss: float
    distinct_outcomes: int
    perp_fills: int
    outcome_fraction: float
    quality_score: float


def fetch_leaderboard(n: int) -> list[dict]:
    out: list[dict] = []
    offset = 0
    page = 50
    while len(out) < n:
        r = requests.get(LB_URL, params={"period": "month", "offset": offset, "limit": page}, timeout=15)
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


def compute_stats(addr: str, rank: int, pnl_30d: float, trades_30d: int, fills: list[dict]) -> OutcomeStats:
    outcome_fills = [f for f in fills if is_outcome(f.get("coin", ""))]
    perp_fills = [f for f in fills if not is_outcome(f.get("coin", "")) and "/" not in f.get("coin", "")]

    buys = [f for f in outcome_fills if f.get("side") == "B"]
    sells = [f for f in outcome_fills if f.get("side") == "A"]

    settled = [f for f in outcome_fills if float(f.get("closedPnl", 0) or 0) != 0]
    settled_pnls = [float(f.get("closedPnl", 0) or 0) for f in settled]
    gross_win = sum(p for p in settled_pnls if p > 0)
    gross_loss = sum(p for p in settled_pnls if p < 0)
    wins = sum(1 for p in settled_pnls if p > 0)
    win_rate = wins / len(settled_pnls) if settled_pnls else 0.0
    max_single_loss = min(settled_pnls) if settled_pnls else 0.0

    # Group fills per outcome (coin) to get distinct outcomes touched
    by_coin: dict[str, list[dict]] = defaultdict(list)
    for f in outcome_fills:
        by_coin[f.get("coin", "")].append(f)

    total_fills_window = len(fills)
    outcome_fraction = len(outcome_fills) / total_fills_window if total_fills_window else 0.0

    # Quality score: positive settled PnL × win-rate, penalized by max loss size
    # Simple heuristic — get the ranking shape first; refine after seeing data.
    net = sum(settled_pnls)
    # Penalize when max single loss > 50% of net win (fat-tail blow-up risk)
    penalty = 1.0
    if gross_win > 0 and abs(max_single_loss) > 0.5 * gross_win:
        penalty = 0.5
    score = net * (0.5 + win_rate) * penalty if len(settled_pnls) >= MIN_OUTCOME_FILLS else 0.0

    return OutcomeStats(
        address=addr,
        rank=rank,
        overall_pnl_30d=pnl_30d,
        overall_trades_30d=trades_30d,
        outcome_fills=len(outcome_fills),
        outcome_buys=len(buys),
        outcome_sells=len(sells),
        settled_pnl=round(net, 2),
        gross_win=round(gross_win, 2),
        gross_loss=round(gross_loss, 2),
        win_rate_settled=round(win_rate, 3),
        max_single_loss=round(max_single_loss, 2),
        distinct_outcomes=len(by_coin),
        perp_fills=len(perp_fills),
        outcome_fraction=round(outcome_fraction, 3),
        quality_score=round(score, 2),
    )


def main() -> int:
    print(f"Pulling top {TOP_N} traders (30d)…", file=sys.stderr, flush=True)
    leaders = fetch_leaderboard(TOP_N)
    print(f"Got {len(leaders)} leaders", file=sys.stderr, flush=True)

    since_ms = int((time.time() - LOOKBACK_DAYS * 86400) * 1000)
    results: list[OutcomeStats] = []
    for i, row in enumerate(leaders):
        addr = row["address"].lower()
        rank = row.get("rank", -1)
        pnl = float(row.get("pnl", 0))
        trades = int(row.get("trades", 0))
        fills = fetch_fills(addr, since_ms)
        stats = compute_stats(addr, rank, pnl, trades, fills)
        results.append(stats)
        if (i + 1) % 5 == 0:
            print(f"  …{i + 1}/{len(leaders)}", file=sys.stderr, flush=True)
        time.sleep(0.15)

    # Rank by quality score
    ranked = sorted(results, key=lambda s: s.quality_score, reverse=True)

    # Output CSV for full record
    csv_path = "research/outcome_leaders.csv"
    with open(csv_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(list(asdict(ranked[0]).keys()))
        for s in ranked:
            w.writerow(list(asdict(s).values()))
    print(f"wrote {csv_path}", file=sys.stderr)

    # Print top 15 shortlist to stdout
    print("\n=== top 15 outcome-leader candidates ===")
    print(f"{'rank':>4}  {'address':<44}  {'settledPnL':>10}  {'wins/n':>8}  {'max1L':>8}  {'#oc':>4}  {'ocFrac':>6}  {'score':>8}")
    for s in ranked[:15]:
        wins = int(s.win_rate_settled * (s.outcome_fills - s.outcome_buys + s.outcome_sells)) if s.outcome_fills else 0
        wins = int(s.win_rate_settled * max(1, len([1 for _ in range(int(s.outcome_fills))])))  # rough
        n_settled = "?"
        print(
            f"{s.rank:>4}  {s.address:<44}  ${s.settled_pnl:>9,.0f}  {s.win_rate_settled:>7.1%}  ${s.max_single_loss:>7,.0f}  {s.distinct_outcomes:>4}  {s.outcome_fraction:>6.1%}  {s.quality_score:>8,.0f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
