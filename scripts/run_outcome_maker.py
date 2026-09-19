#!/usr/bin/env python3
"""Live runner for the HIP-4 outcome maker, aimed at Outcome's LP rewards.

Why this exists: `src/maker.py` was built, tested and never switched on. The
Outcome/Monarch rewards programme pays for two-sided in-band quoting, and the
reward — not the spread — is the edge. The programme scores ONLY orders carrying
Outcome's builder code, so BUILDER is mandatory here.

Deliberately narrow: ONE leg, post-only, hard inventory cap, bounded runtime.

    ./scripts/run_outcome_maker.py --coin '#38830' --minutes 45 --execute
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

import eth_account
import requests
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

from src.hl_outcome import register_outcome_assets
from src.journal import Journal
from src.maker import MakerConfig, OutcomeMaker
from src.market_meta import MarketMeta

BUILDER = "0xab5dbc057628bc18523c4cdfc0e1e2ebdbecb704"
MASTER = "0xE503186067b1B0Fb973c063054B14c4625434A1a"
ENV = "/home/ec2-user/.config/hyper-trader/copytrader.env"
INFO = "https://api.hyperliquid.xyz/info"


def _post(body: dict, tries: int = 8):
    """Our own research agents can saturate the API — back off rather than die."""
    for k in range(tries):
        r = requests.post(INFO, json=body, timeout=25)
        if r.status_code == 200:
            return r.json()
        time.sleep(2.0 * (k + 1))
    raise RuntimeError("rate limited")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--coin", required=True, help="outcome leg, e.g. '#38830'")
    ap.add_argument("--minutes", type=float, default=45.0)
    ap.add_argument("--usd-per-side", type=float, default=50.0,
                    help="programme needs >=$50 bid+ask in-band to score at all")
    ap.add_argument("--max-inventory-usd", type=float, default=60.0)
    ap.add_argument("--execute", action="store_true", help="default is dry-run")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

    book = _post({"type": "l2Book", "coin": args.coin})
    lv = book.get("levels") or []
    if len(lv) < 2 or not lv[0] or not lv[1]:
        print(f"{args.coin}: no two-sided book — refusing to quote")
        return 2
    mid = (float(lv[0][0]["px"]) + float(lv[1][0]["px"])) / 2
    shares = round(args.usd_per_side / mid, 2)
    print(f"{args.coin}: mid={mid:.4f} -> {shares} shares/side (~${args.usd_per_side:.0f})")

    meta = _post({"type": "meta"})
    spot = _post({"type": "spotMeta"})
    key = open(ENV).read().split("HL_PRIVATE_KEY=")[1].split("\n")[0].strip()
    wallet = eth_account.Account.from_key(key)
    ex = Exchange(wallet, constants.MAINNET_API_URL, meta=meta, spot_meta=spot,
                  account_address=MASTER)
    info = Info(constants.MAINNET_API_URL, skip_ws=True, meta=meta, spot_meta=spot)
    for target in (info, ex.info):
        register_outcome_assets(target)

    cfg = MakerConfig(
        coin=args.coin,
        expiry_ts=int(time.time() + args.minutes * 60),
        quote_size_shares=shares,
        # Rewards pay for being NEAR MID, not for a wide spread. The 30bp default
        # floor exists to protect spread-capture EV and would refuse to quote these
        # books at all (measured medians ~2bp), so it is deliberately relaxed —
        # the close fee is ~0.75bp and the reward is what we are here for.
        min_spread_bps=0.0,
        quote_offset_ticks=0,
        max_position_shares=round(args.max_inventory_usd / mid, 2),
        max_inventory_usd=args.max_inventory_usd,
        expiry_buffer_s=30,
        builder_address=BUILDER,
        builder_fee_tenths_bp=0,
    )
    maker = OutcomeMaker(info=info, exchange=ex, market_meta=MarketMeta(info),
                         journal=Journal("state/journal.jsonl"), config=cfg,
                         dry_run=not args.execute)
    maker.run()
    print("done — all quotes cancelled on exit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
