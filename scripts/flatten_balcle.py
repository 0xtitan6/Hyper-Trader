"""Emergency flatten of oversize BAL/CLE YES bag.

HB maker had a position-tracking bug; built up to 1642 shares vs $50 cap.
Dumping ~1600 shares as crossing taker to get back to intended exposure.
"""
from __future__ import annotations
import json, math, sys, time
sys.path.insert(0, "/home/ec2-user/.openclaw/workspace/hyper-trader")

from src.config import load_config
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from eth_account import Account
from src.hl_outcome import register_outcome_assets

cfg = load_config()
wallet = Account.from_key(cfg.private_key)
info = Info(cfg.hyperliquid_api_url, skip_ws=True)
register_outcome_assets(info)
exchange = Exchange(wallet, cfg.hyperliquid_api_url, account_address=cfg.account_address)
register_outcome_assets(exchange.info)

COIN = "#118050"
SZ_TO_SELL = 1600  # leave ~42 shares @ $0.62 = ~$26 inventory, close to intended $50

book = info.post("/info", {"type": "l2Book", "coin": COIN})
bids = book.get("levels", [[], []])[0]
if not bids:
    print("no bids"); sys.exit(2)

# Walk the bid ladder, cross a tick below the 5th level to guarantee fill
walk_px = float(bids[0]["px"])
cum = 0.0
for lvl in bids[:5]:
    cum += float(lvl["sz"])
    walk_px = float(lvl["px"])
    if cum >= SZ_TO_SELL:
        break
px_submit = round(walk_px * 0.998, 5)  # 20bp below worst level
print(f"placing: SELL {SZ_TO_SELL} @ {px_submit} crossing")

t0 = time.time()
result = exchange.order(
    COIN, False, float(SZ_TO_SELL), px_submit,
    order_type={"limit": {"tif": "Ioc"}}, reduce_only=False,
)
print(f"order result ({time.time()-t0:.2f}s):")
print(json.dumps(result, indent=2))
