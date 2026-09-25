"""Backfill HL 1m candles for vol / cross-market feature training.

Read-only. Writes per-coin JSONL to state/candles/<coin>.jsonl.

Grabs the last N days of 1m candles for a coin list via HL /info candleSnapshot.
Respects rate limits by sleeping between requests.

Run:
    .venv/bin/python scripts/candle_backfill.py --days 14 \\
      --coins 'BTC,ETH,SOL,HYPE,ZEC,TAO,XLM,ONDO,SKHX,SP500'
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

from hyperliquid.info import Info

from src.hl_outcome import register_outcome_assets
from src.log import setup_logging

log = logging.getLogger("candle_backfill")
HL_API = "https://api.hyperliquid.xyz"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--coins", required=True)
    p.add_argument("--interval", default="1m")
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--out-dir", default="state/candles")
    p.add_argument("--sleep-s", type=float, default=0.6)  # respect rate limit
    args = p.parse_args()

    setup_logging(level="INFO", json_mode=False)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    info = Info(HL_API, skip_ws=True)
    register_outcome_assets(info)

    coins = [c.strip() for c in args.coins.split(",") if c.strip()]
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - args.days * 86400 * 1000

    for c in coins:
        # HL caps at ~5000 candles per request; 14d of 1m = 20160 candles, so chunk.
        chunk_ms = 4000 * 60 * 1000  # ~4000 minutes = ~2.8d
        cursor = start_ms
        out_path = out_dir / f"{c.replace('/', '_').replace(':', '_')}.jsonl"
        with open(out_path, "w") as f:
            total = 0
            while cursor < end_ms:
                chunk_end = min(cursor + chunk_ms, end_ms)
                resp = None
                backoff = args.sleep_s
                for attempt in range(6):
                    try:
                        resp = info.post("/info", {
                            "type": "candleSnapshot",
                            "req": {"coin": c, "interval": args.interval,
                                    "startTime": cursor, "endTime": chunk_end}
                        })
                        break
                    except Exception as e:
                        msg = str(e)
                        if "429" in msg and attempt < 5:
                            wait = min(60.0, backoff * (2 ** attempt))
                            log.warning("candles: %s 429 attempt %d/6, sleeping %.1fs", c, attempt+1, wait)
                            time.sleep(wait)
                            continue
                        log.exception("candles: %s chunk failed (attempt %d)", c, attempt+1)
                        break
                if resp is None:
                    cursor = chunk_end
                    time.sleep(args.sleep_s)
                    continue
                if isinstance(resp, list):
                    for candle in resp:
                        f.write(json.dumps(candle, separators=(",", ":")) + "\n")
                        total += 1
                cursor = chunk_end
                time.sleep(args.sleep_s)
            log.info("candles: %s wrote %d rows -> %s", c, total, out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
