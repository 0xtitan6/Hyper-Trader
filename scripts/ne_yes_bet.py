"""Directional bet: $150 on NE YES to beat NYJ (Sunday Oct 18).

Outcome 11454 side 0 = NE(A) YES. Book coin #114540. HL mid ~0.755.
Win: +$48. Lose: -$150.
"""
from __future__ import annotations
import json, sys, time
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

COIN = "#114540"
BUDGET_USD = 150.0

book = info.post("/info", {"type": "l2Book", "coin": COIN})
bids, asks = book.get("levels", [[], []])
best_bid = float(bids[0]["px"]) if bids else None
best_ask = float(asks[0]["px"]) if asks else None
print(f"book {COIN}: bid={best_bid} ask={best_ask}")
if not best_ask:
    sys.exit(2)

walk_px = best_ask
cum_sz = 0.0
cum_cost = 0.0
for lvl in asks:
    px = float(lvl["px"]); sz = float(lvl["sz"])
    take = min(sz, (BUDGET_USD - cum_cost) / px)
    if take < 1: break
    cum_sz += int(take)
    cum_cost += int(take) * px
    walk_px = px
    if cum_cost >= BUDGET_USD * 0.95: break

sz_total = int(cum_sz)
if sz_total < 1: sys.exit(3)
px_submit = round(walk_px * 1.002, 5)
print(f"placing: buy {sz_total} @ {px_submit} crossing (~\${cum_cost:.2f})")

t0 = time.time()
result = exchange.order(
    COIN, True, float(sz_total), px_submit,
    order_type={"limit": {"tif": "Ioc"}}, reduce_only=False,
)
print(f"order result ({time.time()-t0:.2f}s):")
print(json.dumps(result, indent=2))

time.sleep(2)
ch = info.post("/info", {"type": "clearinghouseState", "user": cfg.account_address})
hit = [p for p in ch.get("assetPositions", []) if p.get("position",{}).get("coin") == COIN]
if hit: print(f"VERIFIED position: {hit[0]['position']}")
