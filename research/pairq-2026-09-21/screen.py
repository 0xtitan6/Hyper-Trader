import json, time, urllib.request, sys
INFO="https://api.hyperliquid.xyz/info"
def post(body):
    req=urllib.request.Request(INFO, data=json.dumps(body).encode(),
                               headers={"Content-Type":"application/json"})
    for a in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                out=json.loads(r.read().decode())
            time.sleep(0.07); return out
        except Exception as e:
            if a==4: return None
            time.sleep(1.5*(a+1))

meta=json.load(open("research/pairq-2026-09-21/outcomeMeta.json"))
outs=meta["outcomes"]
now=int(time.time()*1000)
rows=[]
for i,o in enumerate(outs):
    oid=o["outcome"]
    c=post({"type":"candleSnapshot","req":{"coin":f"#{10*oid}","interval":"1h",
            "startTime":now-24*3600*1000,"endTime":now}})
    v=n=0.0
    if isinstance(c,list):
        v=sum(float(x["v"]) for x in c); n=sum(int(x["n"]) for x in c)
    rows.append({"oid":oid,"name":o["name"],"desc":o["description"],"v24":v,"n24":int(n)})
    if i%40==0: print(i,file=sys.stderr)
json.dump(rows,open("research/pairq-2026-09-21/screen.json","w"))
rows.sort(key=lambda r:-r["n24"])
print(f"{'oid':>5} {'n24':>6} {'v24':>10}  desc")
for r in rows[:45]:
    print(f"{r['oid']:>5} {r['n24']:>6} {r['v24']:>10.0f}  {r['desc'][:70]}")
print("with any trades:",sum(1 for r in rows if r['n24']>0),"/",len(rows))
