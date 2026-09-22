"""Collect HIP-4 outcome trades with counterparty addresses from the HL websocket.

The `trades` subscription carries `users: [buyer, seller]`, which lets us
identify who is resting the book without any tid matching (that got 429'd on
2026-09-20). Read-only: subscribes, never orders.
"""
import json, sys, time, threading
import websocket  # from hyperliquid-python-sdk deps

rows = json.load(open("research/pairq-2026-09-21/screen.json"))
rows.sort(key=lambda r: -r["n24"])
top = [r for r in rows if r["n24"] >= 150][:26]
coins = []
for r in top:
    coins += [f"#{10*r['oid']}", f"#{10*r['oid']+1}"]
print(f"subscribing {len(coins)} legs across {len(top)} surfaces", file=sys.stderr)

OUT = open("research/pairq-2026-09-21/trades.jsonl", "a")
n = [0]

def on_open(ws):
    for c in coins:
        ws.send(json.dumps({"method": "subscribe",
                            "subscription": {"type": "trades", "coin": c}}))
        time.sleep(0.06)
    print("subscribed", file=sys.stderr)

def on_message(ws, msg):
    d = json.loads(msg)
    if d.get("channel") != "trades":
        return
    for t in d.get("data", []):
        OUT.write(json.dumps(t) + "\n")
        n[0] += 1
    if n[0] % 200 < len(d.get("data", [])):
        OUT.flush()
        print(f"{n[0]} trades", file=sys.stderr)

ws = websocket.WebSocketApp("wss://api.hyperliquid.xyz/ws",
                            on_open=on_open, on_message=on_message)
threading.Thread(target=lambda: ws.run_forever(ping_interval=25), daemon=True).start()
time.sleep(float(sys.argv[1]) if len(sys.argv) > 1 else 900)
OUT.flush(); OUT.close()
print(f"DONE {n[0]} trades", file=sys.stderr)
