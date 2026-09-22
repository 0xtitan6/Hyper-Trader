"""Try to kill XMR hr20: (a) is it just long-beta to a trending XMR? (b) drop the best
month, (c) is it just market-wide hr20? (d) newey-west t, (e) does it exist on ZEC/other
privacy or on the pre-existing 15m data as an independent series?"""
import json, os, math, glob, datetime as dt
import numpy as np
D=os.path.dirname(os.path.abspath(__file__))+"/data"
raw={}
for f in sorted(glob.glob(f"{D}/*_1h_long.json")):
    c=os.path.basename(f).replace("_1h_long.json","")
    rows=json.load(open(f))
    if len(rows)<4800: continue
    raw[c]={int(r[0]):r for r in rows}
COINS=sorted(raw)
common=None
for c,m in raw.items():
    s=set(m); common=s if common is None else (common&s)
grid=np.array(sorted(common))
d=np.diff(grid)==3600000; runs,st=[],0
for i,ok in enumerate(d):
    if not ok: runs.append((st,i)); st=i+1
runs.append((st,len(grid)-1)); b0,b1=max(runs,key=lambda r:r[1]-r[0]); grid=grid[b0:b1+1]
O={c:np.array([raw[c][t][1] for t in grid]) for c in COINS}
C={c:np.array([raw[c][t][4] for t in grid]) for c in COINS}
hours=np.array([dt.datetime.fromtimestamp(t/1000,dt.UTC).hour for t in grid])
mon=np.array([dt.datetime.fromtimestamp(t/1000,dt.UTC).strftime("%Y-%m") for t in grid])
day=np.array([dt.datetime.fromtimestamp(t/1000,dt.UTC).strftime("%Y-%m-%d") for t in grid])
R={c:(C[c]-O[c])/O[c]*1e4 for c in COINS}
IDX=np.mean(np.vstack([R[c] for c in COINS]),axis=0)
def tt(x):
    x=np.asarray(x,float); n=len(x); m=x.mean(); s=x.std(ddof=1); return n,m,s,m/(s/math.sqrt(n))
COST=9.8
for coin,hr in [("XMR",20),("XMR",7),("ZEC",20),("XPL",20)]:
    x=R[coin][hours==hr]; mm=mon[hours==hr]; dd=day[hours==hr]
    print(f"\n########## {coin} hr{hr:02d} ##########")
    n,m,s,t=tt(x); print(f"raw: n={n} {m:+.2f}bp t={t:+.2f} net({COST})={m-COST:+.2f}")
    # (a) de-trend: subtract that coin's mean of the OTHER 23 hours on the SAME day
    others=[]
    for D_ in sorted(set(dd)):
        msk=day==D_
        if msk.sum()!=24: continue
        v=R[coin][msk]; hh=hours[msk]
        others.append((v[hh==hr][0], np.mean(v[hh!=hr])))
    a=np.array([o[0] for o in others]); b=np.array([o[1] for o in others])
    exc=a-b
    n2,m2,s2,t2=tt(exc)
    print(f"(a) excess over same-day mean of other 23 hours: n={n2} {m2:+.2f}bp t={t2:+.2f}")
    # (b) drop the single best calendar month
    best=max(set(mm),key=lambda k:np.mean(x[mm==k]))
    y=x[mm!=best]; n3,m3,s3,t3=tt(y)
    print(f"(b) drop best month ({best}, {np.mean(x[mm==best]):+.1f}bp): n={n3} {m3:+.2f}bp "
          f"t={t3:+.2f} net={m3-COST:+.2f}")
    worst=min(set(mm),key=lambda k:np.mean(x[mm==k]))
    y=x[mm!=worst]; print(f"    drop worst month ({worst}): {np.mean(y):+.2f}bp t={tt(y)[3]:+.2f}")
    # (c) residual vs market hr20
    xi=IDX[hours==hr]
    beta=np.polyfit(xi,x,1)[0]; res=x-beta*xi
    n4,m4,s4,t4=tt(res)
    print(f"(c) residual after market hr{hr:02d} beta={beta:.2f}: {m4:+.2f}bp t={t4:+.2f} "
          f"(market hr{hr:02d} = {xi.mean():+.2f}bp)")
    # (d) newey-west with 5 lags on the daily series
    xd=x-x.mean(); T=len(x); g0=np.dot(xd,xd)/T; S=g0
    for L in range(1,6):
        gl=np.dot(xd[:-L],xd[L:])/T; S+=2*(1-L/6)*gl
    se=math.sqrt(S/T); print(f"(d) Newey-West(5) t = {x.mean()/se:+.2f}  (iid t={t:+.2f})")
    # (e) rolling 60-day net
    nets=x-COST
    roll=[np.mean(nets[i:i+60]) for i in range(0,len(nets)-60,10)]
    print(f"(e) rolling 60-trade net bp: {' '.join(f'{v:+.0f}' for v in roll)}")
    print(f"    fraction of rolling windows with net>0: {np.mean(np.array(roll)>0):.2f}")
