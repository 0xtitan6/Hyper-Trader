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
from src.errors import UnknownPrecisionError
from src.hl_hip3 import register_hip3_dexes
from src.market_meta import MarketMeta


def _dex_names(info: Info) -> list[str]:
    """Names of HIP-3 builder dexes. Empty list on any failure (never fatal)."""
    try:
        dexes = info.post("/info", {"type": "perpDexs"})
    except Exception:  # noqa: BLE001
        return []
    return [d["name"] for d in (dexes or []) if isinstance(d, dict) and d.get("name")]


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
    # load() was missing here: without it `_sz_decimals` is empty and EVERY
    # coin fell back to the 4dp default, so de-risking a coin whose real
    # szDecimals is smaller (AR is 2dp, xyz:SKHY is 2dp) produced `Order has
    # invalid size` — i.e. the one lever we use to prevent a liquidation
    # silently did nothing. register_hip3_dexes is needed for the same reason
    # on the `xyz:*` surface: MarketMeta.load() only sees the original dex.
    market_meta.load()
    register_hip3_dexes(info, market_meta=market_meta)

    # current position
    #
    # HIP-3 COVERAGE (added 2026-08-15): `info.user_state()` returns ONLY the
    # base perp clearinghouse. Builder-deployed dexes (`xyz:*`) are separate
    # sub-accounts, so an `xyz:*` position was invisible here and derisk exited
    # "nothing to do" — a SILENT NO-OP on the one lever that prevents a
    # liquidation. Found 2026-08-15 with xyz:AMAT at 5.7% from liq. Same fix
    # as scripts/risk_snapshot.py: enumerate perpDexs and search each one.
    sz = 0.0
    entry = liq = unreal = None
    found_dex = None  # None => base dex
    for dex in [None, *_dex_names(info)]:
        try:
            if dex is None:
                st = info.user_state(cfg.account_address)
            else:
                st = info.post(
                    "/info",
                    {"type": "clearinghouseState", "user": cfg.account_address, "dex": dex},
                )
        except Exception:  # noqa: BLE001
            continue  # a dead dex must never block flattening on the others
        for ap_ in (st or {}).get("assetPositions", []):
            p = ap_.get("position", {})
            if p.get("coin") == args.coin:
                sz = float(p.get("szi", 0) or 0)
                entry = p.get("entryPx")
                liq = p.get("liquidationPx")
                unreal = p.get("unrealizedPnl")
                found_dex = dex
                break
        if sz != 0.0:
            break
    if sz == 0.0:
        print(f"derisk: no open position in {args.coin} — nothing to do")
        return 0

    close_sz = abs(sz) * args.fraction
    try:
        close_sz = market_meta.round_size(args.coin, close_sz)
    except UnknownPrecisionError as e:
        # Fail loud rather than guess: a wrong-precision order is rejected by
        # HL anyway, so guessing would leave the operator believing the
        # position was flattened when it wasn't.
        print(f"derisk: {e}", file=sys.stderr)
        print("derisk: HIP-3 registration incomplete — flatten manually in the UI", file=sys.stderr)
        return 5
    if close_sz <= 0:
        print(f"derisk: rounded close size is 0 for {args.coin}")
        return 0

    # `all_mids()` covers the base dex only — it has no `xyz:*` key, so even
    # with the position found above we'd have exited "bad mid". Dex-scoped
    # allMids keys by the FULL name ("xyz:AMAT"), matching args.coin.
    if found_dex is None:
        mids = info.all_mids()
    else:
        mids = info.post("/info", {"type": "allMids", "dex": found_dex}) or {}
    mid = float(mids.get(args.coin, 0) or 0)
    if mid <= 0:
        print(f"derisk: bad mid for {args.coin} (dex={found_dex or 'base'})", file=sys.stderr)
        return 3
    is_buy = sz < 0  # close a short by buying
    bps = args.slippage_bps / 10_000
    slipped = mid * (1.0 + bps) if is_buy else mid * (1.0 - bps)
    limit_px = market_meta.round_price(slipped, args.coin)

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
    # `Exchange` builds its OWN internal `Info`, which — like ours above before
    # registration — knows only the base perp dex. Registering on the module-level
    # `info` does NOT propagate here, so `exchange.order("xyz:AMAT", ...)` raised
    # `KeyError: 'xyz:AMAT'`: the third and last silent no-op in this de-risk path
    # (found 2026-08-15 with xyz:AMAT at 5.7% from liq, minutes after the
    # position-lookup and allMids fixes above). src/main.py:121 does exactly this
    # for the live engine's exchange; the operator's lever needs it too.
    register_hip3_dexes(exchange.info, market_meta=market_meta)
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
