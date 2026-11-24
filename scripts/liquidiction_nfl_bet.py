"""One-shot NFL bet on HL HIP-4 outcome market (the Liquidiction/outcome.xyz sports book).

Context: Liquidiction's sports product is NOT a separate parimutuel pool — it's a
curated frontend over Hyperliquid HIP-4 outcome markets, which ARE live tradable
orderbooks (verified 2026-10-11). liquidiction.com does not exist; liquidiction.xyz
is their HL trading UI; outcome.xyz is behind Cloudflare so we hit HL's API directly
with the hyperliquid-python-sdk.

Edge check (consensus = Kalshi mid): all 13 Sunday games priced within 1% of
Kalshi, well under the 3% gate. No edge play tonight.

Fallback per task: place a $5 "least-edge-against-us" TEST bet to prove the
integration end-to-end. SEA@SF (outcome 8554) side 0 (SEA Yes) had edge ~0 against
Kalshi mid; we take it as a buy-at-ask IOC.

Budget: $5 of USDC max. Single order. No retries if rejected.
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

# Target: outcome 8554 side 0 (SEA Yes @ SEA@SF). shortNameA=SEA.
OUTCOME_ID = 8554
SIDE = 0
COIN = f"#{10 * OUTCOME_ID + SIDE}"  # "#85540"
BUDGET_USD = 5.0

# Live snapshot
book = info.post("/info", {"type": "l2Book", "coin": COIN})
bids, asks = book.get("levels", [[], []])
best_bid = float(bids[0]["px"]) if bids else None
best_ask = float(asks[0]["px"]) if asks else None
print(f"book {COIN}: bid={best_bid} ask={best_ask}")
if not best_ask or best_ask <= 0:
    print("no ask liquidity — abort"); sys.exit(2)

# Shares to buy with ~$5 budget. HIP-4 share size is in integer contracts.
# We'll pay best_ask * sz. Round DOWN to stay under budget.
import math
raw_sz = BUDGET_USD / best_ask
sz = max(1, math.floor(raw_sz))
cost = sz * best_ask
if cost > BUDGET_USD + 0.5:
    print(f"min-size {sz} costs ${cost:.2f} > budget ${BUDGET_USD} — abort"); sys.exit(3)

# Place IOC limit at best ask (= market buy, but bounded)
# Use crossing limit 1 tick above ask to guarantee fill.
# tick size for outcomes is 1e-5 typically; use best_ask directly.
px = best_ask
print(f"placing: buy {sz} @ {px} = ~${cost:.2f} USDC on {COIN} (SEA Yes, test bet, no edge)")

t0 = time.time()
try:
    result = exchange.order(
        COIN,
        True,              # is_buy
        float(sz),
        px,
        order_type={"limit": {"tif": "Ioc"}},  # immediate-or-cancel = taker
        reduce_only=False,
    )
    print(f"order result ({time.time()-t0:.2f}s):")
    print(json.dumps(result, indent=2))
except Exception as e:
    print(f"ORDER FAILED: {e!r}")
    sys.exit(4)

# Verify via clearinghouseState: a new asset position in #85540
time.sleep(2)
ch = info.post("/info", {"type": "clearinghouseState", "user": cfg.account_address})
positions = ch.get("assetPositions", [])
hit = [p for p in positions if p.get("position",{}).get("coin") == COIN]
if hit:
    print(f"VERIFIED position: {hit[0]['position']}")
else:
    print(f"no {COIN} position in clearinghouseState — may be unfilled or on different leg")
    # Check userFills instead
    fills = info.post("/info", {"type":"userFillsByTime","user":cfg.account_address,"startTime":int(t0*1000)-5000})
    coin_fills = [f for f in (fills or []) if f.get("coin") == COIN]
    print(f"recent fills on {COIN}: {len(coin_fills)}")
    for f in coin_fills:
        print(" ", f)
