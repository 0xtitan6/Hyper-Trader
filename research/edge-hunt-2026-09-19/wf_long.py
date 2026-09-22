import json,os,math,sys
import numpy as np
D="/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
uni=[u[0] for u in json.load(open(D+"/universe.json"))]
IV=sys.argv[1]; STEP={"5m":5,"15m":15}[IV]
LOOK={"5m":288,"15m":96}[IV]   # ~1 day trailing
HOR=[1,2,4,6]                   # in bars
def st(x):
    x=np.asarray(x,float); n=len(x)
    if n<5: return f"n={n:5d} few"
    m=x.mean(); s=x.std(ddof=1); return f"n={n:5d} mean={m:+7.2f}bp sd={s:6.1f} t={m/(s/math.sqrt(n)):+6.2f}"
def run(half=None):
    allr={h:[] for h in HOR}; up={h:[] for h in HOR}; dn={h:[] for h in HOR}
    for c in uni:
        fp=f"{D}/{c}_{IV}.json"
        if not os.path.exists(fp): continue
        a=np.array(json.load(open(fp)),float)
        if len(a)<LOOK+200: continue
        t,o,hi,lo,cl,v,ntr=[a[:,i] for i in range(7)]
        ntl=v*cl; ms=STEP*60000
        lo_i,hi_i=LOOK,len(a)-max(HOR)-1
        if half==0: hi_i=(LOOK+hi_i)//2
        if half==1: lo_i=(LOOK+hi_i)//2
        mu={}
        for h in HOR:
            rr=[(cl[i+h]-o[i+1])/o[i+1]*1e4 for i in range(lo_i,hi_i)
                if t[i+1]-t[i]==ms and t[i+h]-t[i+1]==(h-1)*ms]
            mu[h]=float(np.mean(rr)) if rr else 0.0
        for i in range(lo_i,hi_i):
            if t[i+1]-t[i]!=ms: continue
            if (ntl[i-LOOK:i]<ntl[i]).mean()*100 < 99: continue
            d=cl[i]-o[i]
            if d==0: continue
            sgn=1.0 if d>0 else -1.0; entry=o[i+1]
            for h in HOR:
                if t[i+h]-t[i+1]!=(h-1)*ms: continue
                adj=sgn*((cl[i+h]-entry)/entry*1e4-mu[h])
                allr[h].append(adj); (up if sgn>0 else dn)[h].append(adj)
    tag={None:"FULL",0:"1st half",1:"2nd half"}[half]
    print(f"\n--- {IV} top-1% vol bars, drift-adj, {tag} ---")
    for h in HOR:
        print(f" +{h*STEP:3d}m ALL {st(allr[h])} | UP {st(up[h])} | DOWN {st(dn[h])}")
for hh in (None,0,1): run(hh)
