#!/usr/bin/env python3
"""Sharp-money NFL scanner.

Reads the Kalshi poller's historical snapshots and ranks every live market
by how much its line has moved over the last N hours. Sharp money moves
lines; retail money doesn't. Lines that have steamed in one direction over
24-72 hours are often sharp-driven — betting WITH that movement captures
positive expected CLV.

Outputs:
    - state/sharp_scan_latest.json: full ranking + metadata
    - stdout: table of top steam movers

Usage:
    python sharp_scanner.py                # scan next upcoming NFL slate
    python sharp_scanner.py --hours 48     # window length
    python sharp_scanner.py --min-move 2   # min pp move to report
"""
from __future__ import annotations
import json, sys, time, argparse
from pathlib import Path
from datetime import datetime, UTC
from collections import defaultdict

STATE = Path(__file__).resolve().parent.parent / "state"
KALSHI_DIR = STATE / "kalshi"
OUT = STATE / "sharp_scan_latest.json"


def load_history(hours_back: float) -> dict[str, list[tuple[float, float]]]:
    """Returns {market_ticker: [(ts, mid), ...]} sorted by ts."""
    cutoff = time.time() - hours_back * 3600
    history: dict[str, list[tuple[float, float]]] = defaultdict(list)
    files = sorted(KALSHI_DIR.glob("markets_*.jsonl"), key=lambda p: p.stat().st_mtime)
    for f in files:
        if f.stat().st_mtime < cutoff:
            continue
        try:
            for line in f.read_text().splitlines():
                try: d = json.loads(line)
                except: continue
                tkr = d.get("market_ticker", "")
                mid = d.get("mid")
                if tkr and mid is not None:
                    history[tkr].append((f.stat().st_mtime, mid))
        except Exception:
            continue
    for tkr in history:
        history[tkr].sort()
    return history


def analyze(history: dict[str, list[tuple[float, float]]]) -> list[dict]:
    """For each market, compute move + consistency."""
    out = []
    for tkr, pts in history.items():
        if len(pts) < 3:
            continue
        first_ts, first_mid = pts[0]
        last_ts, last_mid = pts[-1]
        move = last_mid - first_mid
        # consistency: fraction of consecutive samples moving same direction
        same_dir = 0
        total = 0
        prev = first_mid
        for ts, mid in pts[1:]:
            if mid != prev:
                total += 1
                if (mid - prev) * move > 0:
                    same_dir += 1
                prev = mid
        consistency = (same_dir / total) if total > 0 else 0
        hours = (last_ts - first_ts) / 3600
        if hours < 1:
            continue
        out.append({
            "ticker": tkr,
            "first_mid": round(first_mid, 4),
            "last_mid": round(last_mid, 4),
            "move_pp": round(move * 100, 2),
            "abs_move_pp": round(abs(move) * 100, 2),
            "hours_window": round(hours, 1),
            "samples": len(pts),
            "consistency": round(consistency, 3),
        })
    out.sort(key=lambda x: -x["abs_move_pp"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=96, help="history window hours")
    ap.add_argument("--min-move", type=float, default=1.5, help="min pp move to report")
    ap.add_argument("--series", default="KXNFLGAME", help="market series prefix filter")
    args = ap.parse_args()

    history = load_history(args.hours)
    history = {k: v for k, v in history.items() if args.series in k}
    analysis = analyze(history)
    movers = [a for a in analysis if a["abs_move_pp"] >= args.min_move]

    # Write out
    OUT.write_text(json.dumps({
        "ts": int(time.time()),
        "window_hours": args.hours,
        "series": args.series,
        "min_move_pp": args.min_move,
        "all_markets": len(analysis),
        "movers": movers,
    }, indent=2))

    # Pretty print
    print(f"=== Sharp scan ({args.hours:.0f}h window, min {args.min_move}pp move) ===")
    print(f"total markets tracked: {len(analysis)}  qualifying movers: {len(movers)}")
    print()
    print(f'{"ticker":<42} {"first":>7} {"last":>7} {"move":>7} {"consist":>8} {"hrs":>5}')
    print("-"*85)
    for m in movers[:25]:
        arrow = "↑" if m["move_pp"] > 0 else "↓"
        print(f'{m["ticker"]:<42} {m["first_mid"]:>7.3f} {m["last_mid"]:>7.3f} {m["move_pp"]:>+6.2f}{arrow} {m["consistency"]:>8.2f} {m["hours_window"]:>5.1f}')

    print()
    print("Interpretation:")
    print("  - High abs_move + high consistency = sharp steam, bet WITH the movement")
    print("  - Low consistency = noise or back-and-forth, skip")
    print("  - For CLV: bet the direction the line is already moving in")


if __name__ == "__main__":
    sys.exit(main() or 0)
