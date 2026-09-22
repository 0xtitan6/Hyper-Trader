"""Subscribe to EVERY flowing outcome surface. The trades subscription backfills
~6h on subscribe, so this harvests 6h x ~130 surfaces in one pass."""
import json, sys, time, threading, websocket
rows=json.load(open("research/pairq-2026-09-21/screen.json"))
flow=[r for r in rows if r["n24"]>=5]
coins=[f"#{10*r['oid']}" for r in flow]          # YES leg only; NO is the mirror
print(f"subscribing {len(coins)} YES legs",file=sys.stderr)
OUT=open("research/pairq-2026-09-21/trades_all.jsonl","w"); n=[0]
def on_open(ws):
    for c in coins:
        ws.send(json.dumps({"method":"subscribe","subscription":{"type":"trades","coin":c}}))
        time.sleep(0.05)
    print("subscribed",file=sys.stderr)
def on_message(ws,msg):
    d=json.loads(msg)
    if d.get("channel")!="trades": return
    for t in d.get("data",[]):
        OUT.write(json.dumps(t)+"\n"); n[0]+=1
ws=websocket.WebSocketApp("wss://api.hyperliquid.xyz/ws",on_open=on_open,on_message=on_message)
threading.Thread(target=lambda: ws.run_forever(ping_interval=25),daemon=True).start()
time.sleep(int(sys.argv[1]))
OUT.flush(); OUT.close(); print(f"DONE {n[0]}",file=sys.stderr)
