"""Book + trade snapshot logger for MM model training.

Subscribes via WebSocket to L2 book + trades for one or more coins; writes
compact JSONL to `state/book_snapshots/<coin>.jsonl`. Read-only, submits
nothing.

Features captured per snapshot (used later to train fill-prob, adverse-
selection, micro-price):
  - mid, best_bid, best_ask, spread_bps
  - top-5 depth each side (sz sums)
  - book imbalance (bid_sz / (bid_sz + ask_sz)) at L1 and L5
  - trade flow: aggressor side, size, price, delta-from-mid

Rotation: one file per coin, one line per event. Snapshot on every L2 update
plus every trade. Tiny — ~200 bytes/event.

Run:
    .venv/bin/python scripts/book_logger.py \\
        --coins '#44650,#45160' \\
        --out-dir state/book_snapshots

Kill: pkill -f book_logger, or touch state/BOOK_LOGGER_STOP.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path

from hyperliquid.info import Info

from src.hl_hip3 import register_hip3_dexes
from src.hl_outcome import register_outcome_assets
from src.log import setup_logging

log = logging.getLogger("book_logger")
HL_API = "https://api.hyperliquid.xyz"
STOP_FILE = "./state/BOOK_LOGGER_STOP"


def _levels_summary(levels: list) -> tuple[float, float]:
    """Sum sizes for the first up-to-5 levels. Returns (l1_sz, l5_sz)."""
    if not levels:
        return 0.0, 0.0
    try:
        l1 = float(levels[0].get("sz", 0))
    except (KeyError, TypeError, ValueError):
        l1 = 0.0
    l5 = 0.0
    for lvl in levels[:5]:
        try:
            l5 += float(lvl.get("sz", 0))
        except (KeyError, TypeError, ValueError):
            continue
    return l1, l5


def main() -> int:
    p = argparse.ArgumentParser(prog="book_logger")
    p.add_argument("--coins", required=True, help="Comma-separated coin list")
    p.add_argument("--out-dir", default="state/book_snapshots")
    args = p.parse_args()

    setup_logging(level="INFO", json_mode=False)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    coins = [c.strip() for c in args.coins.split(",") if c.strip()]
    log.info("book_logger: starting for coins=%s out=%s", coins, out_dir)

    files: dict[str, any] = {c: open(out_dir / f"{c.replace('/', '_').replace(':', '_').replace('#', 'h')}.jsonl", "a") for c in coins}

    info = Info(HL_API, skip_ws=False)
    register_outcome_assets(info)
    # HIP-3 needs dex registration for xyz:*, para:*, etc.
    try:
        n = register_hip3_dexes(info)
        log.info("book_logger: registered %d HIP-3 dexes", n)
    except Exception:
        log.exception("book_logger: HIP-3 dex registration failed (continuing without)")

    def _write(coin: str, rec: dict) -> None:
        f = files.get(coin)
        if not f:
            return
        f.write(json.dumps(rec, separators=(",", ":")) + "\n")
        f.flush()

    def on_l2(coin: str):
        def handler(msg: dict) -> None:
            d = msg.get("data") or {}
            levels = d.get("levels") or []
            if len(levels) < 2 or not levels[0] or not levels[1]:
                return
            try:
                best_bid = float(levels[0][0]["px"])
                best_ask = float(levels[1][0]["px"])
            except (KeyError, TypeError, ValueError, IndexError):
                return
            mid = (best_bid + best_ask) / 2.0
            if mid <= 0:
                return
            spread_bps = (best_ask - best_bid) / mid * 10_000.0
            bid_l1, bid_l5 = _levels_summary(levels[0])
            ask_l1, ask_l5 = _levels_summary(levels[1])
            imb_l1 = bid_l1 / (bid_l1 + ask_l1) if (bid_l1 + ask_l1) > 0 else 0.5
            imb_l5 = bid_l5 / (bid_l5 + ask_l5) if (bid_l5 + ask_l5) > 0 else 0.5
            ts = float(d.get("time", time.time() * 1000)) / 1000.0
            _write(coin, {
                "ts": ts, "event": "book", "coin": coin,
                "bid": best_bid, "ask": best_ask, "mid": mid,
                "spread_bps": round(spread_bps, 4),
                "bid_l1": bid_l1, "ask_l1": ask_l1,
                "bid_l5": bid_l5, "ask_l5": ask_l5,
                "imb_l1": round(imb_l1, 4),
                "imb_l5": round(imb_l5, 4),
            })
        return handler

    def on_trades(coin: str):
        def handler(msg: dict) -> None:
            for t in msg.get("data", []):
                try:
                    ts = float(t.get("time", 0)) / 1000.0
                    _write(coin, {
                        "ts": ts, "event": "trade", "coin": coin,
                        "side": t.get("side", ""),
                        "px": float(t.get("px", 0)),
                        "sz": float(t.get("sz", 0)),
                    })
                except (KeyError, TypeError, ValueError):
                    continue
        return handler

    for c in coins:
        try:
            info.subscribe({"type": "l2Book", "coin": c}, on_l2(c))
            info.subscribe({"type": "trades", "coin": c}, on_trades(c))
        except Exception:
            log.exception("subscribe failed for %s", c)

    log.info("book_logger: subscribed. Loop until STOP file appears.")
    while not os.path.exists(STOP_FILE):
        time.sleep(5)
    log.info("book_logger: STOP file seen — exiting")
    for f in files.values():
        try: f.close()
        except Exception: pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
