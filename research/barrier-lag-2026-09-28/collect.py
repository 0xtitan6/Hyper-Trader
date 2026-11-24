"""Collect WS updates for BTC perp + 3 priceTouch barriers, timestamped locally.

Two feeds needed:
- BTC perp l2Book (or bbo). Use `l2Book` for consistency.
- Barrier coin l2Book for each of #12110 (100k), #12130 (90k), #12170 (60k).

Writes JSONL: {ts, feed, coin, bid, ask, mid} per book update.
"""
import json, time, sys
from hyperliquid.info import Info
from hyperliquid.utils import constants
from src.hl_outcome import register_outcome_assets

OUT = "research/barrier-lag-2026-09-28/feed.jsonl"
DUR = int(sys.argv[1]) if len(sys.argv) > 1 else 300  # seconds

BARRIERS = [
    ("#12110", "BTC_100k_yes"),   # OTM up 20% mid ~0.017
    ("#12130", "BTC_90k_yes"),    # OTM up 8.5% mid ~0.028 (most sensitive)
    ("#12170", "BTC_60k_yes"),    # OTM down 27% mid ~0.002 (deep)
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
                # Book has 'levels' -> [bids, asks]; each level: {'px','sz','n'}
                levels = data.get("levels")
                if not levels or len(levels) < 2:
                    return
                bids = levels[0]
                asks = levels[1]
                if not bids or not asks:
                    return
                bid = float(bids[0]["px"])
                ask = float(asks[0]["px"])
                mid = (bid + ask) / 2.0
                ts = time.time()
                f.write(json.dumps({"ts": ts, "feed": name, "coin": coin, "bid": bid, "ask": ask, "mid": mid}) + "\n")
                counts[name] += 1
            except Exception as e:
                err[0] += 1
                if err[0] < 3:
                    print("cb err", name, repr(e))
        return cb

    # subscribe
    inf.subscribe({"type": "l2Book", "coin": "BTC"}, make_cb("BTC", "BTC"))
    for coin, name in BARRIERS:
        inf.subscribe({"type": "l2Book", "coin": coin}, make_cb(coin, name))

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
