import requests,time,json,numpy as np,datetime as dt,math
U="https://api.hyperliquid.xyz/info"
def post(b,tries=5):
    for i in range(tries):
        try:
            r=requests.post(U,json=b,timeout=30)
            if r.status_code==429: time.sleep(5*(i+1)); continue
            r.raise_for_status(); return r.json()
        except Exception as e: time.sleep(2*(i+1))
    return None
T=np.load("/tmp/T.npy"); start=int(T[0]); end=int(T[-1])+7200000
rows={}
cur=start
while cur<end:
    d=post({"type":"fundingHistory","coin":"XMR","startTime":cur,"endTime":end})
    time.sleep(0.4)
    if not d: break
    for r in d: rows[int(r["time"])]=float(r["fundingRate"])
    nt=max(int(r["time"]) for r in d)
    if nt<=cur: break
    cur=nt+1
    if len(d)<500: break
print("funding prints:",len(rows))
ts=np.array(sorted(rows)); fr=np.array([rows[t] for t in ts])*1e4  # bp per hour
hh=np.array([dt.datetime.fromtimestamp(t/1000,dt.UTC).hour for t in ts])
print("range",dt.datetime.fromtimestamp(ts[0]/1000,dt.UTC),"->",dt.datetime.fromtimestamp(ts[-1]/1000,dt.UTC))
print("ALL hours: mean %+.3f bp/hr  median %+.3f  p90 %+.3f  max %+.3f  frac>0 %.3f"%(fr.mean(),np.median(fr),np.percentile(fr,90),fr.max(),np.mean(fr>0)))
for h in (20,21,7):
    y=fr[hh==h]; print("  hr%02d funding print: n=%d mean %+.3f bp  median %+.3f  p90 %+.3f"%(h,len(y),y.mean(),np.median(y),np.percentile(y,90)))
# what a long entered 20:00 exited 21:00 pays: funding charged at the 21:00 print
y21=fr[hh==21]
print("\ncost of the 1h hold = funding print at 21:00 = mean %+.3f bp (claim assumed 0.40, live now 0.46)"%y21.mean())
json.dump({"mean_all":fr.mean(),"mean21":y21.mean()},open("/tmp/xmrfund.json","w"))
