"""Mark the residual inventory. INVARIANT 10: realized is a fact, unrealized
is an opinion. The only maker showing a profit holds 22k open shares, so that
profit is entirely an opinion until marked."""
import json, collections, time, urllib.request, sys
INFO="https://api.hyperliquid.xyz/info"
def post(b):
    req=urllib.request.Request(INFO,data=json.dumps(b).encode(),
                               headers={"Content-Type":"application/json"})
    for a in range(5):
        try:
            with urllib.request.urlopen(req,timeout=30) as r: out=json.loads(r.read().decode())
            time.sleep(0.12); return out
        except Exception:
            if a==4: return None
            time.sleep(2.0*(a+1))

F=json.load(open("research/pairq-2026-09-21/maker_fills.json"))
pos=collections.defaultdict(collections.Counter)
for a,fl in F.items():
    for f in fl:
        if not f["coin"].startswith("#"): continue
        pos[a][f["coin"]] += (float(f["sz"]) if f["side"]=="B" else -float(f["sz"]))
need=set()
for a,p in pos.items():
    for c,v in p.items():
        if abs(v)>1e-6: need.add(c)
print(f"{len(need)} legs need a mark",file=sys.stderr)
marks={}
now=int(time.time()*1000)
for i,c in enumerate(sorted(need)):
    k=post({"type":"candleSnapshot","req":{"coin":c,"interval":"1d",
            "startTime":now-40*24*3600*1000,"endTime":now}})
    marks[c]=float(k[-1]["c"]) if isinstance(k,list) and k else None
    if i%50==0: print(i,file=sys.stderr)
json.dump(marks,open("research/pairq-2026-09-21/marks.json","w"))
print("marked",sum(1 for v in marks.values() if v is not None),"/",len(marks))
