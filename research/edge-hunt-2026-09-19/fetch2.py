import requests, time, json, os
U="https://api.hyperliquid.xyz/info"
D=os.path.dirname(os.path.abspath(__file__))+"/data"
os.makedirs(D,exist_ok=True)
def post(b,tries=6):
    for i in range(tries):
        try:
            r=requests.post(U,json=b,timeout=30)
            if r.status_code==429: time.sleep(4*(i+1)); continue
            r.raise_for_status(); return r.json()
        except Exception as e:
            print("  retry",i,repr(e)[:90]); time.sleep(2*(i+1))
    return None
now=int(time.time()*1000)
r=post({"type":"metaAndAssetCtxs"})
rows=[]
for m,c in zip(r[0]["universe"],r[1]):
    if m.get("isDelisted"): continue
    oi=float(c.get("openInterest",0))*float(c.get("markPx",0) or 0)
    dv=float(c.get("dayNtlVlm",0) or 0)
    rows.append((m["name"],oi,dv))
rows.sort(key=lambda x:-x[1])
uni=[x for x in rows if ':' not in x[0]][:40]
json.dump(uni,open(D+"/universe.json","w"))
print("universe:",[u[0] for u in uni])
for name,oi,dv in uni:
    for iv in ["1m","5m","15m"]:
        fp=f"{D}/{name}_{iv}.json"
        if os.path.exists(fp): continue
        c=post({"type":"candleSnapshot","req":{"coin":name,"interval":iv,"startTime":now-200*86400*1000,"endTime":now}})
        time.sleep(0.35)
        if not c: print("skip",name,iv); continue
        json.dump([[k['t'],float(k['o']),float(k['h']),float(k['l']),float(k['c']),float(k['v']),k['n']] for k in c],open(fp,"w"))
    fp=f"{D}/{name}_funding.json"
    if not os.path.exists(fp):
        allf={}; st=now-60*86400*1000
        while True:
            f=post({"type":"fundingHistory","coin":name,"startTime":st,"endTime":now})
            time.sleep(0.35)
            if not f: break
            for k in f: allf[k['time']]=[float(k['fundingRate']),float(k['premium'])]
            mx=max(x['time'] for x in f)
            if len(f)<500 or mx<=st: break
            st=mx+1
        json.dump(sorted(allf.items()),open(fp,"w"))
    print("done",name,dv)
print("ALLDONE")
