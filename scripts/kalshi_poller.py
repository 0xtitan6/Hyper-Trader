"""Kalshi public API poller — grab NFL / MLB / sports market orderbooks.

Read-only. No API key needed for public market data. Writes JSONL snapshots to
state/kalshi/markets_<epoch>.jsonl with parsed bid/ask/mid for each contract.

Kalshi conventions used here:
  - Each event (e.g. NFL game) has 2 markets: one "TEAM_A wins" YES, one "TEAM_B wins" YES.
  - Orderbook has `yes_dollars` (bids to buy YES) and `no_dollars` (bids to buy NO).
  - Best YES bid = max(yes_dollars price). Best YES ask = 1 - max(no_dollars price).

Run:
    .venv-ml/bin/python scripts/kalshi_poller.py --interval 60 --series KXNFLGAME

Kill: touch state/KALSHI_STOP
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
import urllib.request
from pathlib import Path

log = logging.getLogger("kalshi_poller")
STOP_FILE = "./state/KALSHI_STOP"
BASE = "https://api.elections.kalshi.com/trade-api/v2"


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def _best_yes(ob: dict) -> tuple[float | None, float | None, float, float]:
    """Return (yes_bid, yes_ask, yes_bid_depth_usd, yes_ask_depth_usd)."""
    fp = ob.get("orderbook_fp") or ob.get("orderbook") or {}
    yes_bids = fp.get("yes_dollars") or []
    no_bids = fp.get("no_dollars") or []
    yes_bid = max((float(p) for p, _ in yes_bids), default=None)
    no_bid = max((float(p) for p, _ in no_bids), default=None)
    yes_ask = (1.0 - no_bid) if no_bid is not None else None
    bid_depth = sum(float(sz) for _, sz in yes_bids)
    ask_depth = sum(float(sz) for _, sz in no_bids)
    return yes_bid, yes_ask, bid_depth, ask_depth


def fetch_series_events(series: str) -> list:
    d = _get(f"{BASE}/events?series_ticker={series}&status=open&limit=200")
    return d.get("events", [])


def fetch_event_markets(event_ticker: str) -> list:
    """Kalshi /events returns event shells; need /markets?event_ticker= for actual list."""
    d = _get(f"{BASE}/markets?event_ticker={event_ticker}&status=open&limit=100")
    return d.get("markets", [])


def fetch_market_orderbook(ticker: str) -> dict:
    return _get(f"{BASE}/markets/{ticker}/orderbook")


def fetch_market(ticker: str) -> dict:
    return _get(f"{BASE}/markets/{ticker}").get("market", {})


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--interval", type=int, default=300)
    p.add_argument("--series", default="KXNFLGAME,KXMLBGAME",
                   help="Comma-separated Kalshi series tickers to poll")
    p.add_argument("--out-dir", default="state/kalshi")
    p.add_argument("--sleep-s", type=float, default=0.4)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    series_list = [s.strip() for s in args.series.split(",") if s.strip()]

    log.info("kalshi_poller: interval=%ds series=%s", args.interval, series_list)

    while not os.path.exists(STOP_FILE):
        ts = int(time.time())
        out_path = out_dir / f"markets_{ts}.jsonl"
        n = 0
        with open(out_path, "w") as f:
            for series in series_list:
                try:
                    evs = fetch_series_events(series)
                except Exception:
                    log.exception("failed to fetch series %s", series)
                    continue
                for ev in evs:
                    ev_ticker = ev.get("event_ticker")
                    ev_title = ev.get("title")
                    try:
                        markets = fetch_event_markets(ev_ticker)
                        time.sleep(args.sleep_s)
                    except Exception:
                        log.exception("markets fetch failed for event %s", ev_ticker)
                        continue
                    for m in markets:
                        ticker = m.get("ticker")
                        if not ticker:
                            continue
                        try:
                            ob = fetch_market_orderbook(ticker)
                            time.sleep(args.sleep_s)
                        except Exception:
                            log.exception("orderbook fetch failed for %s", ticker)
                            continue
                        yes_bid, yes_ask, bid_depth, ask_depth = _best_yes(ob)
                        mid = ((yes_bid + yes_ask) / 2) if (yes_bid and yes_ask) else None
                        spread = (yes_ask - yes_bid) if (yes_bid and yes_ask) else None
                        row = {
                            "ts": ts,
                            "series": series,
                            "event_ticker": ev_ticker,
                            "event_title": ev_title,
                            "market_ticker": ticker,
                            "market_title": m.get("title"),
                            "close_time": m.get("close_time"),
                            "yes_bid": yes_bid,
                            "yes_ask": yes_ask,
                            "mid": mid,
                            "spread": spread,
                            "yes_bid_depth_usd": bid_depth,
                            "yes_ask_depth_usd": ask_depth,
                        }
                        f.write(json.dumps(row, separators=(",", ":")) + "\n")
                        n += 1
        log.info("kalshi_poller wrote %d markets -> %s", n, out_path)
        time.sleep(args.interval)

    log.info("STOP file seen — exiting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
