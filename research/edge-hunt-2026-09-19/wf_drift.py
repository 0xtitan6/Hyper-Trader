import json,os,math
import numpy as np
D="/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
uni=[u[0] for u in json.load(open(D+"/universe.json"))]
HOR=[1,2,5,10,30]; LOOK=1440
def st(x):
    x=np.asarray(x,float); n=len(x)
    if n<5: return f"n={n:5d} few"
    m=x.mean(); s=x.std(ddof=1); return f"n={n:5d} mean={m:+7.2f}bp sd={s:6.1f} t={m/(s/math.sqrt(n)):+6.2f}"
up={h:[] for h in HOR}; dn={h:[] for h in HOR}; allr={h:[] for h in HOR}
percoin={}
for c in uni:
    fp=f"{D}/{c}_1m.json"
    if not os.path.exists(fp): continue
    a=np.array(json.load(open(fp)),float)
    if len(a)<LOOK+100: continue
    t,o,hi,lo,cl,v,ntr=[a[:,i] for i in range(7)]
    ntl=v*cl
    # unconditional drift per coin per horizon (bp), from same sample
    mu={}
    for h in HOR:
        rr=[]
        for i in range(LOOK,len(a)-31):
            if t[i+1]-t[i]!=60000 or t[i+h]-t[i+1]!=(h-1)*60000: continue
            rr.append((cl[i+h]-o[i+1])/o[i+1]*1e4)
        mu[h]=float(np.mean(rr)) if rr else 0.0
    for i in range(LOOK,len(a)-31):
        if t[i+1]-t[i]!=60000: continue
        w=ntl[i-LOOK:i]; pr=(w<ntl[i]).mean()*100
        if pr<99: continue
        d=cl[i]-o[i]
        if d==0: continue
        sgn=1.0 if d>0 else -1.0
        entry=o[i+1]
        for h in HOR:
            if t[i+h]-t[i+1]!=(h-1)*60000: continue
            raw=(cl[i+h]-entry)/entry*1e4
            adj=sgn*(raw-mu[h])
            allr[h].append(adj)
            (up if sgn>0 else dn)[h].append(adj)
            percoin.setdefault(c,{}).setdefault(h,[]).append(adj)
print("DRIFT-ADJUSTED signed fwd return, top-1% volume bars (sign=bar direction)")
print("  positive = momentum(follow-through), negative = reversion")
for h in HOR:
    print(f" +{h:2d}m ALL {st(allr[h])} | UP-spikes {st(up[h])} | DOWN-spikes {st(dn[h])}")
print("\nPER-COIN +10m (drift-adj):")
rows=[]
for c,dd in percoin.items():
    if 10 in dd and len(dd[10])>=15:
        x=np.array(dd[10]); rows.append((x.mean(),len(x),c))
rows.sort()
for m,n,c in rows: print(f"  {c:8s} n={n:4d} mean={m:+8.2f}bp")
pos=sum(1 for m,n,c in rows if m>0)
print(f"  coins with positive(momentum) mean: {pos}/{len(rows)}")
