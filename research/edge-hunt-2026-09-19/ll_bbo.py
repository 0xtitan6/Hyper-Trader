import json, time, sys
import websocket

COINS = ["BTC","ETH","HYPE","SOL","DOGE","XRP","SUI","LTC","AVAX","LINK","ARB","NEAR","ENA","UNI","WLD","TAO"]
D = "/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 3000.0
f = open(D + "/ll_bbo.jsonl", "a", buffering=1)
t_end = time.time() + DUR
n = [0]


def on_open(ws):
    for c in COINS:
        ws.send(json.dumps({"method": "subscribe", "subscription": {"type": "bbo", "coin": c}}))
        time.sleep(0.05)
    print("subscribed", len(COINS), flush=True)


def on_message(ws, msg):
    if time.time() > t_end:
        ws.close()
        return
    try:
        d = json.loads(msg)
    except Exception:
        return
    if d.get("channel") != "bbo":
        return
    dd = d["data"]
    bbo = dd.get("bbo") or []
    if len(bbo) < 2 or bbo[0] is None or bbo[1] is None:
        return
    # coin, server_time_ms, bid, ask, local_recv_ms
    f.write(json.dumps([dd["coin"], dd["time"], float(bbo[0]["px"]), float(bbo[1]["px"]),
                        int(time.time() * 1000)]) + "\n")
    n[0] += 1
    if n[0] % 20000 == 0:
        print("msgs", n[0], flush=True)


while time.time() < t_end:
    try:
        ws = websocket.WebSocketApp("wss://api.hyperliquid.xyz/ws",
                                    on_open=on_open, on_message=on_message)
        ws.run_forever(ping_interval=20)
    except Exception as e:
        print("err", repr(e)[:80], flush=True)
    time.sleep(1)
print("done", n[0], flush=True)
