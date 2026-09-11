"""Dense book-snapshot collector for the maker-improving ML model.

Every ~30s, snapshots the top makeable outcome markets' order books and logs
microstructure features. From consecutive snapshots we derive:
  features (at time t): queue-imbalance, spread, mid-momentum, realized vol
  label   (t -> t+k):   forward mid move (did it go against a maker quote?)

Read-only (REST l2Book), no orders. Runs detached for a week, then self-expires.
Output: research/ml_market_snapshots.jsonl  (one line per market per tick)
"""
import json
import sys
import time
from datetime import datetime, timezone

REPO = "/home/ec2-user/.openclaw/workspace/hyper-trader"
sys.path.insert(0, REPO)
from dotenv import load_dotenv
load_dotenv(f"{REPO}/.env")
from hyperliquid.info import Info
from hyperliquid.utils import constants
from src.hl_outcome import encode_outcome_coin_name, register_outcome_assets

OUT = f"{REPO}/research/ml_market_snapshots.jsonl"
WEEK_END = datetime(2026, 7, 14, 1, 0, tzinfo=timezone.utc)
INTERVAL_S = 30
REFRESH_MARKETS_EVERY = 40  # re-pick target markets every ~20 min


def makeable(info, top=12):  # widened 6->12 to cover the full tape set (better replay match-rate)
    resp = info.post("/info", {"type": "outcomeMeta"}) or {}
    out = []
    for o in resp.get("outcomes", []):
        oid = o.get("outcome")
        if not isinstance(oid, int):
            continue
        for side in range(2):
            coin = encode_outcome_coin_name(oid, side)
            try:
                bk = info.post("/info", {"type": "l2Book", "coin": coin}) or {}
                lv = bk.get("levels") or [[], []]
                b, a = lv[0], lv[1]
                if not b or not a:
                    continue
                bb, ba = float(b[0]["px"]), float(a[0]["px"])
                mid = (bb + ba) / 2
                if not (0.08 <= mid <= 0.92):
                    continue
                sp = (ba - bb) / mid * 10000
                dep = sum(float(x["sz"]) for x in b[:5]) + sum(float(x["sz"]) for x in a[:5])
                if sp >= 25 and dep > 40:
                    out.append((sp * (dep ** 0.5), coin))
            except Exception:
                pass
    out.sort(reverse=True)
    return [c for _, c in out[:top]]


def snap(info, coin):
    bk = info.post("/info", {"type": "l2Book", "coin": coin}) or {}
    lv = bk.get("levels") or [[], []]
    b, a = lv[0], lv[1]
    if not b or not a:
        return None
    bb, ba = float(b[0]["px"]), float(a[0]["px"])
    bd = sum(float(x["sz"]) for x in b[:5])
    ad = sum(float(x["sz"]) for x in a[:5])
    mid = (bb + ba) / 2
    qi = (bd - ad) / (bd + ad) if (bd + ad) else 0.0
    return {"coin": coin, "mid": round(mid, 5), "spread_bps": round((ba - bb) / mid * 10000, 1),
            "qi": round(qi, 4), "bid_depth": round(bd, 1), "ask_depth": round(ad, 1),
            "best_bid": bb, "best_ask": ba}


def main():
    info = Info(constants.MAINNET_API_URL, skip_ws=True)
    coins = makeable(info)
    i = 0
    while datetime.now(timezone.utc) <= WEEK_END:
        if i % REFRESH_MARKETS_EVERY == 0:
            try:
                nc = makeable(info)
                if nc:
                    coins = nc
            except Exception:
                pass
        ts = datetime.now(timezone.utc).isoformat()
        with open(OUT, "a") as f:
            for c in coins:
                try:
                    s = snap(info, c)
                    if s:
                        s["ts"] = ts
                        f.write(json.dumps(s) + "\n")
                except Exception:
                    pass
        i += 1
        time.sleep(INTERVAL_S)


if __name__ == "__main__":
    main()
