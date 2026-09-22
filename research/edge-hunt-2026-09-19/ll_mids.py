import json, time, sys
import websocket
COINS=["BTC","ETH","SOL","HYPE","DOGE","XRP","SUI","LTC","BNB","AVAX","LINK","ADA","NEAR","ARB","WLD","TAO","ENA","UNI","AAVE","INJ"]
D="/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
DUR=float(sys.argv[1]) if len(sys.argv)>1 else 3600.0
f=open(D+"/ll_mids.jsonl","a",buffering=1)
t_end=time.time()+DUR
n=[0]
def on_open(ws):
    ws.send(json.dumps({"method":"subscribe","subscription":{"type":"allMids"}}))
    print("subscribed",flush=True)
def on_message(ws,msg):
    if time.time()>t_end:
        ws.close();return
    try: d=json.loads(msg)
    except Exception: return
    if d.get("channel")!="allMids": return
    m=d["data"]["mids"]
    f.write(json.dumps([int(time.time()*1000),{c:m[c] for c in COINS if c in m}])+"\n")
    n[0]+=1
    if n[0]%500==0: print("msgs",n[0],flush=True)
while time.time()<t_end:
    try:
        ws=websocket.WebSocketApp("wss://api.hyperliquid.xyz/ws",on_open=on_open,on_message=on_message)
        ws.run_forever(ping_interval=20)
    except Exception as e:
        print("err",repr(e)[:80],flush=True)
    time.sleep(1)
print("done",n[0],flush=True)
