"""Longer baseline from 5m candles."""
import json, time, urllib.request
from datetime import datetime, timezone
INFO = "https://api.hyperliquid.xyz/info"
def post(b):
    req = urllib.request.Request(INFO, data=json.dumps(b).encode(),
        headers={"Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())
now_ms = int(time.time()*1000)
day_ms = 24*3600*1000
start = now_ms - 90*day_ms
candles = []
cur = start
page=0
while cur < now_ms:
    page+=1
    end = min(cur + 5000*5*60*1000, now_ms)
    try:
        r = post({"type":"candleSnapshot","req":{"coin":"xyz:CL","interval":"5m","startTime":cur,"endTime":end}})
        if isinstance(r,list):
            candles.extend(r)
            print(f"p{page}: {len(r)} bars @ {datetime.fromtimestamp(cur/1000,timezone.utc).isoformat()}")
    except Exception as e:
        print(f"p{page}: {e}")
    cur = end+1
    time.sleep(0.3)
seen={c["t"]:c for c in candles}
candles=sorted(seen.values(),key=lambda c:c["t"])
print(f"unique 5m bars: {len(candles)}, span: {datetime.fromtimestamp(candles[0]['t']/1000,timezone.utc) if candles else '?'} .. {datetime.fromtimestamp(candles[-1]['t']/1000,timezone.utc) if candles else '?'}")
rets=[]
for i in range(1,len(candles)):
    p=float(candles[i-1]["c"]); c=float(candles[i]["c"])
    if p>0: rets.append((candles[i]["t"], 10000*(c-p)/p, c))
if rets:
    abs_r=sorted([abs(r[1]) for r in rets])
    n=len(abs_r)
    for p in [0.5,0.9,0.95,0.99,0.999,1.0]:
        k=min(int(p*n), n-1)
        print(f"  p{p*100:>5.1f}: {abs_r[k]:7.2f} bps  (5m)")
    # count >50bps *per minute equivalent* — 5m return >50bps implies at least one 1m sub-move
    for th in [50,100,200]:
        cnt=sum(1 for r in rets if abs(r[1])>=th)
        days=(candles[-1]["t"]-candles[0]["t"])/day_ms if len(candles)>1 else 1
        print(f"  |ret_5m|>={th}bps: {cnt} bars ({cnt/days:.2f}/day)")
