#!/usr/bin/env python3
"""CLV paper journal closer.

Runs at or shortly before each game's kickoff. Pulls the most recent
Kalshi snapshot for every ticker in state/clv_paper_journal.jsonl,
records the closing mid, computes CLV in percentage points, and (after
game ends) records the actual outcome.

CLV = closing_mid - entry_mid
Positive CLV = you got a better price than the market closed at => sharp signal.

Usage:
    python clv_closer.py --close    # update closing_mid for all open picks
    python clv_closer.py --settle   # update actual_outcome from Firecrawl results
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path

STATE = Path(__file__).resolve().parent.parent / "state"
JOURNAL = STATE / "clv_paper_journal.jsonl"
KALSHI_DIR = STATE / "kalshi"


def latest_kalshi() -> dict:
    files = sorted(
        (p for p in KALSHI_DIR.glob("markets_*.jsonl") if p.stat().st_size > 0),
        key=lambda p: p.stat().st_mtime,
    )
    if not files:
        return {}
    by_ticker = {}
    for line in files[-1].read_text().splitlines():
        try: d = json.loads(line)
        except: continue
        by_ticker[d.get("market_ticker","")] = d
    return by_ticker


def read_journal() -> list[dict]:
    if not JOURNAL.exists(): return []
    out = []
    for line in JOURNAL.read_text().splitlines():
        try: out.append(json.loads(line))
        except: continue
    return out


def write_journal(entries: list[dict]) -> None:
    with JOURNAL.open("w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def main():
    if "--close" in sys.argv:
        kalshi = latest_kalshi()
        if not kalshi:
            print("no kalshi snapshots found")
            return 1
        entries = read_journal()
        updated = 0
        print(f"{'pick':<30} {'entry':>8} {'closing':>8} {'CLV pp':>8}")
        for e in entries:
            if e.get("closing_mid") is not None: continue
            tkr = e.get("ticker","")
            m = kalshi.get(tkr)
            if not m: continue
            close = m.get("mid")
            e["closing_mid"] = close
            e["closing_ts"] = int(time.time())
            e["clv_pp"] = round((close - e["entry_mid"]) * 100, 2)
            print(f'{e["pick"][:28]:<30} {e["entry_mid"]:>8.3f} {close:>8.3f} {e["clv_pp"]:>+8.2f}')
            updated += 1
        write_journal(entries)
        # Summary
        open_picks = [x for x in entries if x.get("clv_pp") is not None and x.get("actual_outcome") is None]
        if open_picks:
            total_clv = sum(x["clv_pp"] for x in open_picks)
            print(f"\nTotal CLV across {len(open_picks)} picks: {total_clv:+.2f}pp  (avg {total_clv/len(open_picks):+.2f}pp)")
            if total_clv > 0:
                print("positive aggregate CLV — signal looks sharp")
            else:
                print("negative aggregate CLV — picks are retail quality")
        print(f"\nupdated {updated} picks")
        return 0

    if "--settle" in sys.argv:
        print("not implemented yet — ask again after games end")
        return 0

    print("usage: clv_closer.py --close | --settle")
    return 1


if __name__ == "__main__":
    sys.exit(main())
