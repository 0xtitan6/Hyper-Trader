"""Polymarket public API poller — grab active markets + outcome prices.

Read-only. Writes JSONL snapshots to state/polymarket/markets_<epoch>.jsonl
every N seconds. Later join to HL outcomes by fuzzy question-match for
fair-value comparison.

Run:
    .venv/bin/python scripts/polymarket_poller.py --interval 60 --limit 500

Kill: touch state/POLYMARKET_STOP
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
import urllib.request
from pathlib import Path

log = logging.getLogger("polymarket_poller")
STOP_FILE = "./state/POLYMARKET_STOP"
ENDPOINT = "https://gamma-api.polymarket.com/markets"


def fetch(limit: int = 500, offset: int = 0, tag_id: int | None = None) -> list:
    url = f"{ENDPOINT}?limit={limit}&offset={offset}&active=true&closed=false"
    if tag_id is not None:
        url += f"&tag_id={tag_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--interval", type=int, default=60)
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--out-dir", default="state/polymarket")
    p.add_argument("--tag-ids", default="1,100639",
                   help="Comma-separated tag_ids (default: 1=broad sports, 100639=soccer/fixtures)")
    args = p.parse_args()
    tag_ids = [int(x) for x in args.tag_ids.split(",") if x.strip()]

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log.info("polymarket_poller: interval=%ds limit=%d", args.interval, args.limit)

    while not os.path.exists(STOP_FILE):
        try:
            ts = int(time.time())
            out_path = out_dir / f"markets_{ts}.jsonl"
            n = 0
            seen_ids = set()
            with open(out_path, "w") as f:
                for tid in tag_ids:
                    offset = 0
                    while True:
                        markets = fetch(limit=args.limit, offset=offset, tag_id=tid)
                        if not markets:
                            break
                        for m in markets:
                            mid = m.get("id")
                            if mid in seen_ids:
                                continue
                            seen_ids.add(mid)
                            slim = {
                                "ts": ts,
                                "tag_id": tid,
                                "id": mid,
                                "question": m.get("question"),
                                "slug": m.get("slug"),
                                "endDate": m.get("endDate"),
                                "outcomePrices": m.get("outcomePrices"),
                                "outcomes": m.get("outcomes"),
                                "volume": m.get("volume"),
                                "liquidity": m.get("liquidity"),
                                "category": m.get("category"),
                            }
                            f.write(json.dumps(slim, separators=(",", ":")) + "\n")
                            n += 1
                        if len(markets) < args.limit:
                            break
                        offset += args.limit
                        time.sleep(0.6)
            log.info("wrote %d markets across tags=%s -> %s", n, tag_ids, out_path)
        except Exception:
            log.exception("polymarket fetch failed")
        time.sleep(args.interval)

    log.info("STOP file seen — exiting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
