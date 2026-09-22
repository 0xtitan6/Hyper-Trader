import json, time, urllib.request, sys
INFO="https://api.hyperliquid.xyz/info"
def post(body):
    req=urllib.request.Request(INFO, data=json.dumps(body).encode(),
                               headers={"Content-Type":"application/json"})
    for a in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                out=json.loads(r.read().decode())
            time.sleep(0.06); return out
        except Exception as e:
            if a==4: print("FAIL",body.get("type"),e,file=sys.stderr); return None
            time.sleep(1.5*(a+1))

meta = post({"type":"outcomeMeta"}) or {}
outs = meta.get("outcomes",[])
print("total outcomes:", len(outs))
json.dump(meta, open("research/pairq-2026-09-21/outcomeMeta.json","w"))
# print a few descriptions to understand shape
for o in outs[:5]:
    print(json.dumps(o)[:400])
