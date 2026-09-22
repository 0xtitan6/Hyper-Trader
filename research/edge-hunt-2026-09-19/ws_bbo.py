import json,time,sys
import websocket
COINS=["BTC","ETH","SOL","HYPE","DOGE","XRP","SUI","LTC","PUMP","ASTER"]
D="/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
DUR=float(sys.argv[1]); f=open(D+"/ws_bbo.jsonl","a",buffering=1)
t_end=time.time()+DUR; last={}
def on_open(ws):
    for c in COINS:
        ws.send(json.dumps({"method":"subscribe","subscription":{"type":"bbo","coin":c}})); time.sleep(0.05)
    print("bbo subscribed",flush=True)
def on_message(ws,msg):
    if time.time()>t_end: ws.close(); return
    d=json.loads(msg)
    if d.get("channel")!="bbo": return
    x=d["data"]; c=x["coin"]; b,a=x["bbo"]
    if not b or not a: return
    now=time.time()
    if now-last.get(c,0)<0.4: return
    last[c]=now
    f.write(json.dumps([c,int(x["time"]),float(b["px"]),float(a["px"]),int(now*1000)])+"\n")
def on_error(ws,e): print("ERR",repr(e)[:120],flush=True)
while time.time()<t_end:
    try:
        websocket.WebSocketApp("wss://api.hyperliquid.xyz/ws",on_open=on_open,on_message=on_message,on_error=on_error).run_forever(ping_interval=20,ping_timeout=10)
    except Exception as e: print("rc",repr(e)[:80],flush=True)
    time.sleep(2)
print("bbo done",flush=True)
