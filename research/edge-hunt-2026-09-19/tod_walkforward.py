"""The decisive test: WALK-FORWARD hour-of-day mining.
Each month, pick the best coin-hour(s) using ONLY prior data, trade them the next month,
charge real costs. If mining hour-of-day is an edge, this makes money. If it is overfitting,
it does not. Also: XMR hour-20 specifically, out-of-sample-by-construction after the
in-sample discovery window.
"""
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
V={c:np.array([raw[c][t][5] for t in grid]) for c in COINS}
NT={c:np.array([raw[c][t][6] for t in grid]) for c in COINS}
hours=np.array([dt.datetime.fromtimestamp(t/1000,dt.UTC).hour for t in grid])
mon=np.array([dt.datetime.fromtimestamp(t/1000,dt.UTC).strftime("%Y-%m") for t in grid])
R={c:(C[c]-O[c])/O[c]*1e4 for c in COINS}
# per-coin all-in round trip cost at $640 measured live in tod_cost.py; default 11bp for
# coins we did not measure (9bp fee + ~2bp slippage), XMR measured 9.44+0.40 funding
COST={"XMR":9.8,"ZEC":9.8,"XPL":10.3,"ENA":15.3,"INJ":13.6,"NEAR":11.2,"CRV":12.0,
      "TAO":11.4,"ZRO":12.7,"BTC":9.5,"ETH":9.5,"SOL":10.3}
DEF=12.0
def tt(x):
    x=np.asarray(x,float); n=len(x)
    if n<8: return n,0,0,0
    m=x.mean(); s=x.std(ddof=1); return n,m,s,m/(s/math.sqrt(n))

months=sorted(set(mon))
print("months:",months)
print("\n=== WALK-FORWARD: train on all months < M, trade best coin-hour in month M ===")
print(f"{'month':<9} {'picked':<16} {'train t':>8} {'train bp':>9} {'OOS n':>6} {'OOS gross':>10} {'cost':>6} {'OOS net':>8}")
allnet=[]; alltr=[]
for mi in range(3,len(months)):
    M=months[mi]; tr=np.isin(mon,months[:mi]); te=mon==M
    best=None
    for c in COINS:
        for h in range(24):
            msk=tr&(hours==h)
            n,m,s,t=tt(R[c][msk])
            if n<40: continue
            sc=abs(t)
            if best is None or sc>best[0]: best=(sc,c,h,np.sign(m),m,t)
    _,c,h,sg,m_tr,t_tr=best
    x=sg*R[c][te&(hours==h)]
    cost=COST.get(c,DEF)
    if len(x)==0: continue
    net=x-cost
    allnet.extend(net); alltr.append((M,c,h,sg,m_tr,t_tr,len(x),x.mean(),net.mean()))
    print(f"{M:<9} {c+' hr'+f'{h:02d}'+('+' if sg>0 else '-'):<16} {t_tr:>+8.2f} {m_tr:>+9.2f} "
          f"{len(x):>6} {x.mean():>+10.2f} {cost:>6.1f} {net.mean():>+8.2f}")
allnet=np.array(allnet); n,m,s,t=tt(allnet)
print(f"\nWALK-FORWARD TOTAL: n={n} trades  net mean={m:+.2f}bp/trade  sd={s:.1f}  t={t:+.2f}")
print(f"  sum = {allnet.sum():+.0f}bp over {n} trades ; hitrate {np.mean(allnet>0):.3f}")

print("\n=== same, but pick the best 5 coin-hours each month and equal-weight ===")
allnet5=[]
for mi in range(3,len(months)):
    M=months[mi]; tr=np.isin(mon,months[:mi]); te=mon==M
    cands=[]
    for c in COINS:
        for h in range(24):
            msk=tr&(hours==h); n0,m0,s0,t0=tt(R[c][msk])
            if n0<40: continue
            cands.append((abs(t0),c,h,np.sign(m0)))
    cands.sort(reverse=True)
    for _,c,h,sg in cands[:5]:
        x=sg*R[c][te&(hours==h)]-COST.get(c,DEF)
        allnet5.extend(x)
allnet5=np.array(allnet5); n,m,s,t=tt(allnet5)
print(f"top-5 WALK-FORWARD: n={n} net mean={m:+.2f}bp/trade sd={s:.1f} t={t:+.2f} sum={allnet5.sum():+.0f}bp")

print("\n=== XMR hr20 standalone, month by month, NET of measured 9.8bp all-in ===")
x=R["XMR"][hours==20]; mm=mon[hours==20]
cum=0
for k in sorted(set(mm)):
    y=x[mm==k]-9.8; cum+=y.sum()
    print(f"  {k} n={len(y):>3} gross={np.mean(x[mm==k]):+7.2f}bp net={y.mean():+7.2f}bp "
          f"sum={y.sum():+8.0f}bp cum={cum:+8.0f}bp")
n,m,s,t=tt(x-9.8)
print(f"  ALL: n={n} net={m:+.2f}bp/trade t={t:+.2f} total={n*m:+.0f}bp = {n*m/100:+.1f}% of notional over 208 days")
# block bootstrap CI (weekly blocks) on the net mean
y=x-9.8; rng=np.random.default_rng(5); B=5000; bl=7
nb=len(y)//bl
bs=[]
for _ in range(B):
    idx=rng.integers(0,nb,nb)
    samp=np.concatenate([y[i*bl:(i+1)*bl] for i in idx])
    bs.append(samp.mean())
bs=np.array(bs)
print(f"  weekly-block bootstrap (B=5000): mean {bs.mean():+.2f}bp, "
      f"95% CI [{np.percentile(bs,2.5):+.2f}, {np.percentile(bs,97.5):+.2f}]bp, "
      f"P(net<=0)={np.mean(bs<=0):.4f}")

print("\n=== XMR hour profile (all 24, gross open->close bp) + volume/trade-count check ===")
for h in range(24):
    y=R["XMR"][hours==h]; n,m,s,t=tt(y)
    vv=np.mean(V["XMR"][hours==h]*C["XMR"][hours==h]); nt=np.mean(NT["XMR"][hours==h])
    print(f"  hr {h:02d}: {m:+7.2f}bp t={t:+5.2f}  $vol={vv/1e3:8.0f}k trades/hr={nt:7.0f}")
print(f"  sum of 24 hourly means = {sum(np.mean(R['XMR'][hours==h]) for h in range(24)):+.1f}bp/day "
      f"vs actual mean daily = {np.mean(R['XMR'])*24:+.1f}bp")
