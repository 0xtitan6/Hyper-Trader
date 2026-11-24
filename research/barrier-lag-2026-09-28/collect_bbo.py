"""BBO-feed collector: sample bid/ask on BTC perp + priceTouch barriers.

BBO fires on every touch change (much faster than l2Book snapshots)."""
import json, time, sys
from hyperliquid.info import Info
from hyperliquid.utils import constants
from src.hl_outcome import register_outcome_assets

OUT = "research/barrier-lag-2026-09-28/bbo.jsonl"
DUR = int(sys.argv[1]) if len(sys.argv) > 1 else 300

BARRIERS = [
    ("#12110", "BTC_100k_yes"),
    ("#12130", "BTC_90k_yes"),
    ("#12111", "BTC_100k_no"),
    ("#12131", "BTC_90k_no"),
]

def main():
    inf = Info(constants.MAINNET_API_URL, skip_ws=False)
    register_outcome_assets(inf)
    f = open(OUT, "w", buffering=1)

    counts = {"BTC": 0}
    for _, name in BARRIERS:
        counts[name] = 0
    err = [0]

    def make_cb(coin, name):
        def cb(msg):
            try:
                data = msg.get("data") or msg
                # bbo message format: {'coin': 'BTC', 'time': ..., 'bbo': [bid_lvl, ask_lvl]}
                bbo = data.get("bbo")
                if not bbo or len(bbo) < 2:
                    return
                bid_lvl, ask_lvl = bbo[0], bbo[1]
                if not bid_lvl or not ask_lvl:
                    return
                bid = float(bid_lvl["px"])
                ask = float(ask_lvl["px"])
                mid = (bid + ask) / 2.0
                ts = time.time()
                srv = data.get("time")
                f.write(json.dumps({"ts": ts, "srv": srv, "feed": name, "coin": coin,
                                    "bid": bid, "ask": ask, "mid": mid,
                                    "bid_sz": float(bid_lvl.get("sz", 0)),
                                    "ask_sz": float(ask_lvl.get("sz", 0))}) + "\n")
                counts[name] += 1
            except Exception as e:
                err[0] += 1
                if err[0] < 5:
                    print("cb err", name, repr(e))
        return cb

    inf.subscribe({"type": "bbo", "coin": "BTC"}, make_cb("BTC", "BTC"))
    for coin, name in BARRIERS:
        inf.subscribe({"type": "bbo", "coin": coin}, make_cb(coin, name))

    t0 = time.time()
    tick = 30
    next_report = t0 + tick
    while time.time() - t0 < DUR:
        time.sleep(0.5)
        if time.time() >= next_report:
            print(f"t={int(time.time()-t0)}s counts={counts} err={err[0]}", flush=True)
            next_report += tick

    print(f"DONE t={int(time.time()-t0)}s counts={counts} err={err[0]}", flush=True)
    f.close()
    try:
        inf.disconnect_websocket()
    except Exception:
        pass

if __name__ == "__main__":
    main()
