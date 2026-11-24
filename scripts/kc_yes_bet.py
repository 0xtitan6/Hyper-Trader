"""Directional bet: $150 on KC YES to beat LAC (Sunday Oct 18).

Outcome 11459 side 0 = KC(A) YES. Book coin #114590. HL mid ~0.779.
If KC wins: +$42 profit. If KC loses: -$150 total loss.

Sized within <$200 autonomy scope. Taker IOC.
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

OUTCOME_ID = 11459
SIDE = 0  # YES
COIN = f"#{10 * OUTCOME_ID + SIDE}"  # #114590
BUDGET_USD = 150.0

book = info.post("/info", {"type": "l2Book", "coin": COIN})
bids, asks = book.get("levels", [[], []])
best_bid = float(bids[0]["px"]) if bids else None
best_ask = float(asks[0]["px"]) if asks else None
print(f"book {COIN}: bid={best_bid} ask={best_ask}")
if not best_ask:
    print("no ask liquidity — abort"); sys.exit(2)

# Walk the ask ladder up to budget. Place one aggressive IOC at a crossing px
# that covers 2-3 levels. Use px = top of level 3 or 1.5% above best_ask.
walk_px = best_ask
cum_sz = 0.0
cum_cost = 0.0
for lvl in asks:
    px = float(lvl["px"])
    sz = float(lvl["sz"])
    take = min(sz, (BUDGET_USD - cum_cost) / px)
    if take < 1:
        break
    cum_sz += int(take)
    cum_cost += int(take) * px
    walk_px = px
    if cum_cost >= BUDGET_USD * 0.95:
        break

sz_total = int(cum_sz)
if sz_total < 1:
    print("budget too small for 1 share"); sys.exit(3)

# Cross a tick above walk_px to guarantee fill
px_submit = round(walk_px * 1.002, 5)
print(f"placing: buy {sz_total} @ {px_submit} crossing (would fill ~${cum_cost:.2f})")

t0 = time.time()
try:
    result = exchange.order(
        COIN, True, float(sz_total), px_submit,
        order_type={"limit": {"tif": "Ioc"}},
        reduce_only=False,
    )
    print(f"order result ({time.time()-t0:.2f}s):")
    print(json.dumps(result, indent=2))
except Exception as e:
    print(f"ORDER FAILED: {e!r}"); sys.exit(4)

time.sleep(2)
ch = info.post("/info", {"type": "clearinghouseState", "user": cfg.account_address})
positions = ch.get("assetPositions", [])
hit = [p for p in positions if p.get("position",{}).get("coin") == COIN]
if hit:
    print(f"VERIFIED position: {hit[0]['position']}")
else:
    fills = info.post("/info", {"type":"userFillsByTime","user":cfg.account_address,"startTime":int(t0*1000)-5000})
    coin_fills = [f for f in (fills or []) if f.get("coin") == COIN]
    print(f"recent fills on {COIN}: {len(coin_fills)}")
    for f in coin_fills: print(" ", f)
