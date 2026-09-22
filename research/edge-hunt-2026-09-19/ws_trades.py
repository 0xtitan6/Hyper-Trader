import json, time, threading, sys, os
import websocket

COINS = ["BTC","ETH","SOL","HYPE","DOGE","XRP","SUI","LTC","PUMP","ASTER"]
D = "/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 4200.0
ft = open(D + "/ws_trades.jsonl", "a", buffering=1)
fm = open(D + "/ws_mids.jsonl", "a", buffering=1)
t_end = time.time() + DUR
cnt = {"t": 0, "m": 0}
last_mid_write = [0.0]

def on_open(ws):
    for c in COINS:
        ws.send(json.dumps({"method": "subscribe", "subscription": {"type": "trades", "coin": c}}))
        time.sleep(0.05)
    ws.send(json.dumps({"method": "subscribe", "subscription": {"type": "allMids"}}))
    print("subscribed", flush=True)

def on_message(ws, msg):
    if time.time() > t_end:
        ws.close(); return
    try:
        d = json.loads(msg)
    except Exception:
        return
    ch = d.get("channel")
    if ch == "trades":
        now = int(time.time() * 1000)
        for t in d["data"]:
            # coin, side (B=buy aggressor), px, sz, time, tid, hash
            ft.write(json.dumps([t["coin"], t["side"], t["px"], t["sz"], t["time"], t.get("tid"), now]) + "\n")
            cnt["t"] += 1
    elif ch == "allMids":
        now = time.time()
        if now - last_mid_write[0] < 0.25:
            return
        last_mid_write[0] = now
        mids = d["data"]["mids"]
        sub = {c: mids[c] for c in COINS if c in mids}
        fm.write(json.dumps([int(now * 1000), sub]) + "\n")
        cnt["m"] += 1

def on_error(ws, e):
    print("ERR", repr(e)[:150], flush=True)

while time.time() < t_end:
    try:
        ws = websocket.WebSocketApp("wss://api.hyperliquid.xyz/ws",
                                    on_open=on_open, on_message=on_message, on_error=on_error)
        ws.run_forever(ping_interval=20, ping_timeout=10)
    except Exception as e:
        print("reconnect", repr(e)[:100], flush=True)
    time.sleep(2)
print("done trades=%d mids=%d" % (cnt["t"], cnt["m"]), flush=True)
