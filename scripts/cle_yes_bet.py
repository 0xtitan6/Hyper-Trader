"""Flip BAL YES → CLE YES after Lamar scratch news.

1. Flat remaining BAL YES dust (42 sh)
2. Buy $150 CLE YES (#118051) at crossing
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

# 1. Flat BAL YES dust
BAL = "#118050"
book = info.post("/info", {"type": "l2Book", "coin": BAL})
bb = float(book["levels"][0][0]["px"])
print(f"flattening 42 BAL YES @ ~{bb}")
r1 = exchange.order(BAL, False, 42.0, round(bb * 0.995, 5),
    order_type={"limit": {"tif": "Ioc"}}, reduce_only=False)
print(json.dumps(r1, indent=2))

# 2. Buy CLE YES $150
CLE = "#118051"
BUDGET = 150.0
book = info.post("/info", {"type": "l2Book", "coin": CLE})
asks = book["levels"][1]
walk_px = float(asks[0]["px"])
cum_sz = 0.0; cum_cost = 0.0
for lvl in asks:
    px = float(lvl["px"]); sz = float(lvl["sz"])
    take = min(sz, (BUDGET - cum_cost) / px)
    if take < 1: break
    cum_sz += int(take); cum_cost += int(take) * px
    walk_px = px
    if cum_cost >= BUDGET * 0.95: break

sz_total = int(cum_sz)
px_submit = round(walk_px * 1.002, 5)
print(f"\nbuying {sz_total} CLE YES @ {px_submit} (~${cum_cost:.2f})")
t0 = time.time()
r2 = exchange.order(CLE, True, float(sz_total), px_submit,
    order_type={"limit": {"tif": "Ioc"}}, reduce_only=False)
print(f"order ({time.time()-t0:.2f}s):")
print(json.dumps(r2, indent=2))
