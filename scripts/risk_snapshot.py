#!/usr/bin/env python
"""Compact live risk snapshot for the autonomous operator.

Prints account totals and, per open perp position, the distance-to-liquidation
buffer and a recommended action tier. Read-only (no orders). The operator parses
LIQ_BUFFER lines to decide whether to flatten (via scripts.derisk).

Action tiers (per position, by liq buffer = |mark-liqPx|/mark):
  CRITICAL  buffer < 6%   -> operator should flatten this coin (reduce_only IOC)
  WARN      6% <= buffer < 10% -> operator should escalate (message), not auto-flatten
  OK        buffer >= 10%

HIP-3 COVERAGE (added 2026-08-15): `info.user_state()` returns ONLY the base perp
clearinghouse. Builder-deployed dexes (`xyz:*` et al) live in separate sub-accounts
and were entirely invisible here — on 2026-08-15 that hid 8 open xyz positions worth
$167.90 notional while this script printed `WORST_TIER OK`. We now enumerate
`perpDexs` and pull each dex's own clearinghouseState + marks.

CROSS-MARGIN CAVEAT: per-position `liquidationPx` assumes every OTHER position in
that sub-account stays put, so a small position can show a scary buffer while the
sub-account is nowhere near liquidation. Cross liquidation actually triggers on
accountValue vs crossMaintenanceMarginUsed, so we print ACCOUNT_HEALTH per dex.
Trust ACCOUNT_HEALTH over a lone CRITICAL LIQ_BUFFER on a cross book.
"""
from __future__ import annotations

import json

from hyperliquid.info import Info

from src.config import load_config

CRIT = 0.06
WARN = 0.10


def _tier(buf: float) -> str:
    return "CRITICAL" if buf < CRIT else "WARN" if buf < WARN else "OK"


def _worse(a: str, b: str) -> str:
    order = {"OK": 0, "WARN": 1, "CRITICAL": 2}
    return a if order[a] >= order[b] else b


def _dex_names(info: Info) -> list[str]:
    """Names of HIP-3 builder dexes. Empty list on any failure (never fatal)."""
    try:
        dexes = info.post("/info", {"type": "perpDexs"})
    except Exception:  # noqa: BLE001
        return []
    names = []
    for d in dexes or []:
        if isinstance(d, dict) and d.get("name"):
            names.append(d["name"])
    return names


def _dex_marks(info: Info, dex: str) -> dict[str, float]:
    """markPx per coin for one dex. `all_mids()` only covers the base dex."""
    try:
        meta, ctxs = info.post("/info", {"type": "metaAndAssetCtxs", "dex": dex})
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for u, c in zip(meta.get("universe", []), ctxs):
        px = c.get("markPx")
        if px:
            out[u["name"]] = float(px)
    return out


def _report_positions(assets: list, marks: dict[str, float], worst: str) -> tuple[str, float]:
    """Print LIQ_BUFFER lines for one clearinghouse. Returns (worst_tier, gross_notional)."""
    gross = 0.0
    for ap in assets:
        p = ap.get("position", {})
        coin = p.get("coin")
        szi = float(p.get("szi", 0) or 0)
        if szi == 0:
            continue
        liq = p.get("liquidationPx")
        unreal = float(p.get("unrealizedPnl", 0) or 0)
        # xyz positions are keyed "xyz:AMAT" in state but "AMAT" in that dex's meta.
        mark = float(marks.get(coin) or marks.get(coin.split(":")[-1], 0) or 0)
        gross += abs(szi) * mark
        if liq and mark:
            buf = abs(mark - float(liq)) / mark
            tier = _tier(buf)
            buf_s = f"{buf*100:.1f}%"
        else:
            # No liqPx (fully collateralised) or no mark. Missing mark is a data
            # gap, not safety — say so instead of silently scoring it OK.
            tier = "OK" if liq is None else "UNKNOWN"
            buf_s = "n/a" if liq is None else "NO_MARK"
        if tier in ("CRITICAL", "WARN"):
            worst = _worse(worst, tier)
        print(
            f"LIQ_BUFFER coin={coin} tier={tier} buffer={buf_s} "
            f"szi={szi:+.4f} mark={mark:.6f} liqPx={liq} unreal=${unreal:.2f}"
        )
    return worst, gross


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
    base_marks = {c: float(v) for c, v in mids.items() if v}
    worst, gross = _report_positions(us.get("assetPositions", []), base_marks, worst)
    print(f"ACCOUNT_HEALTH dex=base equity=${perp:.2f} maintMargin=${maint:.2f} "
          f"coverage={(perp/maint if maint else float('inf')):.1f}x grossNotional=${gross:.2f}")

    # --- HIP-3 builder dexes (separate sub-accounts; invisible to user_state) ---
    total_gross = gross
    for dex in _dex_names(info):
        try:
            st = info.post("/info", {"type": "clearinghouseState", "user": addr, "dex": dex})
        except Exception as exc:  # noqa: BLE001
            print(f"DEX_ERROR dex={dex} {type(exc).__name__}: {exc}")
            worst = _worse(worst, "WARN")
            continue
        assets = [a for a in st.get("assetPositions", []) if float(a.get("position", {}).get("szi", 0) or 0)]
        if not assets:
            continue
        d_equity = float(st.get("marginSummary", {}).get("accountValue", 0) or 0)
        d_maint = float(st.get("crossMaintenanceMarginUsed", 0) or 0)
        worst, d_gross = _report_positions(assets, _dex_marks(info, dex), worst)
        total_gross += d_gross
        print(f"ACCOUNT_HEALTH dex={dex} equity=${d_equity:.2f} maintMargin=${d_maint:.2f} "
              f"coverage={(d_equity/d_maint if d_maint else float('inf')):.1f}x grossNotional=${d_gross:.2f}")

    print(f"GROSS_NOTIONAL_ALL_DEXES ${total_gross:.2f}")
    print(f"WORST_TIER {worst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
