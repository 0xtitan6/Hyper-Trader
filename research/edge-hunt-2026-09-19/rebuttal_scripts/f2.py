import json,datetime as dt,numpy as np,math
f=json.load(open("/tmp/xmr_funding.json"))
rows=sorted({int(x['time'])//3600000*3600000:float(x['fundingRate']) for x in f}.items())
t=np.array([r[0] for r in rows]); fr=np.array([r[1] for r in rows])*1e4  # bp per hour
h=np.array([dt.datetime.fromtimestamp(x/1000,dt.UTC).hour for x in t])
mon=np.array([dt.datetime.fromtimestamp(x/1000,dt.UTC).strftime("%Y-%m") for x in t])
print("n funding hours",len(t), dt.datetime.fromtimestamp(t[0]/1000,dt.UTC),"->",dt.datetime.fromtimestamp(t[-1]/1000,dt.UTC))
print(f"ALL hours mean funding = {fr.mean():+.4f} bp/hr  median {np.median(fr):+.4f}  p90 {np.percentile(fr,90):+.3f}  max {fr.max():+.3f}")
for hh in (20,21,7,8):
    x=fr[h==hh]; print(f"  hour {hh:02d}: n={len(x)} mean={x.mean():+.4f}bp median={np.median(x):+.4f} p90={np.percentile(x,90):+.3f} max={x.max():+.3f}")
print("\nmonthly mean funding bp/hr (all hours) and at hr20/21:")
for m in sorted(set(mon)):
    a=fr[mon==m]; b=fr[(mon==m)&(h==20)]; c=fr[(mon==m)&(h==21)]
    print(f"  {m} all={a.mean():+.4f} hr20={b.mean():+.4f} hr21={c.mean():+.4f} n={len(a)}")
# annualized equivalent
print(f"\nmean funding over whole window = {fr.mean():+.4f}bp/hr = {fr.mean()*24*365/100:+.1f}% APR for longs")
