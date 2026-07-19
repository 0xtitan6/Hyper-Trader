#!/usr/bin/env python
"""Compact live risk snapshot for the autonomous operator.

Prints account totals and, per open perp position, the distance-to-liquidation
buffer and a recommended action tier. Read-only (no orders). The operator parses
LIQ_BUFFER lines to decide whether to flatten (via scripts.derisk).

Action tiers (per position, by liq buffer = |mark-liqPx|/mark):
  CRITICAL  buffer < 6%   -> operator should flatten this coin (reduce_only IOC)
  WARN      6% <= buffer < 10% -> operator should escalate (message), not auto-flatten
  OK        buffer >= 10%
"""
from __future__ import annotations

import json

from hyperliquid.info import Info

from src.config import load_config

CRIT = 0.06
WARN = 0.10


def main() -> int:
    cfg = load_config("config.yaml")
    info = Info(cfg.hyperliquid_api_url, skip_ws=True)
    addr = cfg.account_address
    us = info.user_state(addr)
    spot = info.spot_user_state(addr.lower())
    mids = info.all_mids()

    spot_usdc = next((float(b["total"]) for b in spot.get("balances", []) if b["coin"] == "USDC"), 0.0)
    perp = float(us["marginSummary"]["accountValue"])
    maint = float(us.get("crossMaintenanceMarginUsed", 0) or 0)
    # NOTE: on HL unified margin, spot USDC is cross-collateral already reflected in the
    # perp accountValue, so perp+spot DOUBLE-COUNTS. Use HL's authoritative account-value
    # history as the canonical TOTAL (matches the HL UI); fall back to spot if unavailable.
    total = spot_usdc
    try:
        pf = info.portfolio(addr)
        for window, data in pf:
            if window == "day":
                hist = data.get("accountValueHistory", [])
                if hist:
                    total = float(hist[-1][1])
                break
    except Exception:  # noqa: BLE001
        pass
    print(f"TOTAL ${total:.2f}  (perp equity ${perp:.2f}, spot USDC ${spot_usdc:.2f}; unified-margin, not additive)  maintMargin ${maint:.2f}")

    worst = "OK"
    for ap in us.get("assetPositions", []):
        p = ap.get("position", {})
        coin = p.get("coin")
        szi = float(p.get("szi", 0) or 0)
        if szi == 0:
            continue
        liq = p.get("liquidationPx")
        unreal = float(p.get("unrealizedPnl", 0) or 0)
        mark = float(mids.get(coin, 0) or 0)
        buf = abs(mark - float(liq)) / mark if (liq and mark) else 1.0
        tier = "CRITICAL" if buf < CRIT else "WARN" if buf < WARN else "OK"
        if tier == "CRITICAL":
            worst = "CRITICAL"
        elif tier == "WARN" and worst != "CRITICAL":
            worst = "WARN"
        print(
            f"LIQ_BUFFER coin={coin} tier={tier} buffer={buf*100:.1f}% "
            f"szi={szi:+.4f} mark={mark:.6f} liqPx={liq} unreal=${unreal:.2f}"
        )
    print(f"WORST_TIER {worst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
