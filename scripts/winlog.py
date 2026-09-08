#!/usr/bin/env python
"""Append-only mission log: account value, session PnL, and progress to $1,000.

Neil set the mission on 2026-08-14: $200 -> $1,000 by 2026-08-31, and asked for
"consistent logs on our wins". This writes ONE line per run to state/wins.log so
we have an honest, tamper-free time series of what the account actually did —
not a projection, not a backtest. Read-only against HL (never places orders).

Deliberately separate from the engine: its own file, no shared state, so a bug
here can never take the trading bot down. Safe to run from cron.

Usage:
    .venv/bin/python scripts/winlog.py            # append a datapoint
    .venv/bin/python scripts/winlog.py --report   # print the whole run so far
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from hyperliquid.info import Info

from src.config import load_config

LOG = Path("state/wins.log")
MISSION_TARGET = 1000.0
MISSION_DEADLINE = "2026-08-31"


def account_total(info: Info, addr: str) -> tuple[float, float, float]:
    """Return (total, perp_equity, unrealized). Mirrors risk_snapshot's convention:
    on HL unified margin spot USDC is already cross-collateral inside the perp
    accountValue, so we use HL's own account-value history as canonical TOTAL."""
    us = info.user_state(addr)
    perp = float(us["marginSummary"]["accountValue"])
    unreal = sum(
        float(p["position"].get("unrealizedPnl", 0) or 0) for p in us.get("assetPositions", [])
    )
    spot = info.spot_user_state(addr.lower())
    total = next(
        (float(b["total"]) for b in spot.get("balances", []) if b["coin"] == "USDC"), 0.0
    )
    try:
        for window, data in info.portfolio(addr):
            if window == "day":
                hist = data.get("accountValueHistory", [])
                if hist:
                    total = float(hist[-1][1])
                break
    except Exception:  # noqa: BLE001 — never let a stats call break the log
        pass
    return total, perp, unreal


def read_log() -> list[dict]:
    if not LOG.exists():
        return []
    out = []
    for line in LOG.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="Print the run so far and exit")
    args = ap.parse_args()

    history = read_log()

    if args.report:
        if not history:
            print("no datapoints yet")
            return 0
        first, last = history[0], history[-1]
        span_h = (last["ts"] - first["ts"]) / 3600.0
        pnl = last["total"] - first["total"]
        print(f"MISSION ${MISSION_TARGET:.0f} by {MISSION_DEADLINE}")
        print(f"  start   ${first['total']:.2f}  ({first['utc']})")
        print(f"  now     ${last['total']:.2f}  ({last['utc']})")
        print(f"  change  ${pnl:+.2f} over {span_h:.1f}h  across {len(history)} datapoints")
        print(f"  to go   ${MISSION_TARGET - last['total']:.2f}")
        wins = [h for h in history if h.get("delta", 0) > 0]
        losses = [h for h in history if h.get("delta", 0) < 0]
        print(f"  ticks   {len(wins)} up / {len(losses)} down")
        if wins:
            best = max(wins, key=lambda h: h["delta"])
            print(f"  best    ${best['delta']:+.2f} at {best['utc']}")
        if losses:
            worst = min(losses, key=lambda h: h["delta"])
            print(f"  worst   ${worst['delta']:+.2f} at {worst['utc']}")
        return 0

    cfg = load_config("config.yaml")
    info = Info(cfg.hyperliquid_api_url, skip_ws=True)
    total, perp, unreal = account_total(info, cfg.account_address)

    prev = history[-1]["total"] if history else total
    row = {
        "ts": time.time(),
        "utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "total": round(total, 2),
        "perp_equity": round(perp, 2),
        "unrealized": round(unreal, 2),
        "delta": round(total - prev, 2),
        "to_target": round(MISSION_TARGET - total, 2),
    }
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps(row) + "\n")
    print(
        f"{row['utc']}  TOTAL ${row['total']:.2f}  "
        f"delta ${row['delta']:+.2f}  unreal ${row['unrealized']:+.2f}  "
        f"to ${MISSION_TARGET:.0f}: ${row['to_target']:.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
