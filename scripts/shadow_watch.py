"""Shadow-track an outcome leader's fills into a paper journal.

Polls HL `userFillsByTime` every 20s for the target wallet, classifies each
new outcome fill as open/add/reduce/close based on `startPosition`, and
records the leader fill + the hypothetical mirror our bot would have made
under a per-trade cap. Never places an order.

Run:
    nohup .venv/bin/python -m scripts.shadow_watch \\
        --wallet 0xbdfa4f4492dd7b7cf211209c4791af8d52bf5c50 \\
        --max-per-trade-usd 25 \\
        --until 2026-06-26T16:46:00Z \\
        --out state/shadow_journal.jsonl \\
        >> state/shadow.log 2>&1 &
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

HL_URL = "https://api.hyperliquid.xyz/info"
POLL_INTERVAL_S = 20

log = logging.getLogger("shadow")


def is_outcome(coin: str) -> bool:
    return coin.startswith("#") or coin.startswith("+")


def classify(side: str, start_position: float) -> str:
    """Classify a fill given the leader's pre-fill position.

    side: "B" (buy) | "A" (sell/ask)
    """
    if start_position == 0:
        return "open_long" if side == "B" else "open_short"
    if start_position > 0:
        return "add_long" if side == "B" else "reduce_long"
    return "reduce_short" if side == "B" else "add_short"


def fetch_fills(wallet: str, start_ms: int) -> list[dict]:
    r = requests.post(
        HL_URL,
        json={"type": "userFillsByTime", "user": wallet.lower(), "startTime": start_ms},
        timeout=20,
    )
    r.raise_for_status()
    return r.json() or []


def hypothetical_mirror(fill: dict, max_per_trade_usd: float) -> dict:
    """Compute what our paper-mirror would have done under the cap.

    We only mirror OPENS (open_long, open_short). Adds/reduces/closes are
    skipped — Track 1's whole premise is leaders make money at ENTRY.
    """
    sz = abs(float(fill.get("sz", 0)))
    px = abs(float(fill.get("px", 0)))
    leader_ntl = sz * px
    if leader_ntl == 0:
        return {"hyp_action": "skip_zero_ntl"}
    factor = min(1.0, max_per_trade_usd / leader_ntl)
    hyp_sz = sz * factor
    hyp_ntl = hyp_sz * px
    return {
        "hyp_action": "mirror",
        "hyp_sz": round(hyp_sz, 6),
        "hyp_notional_usd": round(hyp_ntl, 2),
        "hyp_size_factor": round(factor, 4),
        "leader_notional_usd": round(leader_ntl, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wallet", required=True)
    ap.add_argument("--max-per-trade-usd", type=float, default=25.0)
    ap.add_argument("--out", required=True, help="output JSONL path")
    ap.add_argument("--until", required=True, help="UTC ISO timestamp to stop")
    ap.add_argument("--bootstrap-min", type=int, default=5, help="look back this many minutes on first poll")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    until = datetime.fromisoformat(args.until.replace("Z", "+00:00"))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    seen_tids: set[int] = set()
    if out_path.exists():
        with out_path.open() as fh:
            for line in fh:
                try:
                    e = json.loads(line)
                    if e.get("type") == "leader_fill":
                        seen_tids.add(int(e["tid"]))
                except Exception:
                    continue
        log.info("loaded %d prior tids from %s", len(seen_tids), out_path)

    last_ms = int((time.time() - args.bootstrap_min * 60) * 1000)
    log.info("shadow-tracking %s until %s, cap=$%.0f", args.wallet, until.isoformat(), args.max_per_trade_usd)

    while datetime.now(tz=timezone.utc) < until:
        try:
            fills = fetch_fills(args.wallet, last_ms)
        except Exception as e:
            log.warning("poll failed: %s", e)
            time.sleep(POLL_INTERVAL_S)
            continue

        new_outcomes = 0
        for f in sorted(fills, key=lambda x: x.get("time", 0)):
            ts_ms = int(f.get("time", 0))
            tid = int(f.get("tid", 0))
            if tid in seen_tids:
                continue
            seen_tids.add(tid)
            last_ms = max(last_ms, ts_ms)
            coin = f.get("coin", "")
            if not is_outcome(coin):
                continue
            new_outcomes += 1
            start_pos = float(f.get("startPosition", 0) or 0)
            side = f.get("side", "?")
            action = classify(side, start_pos)
            record = {
                "type": "leader_fill",
                "ts": ts_ms / 1000.0,
                "tid": tid,
                "leader": args.wallet.lower(),
                "coin": coin,
                "side": side,
                "sz": float(f.get("sz", 0)),
                "px": float(f.get("px", 0)),
                "start_position": start_pos,
                "closed_pnl": float(f.get("closedPnl", 0) or 0),
                "action": action,
            }
            if action.startswith("open_"):
                record.update(hypothetical_mirror(f, args.max_per_trade_usd))
            else:
                record["hyp_action"] = f"skip_{action}"  # only mirror opens

            with out_path.open("a") as fh:
                fh.write(json.dumps(record) + "\n")
            log.info(
                "%s %s %s sz=%s px=%s action=%s hyp=%s",
                coin, side, f"start={start_pos}", record["sz"], record["px"], action,
                record.get("hyp_action"),
            )

        if new_outcomes:
            log.info("logged %d new outcome fills", new_outcomes)
        time.sleep(POLL_INTERVAL_S)

    log.info("shadow window ended; exiting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
