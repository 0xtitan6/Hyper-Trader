import requests,time,json,datetime as dt
U="https://api.hyperliquid.xyz/info"
def post(b,tries=5):
    for i in range(tries):
        r=requests.post(U,json=b,timeout=40)
        if r.status_code==429: time.sleep(4*(i+1)); continue
        r.raise_for_status(); return r.json()
    return None
start=int(dt.datetime(2026,2,22,tzinfo=dt.UTC).timestamp()*1000)
end=int(time.time()*1000)
out=[]
s=start
while s<end:
    d=post({"type":"fundingHistory","coin":"XMR","startTime":s,"endTime":min(s+500*3600*1000,end)})
    time.sleep(0.4)
    if not d: break
    out+=d
    ns=max(int(x['time']) for x in d)+3600000
    if ns<=s: break
    s=ns
    print(len(out), dt.datetime.fromtimestamp(out[-1]['time']/1000,dt.UTC), flush=True)
json.dump(out,open("/tmp/xmr_funding.json","w"))
print("TOTAL",len(out))
