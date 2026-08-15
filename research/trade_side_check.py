"""HL trade-side accuracy check (Lee-Ready style).

Paper #4 (Polymarket) found the public trade-direction feed agrees with truth
only ~59% of the time -> flow-imbalance/VPIN computed from it is noise. This
tests whether HL's outcome-market trade `side` is reliable: subscribe to L2 book
+ trades together, and for each trade classify by PRICE (executed at ask = buy
taker, at bid = sell taker) and compare to the feed's `side` label.

Verdict: agreement near 100% OR near 0% => side is reliable (just a convention);
agreement near 50% => side is NOISE and the flow thesis is dead for us.
"""
import json
import sys
import time
from collections import defaultdict

REPO = "/home/ec2-user/.openclaw/workspace/hyper-trader"
sys.path.insert(0, REPO)
from dotenv import load_dotenv
load_dotenv(f"{REPO}/.env")
from hyperliquid.info import Info
from hyperliquid.utils import constants
from src.hl_outcome import encode_outcome_coin_name, register_outcome_assets

best = {}          # coin -> (bid, ask)
tally = defaultdict(int)  # keys: matchB_ask, matchB_bid, matchA_ask, matchA_bid, mid, nobook


def on_book(msg):
    try:
        d = msg.get("data", {})
        coin = d.get("coin"); lv = d.get("levels")
        if coin and lv and lv[0] and lv[1]:
            best[coin] = (float(lv[0][0]["px"]), float(lv[1][0]["px"]))
    except Exception:
        pass


def on_trades(msg):
    try:
        d = msg.get("data")
        trades = d if isinstance(d, list) else []
        for t in trades:
            coin = t.get("coin"); px = float(t.get("px")); side = t.get("side")
            bb_ba = best.get(coin)
            if not bb_ba:
                tally["nobook"] += 1; continue
            bb, ba = bb_ba
            if px >= ba - 1e-9:
                loc = "ask"      # executed at/above ask -> taker BOUGHT
            elif px <= bb + 1e-9:
                loc = "bid"      # executed at/below bid -> taker SOLD
            else:
                tally["mid"] += 1; continue
            tally[f"{side}_{loc}"] += 1
    except Exception:
        pass


def main():
    info = Info(constants.MAINNET_API_URL, skip_ws=False)
    register_outcome_assets(info)
    # pick active makeable markets
    resp = info.post("/info", {"type": "outcomeMeta"}) or {}
    coins = []
    for o in resp.get("outcomes", []):
        oid = o.get("outcome")
        if not isinstance(oid, int):
            continue
        for s in range(2):
            coins.append(encode_outcome_coin_name(oid, s))
    # subscribe to a broad set so we catch trades
    for c in coins[:40]:
        info.subscribe({"type": "l2Book", "coin": c}, on_book)
        info.subscribe({"type": "trades", "coin": c}, on_trades)
    time.sleep(150)
    # analyze: is "side" price-consistent?
    b_ask = tally["B_ask"]; b_bid = tally["B_bid"]
    a_ask = tally["A_ask"]; a_bid = tally["A_bid"]
    classifiable = b_ask + b_bid + a_ask + a_bid
    print(json.dumps({
        "classifiable_trades": classifiable, "at_mid": tally["mid"], "no_book": tally["nobook"],
        "B_at_ask": b_ask, "B_at_bid": b_bid, "A_at_ask": a_ask, "A_at_bid": a_bid,
    }))
    if classifiable >= 20:
        # if side B == buy(ask) and A == sell(bid): consistent = B_ask + A_bid
        consistent = b_ask + a_bid
        frac = consistent / classifiable
        print(f"consistency(B=buy/A=sell): {frac:.1%}  (near 100% or 0% = RELIABLE; near 50% = NOISE)")
    else:
        print("too few classifiable trades in window — rerun longer or on busier markets")


if __name__ == "__main__":
    main()
