#!/usr/bin/env python
"""Standalone de-risk / flatten helper for the autonomous operator.

Flattens a single perp position with a reduce_only IOC order, reusing the exact
construction the live bot uses (src.config / Exchange / MarketMeta). This is the
one lever the operator uses to PREVENT a liquidation — it is deliberately narrow:
one coin, reduce_only (can never open or flip a position), IOC (no resting order).

SAFETY:
  - Default is --dry-run: prints the intended order, submits NOTHING.
  - --execute is required to actually place the reduce_only IOC.
  - reduce_only=True means the exchange rejects anything that would increase/flip.
  - Refuses if there is no open position in `coin`.

Usage:
  python -m scripts.derisk --coin AR            # dry-run (default), shows the order
  python -m scripts.derisk --coin AR --execute  # actually flatten AR
  python -m scripts.derisk --coin AR --fraction 0.5 --execute   # flatten half
"""
from __future__ import annotations

import argparse
import sys

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info

from src.config import load_config
from src.market_meta import MarketMeta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--coin", required=True, help="perp coin to flatten, e.g. AR")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--fraction", type=float, default=1.0, help="fraction of the position to close (0<f<=1)")
    ap.add_argument("--slippage-bps", type=float, default=60.0, help="cross-the-book slippage for the IOC")
    ap.add_argument("--execute", action="store_true", help="actually submit (default: dry-run)")
    args = ap.parse_args(argv)

    if not (0.0 < args.fraction <= 1.0):
        print(f"derisk: bad --fraction {args.fraction}", file=sys.stderr)
        return 2

    cfg = load_config(args.config)
    info = Info(cfg.hyperliquid_api_url, skip_ws=True)
    market_meta = MarketMeta(info)

    # current position
    us = info.user_state(cfg.account_address)
    sz = 0.0
    entry = None
    for ap_ in us.get("assetPositions", []):
        p = ap_.get("position", {})
        if p.get("coin") == args.coin:
            sz = float(p.get("szi", 0) or 0)
            entry = p.get("entryPx")
            liq = p.get("liquidationPx")
            unreal = p.get("unrealizedPnl")
            break
    if sz == 0.0:
        print(f"derisk: no open position in {args.coin} — nothing to do")
        return 0

    close_sz = abs(sz) * args.fraction
    close_sz = market_meta.round_size(args.coin, close_sz)
    if close_sz <= 0:
        print(f"derisk: rounded close size is 0 for {args.coin}")
        return 0

    mid = float(info.all_mids().get(args.coin, 0) or 0)
    if mid <= 0:
        print(f"derisk: bad mid for {args.coin}", file=sys.stderr)
        return 3
    is_buy = sz < 0  # close a short by buying
    bps = args.slippage_bps / 10_000
    slipped = mid * (1.0 + bps) if is_buy else mid * (1.0 - bps)
    limit_px = market_meta.round_price(slipped)

    action = "BUY" if is_buy else "SELL"
    print(
        f"derisk {args.coin}: pos szi={sz:+.4f} entry={entry} liqPx={liq} unreal={unreal}\n"
        f"  -> reduce_only IOC {action} sz={close_sz} @ limit {limit_px} (mid {mid:.6f}, slip {args.slippage_bps}bps, frac {args.fraction})"
    )

    if not args.execute:
        print("  DRY-RUN — no order submitted. Re-run with --execute to flatten.")
        return 0

    wallet = Account.from_key(cfg.private_key)
    exchange = Exchange(wallet, cfg.hyperliquid_api_url, account_address=cfg.account_address)
    try:
        result = exchange.order(
            args.coin, is_buy, close_sz, limit_px,
            order_type={"limit": {"tif": "Ioc"}}, reduce_only=True,
        )
        print(f"  SUBMITTED reduce_only IOC: {result}")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"  ERROR submitting reduce_only IOC for {args.coin}: {e}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
