import json,os,math,sys
import numpy as np
D="/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
uni=[u[0] for u in json.load(open(D+"/universe.json"))]
CFG={"1m":(1,1440),"5m":(5,288),"15m":(15,96)}
def st(x):
    x=np.asarray(x,float); n=len(x)
    if n<5: return f"n={n:5d} few"
    m=x.mean(); s=x.std(ddof=1); return f"n={n:5d} mean={m:+7.2f}bp sd={s:6.1f} t={m/(s/math.sqrt(n)):+6.2f}"
for IV in ["1m","5m","15m"]:
    STEP,LOOK=CFG[IV]; ms=STEP*60000; HOR=[1,2,4,8]
    res={h:[] for h in HOR}; up={h:[] for h in HOR}; dn={h:[] for h in HOR}
    for c in uni:
        fp=f"{D}/{c}_{IV}.json"
        if not os.path.exists(fp): continue
        a=np.array(json.load(open(fp)),float)
        if len(a)<LOOK+200: continue
        t,o,hi,lo,cl,v,ntr=[a[:,i] for i in range(7)]
        ntl=v*cl; ret=np.abs(cl-o)/o
        for i in range(LOOK,len(a)-max(HOR)-1):
            if t[i+1]-t[i]!=ms: continue
            if (ntl[i-LOOK:i]<ntl[i]).mean()<0.99: continue
            if (ret[i-LOOK:i]<ret[i]).mean()<0.99: continue   # BOTH volume and move extreme
            d=cl[i]-o[i]
            if d==0: continue
            sgn=1.0 if d>0 else -1.0; entry=o[i+1]
            for h in HOR:
                if t[i+h]-t[i+1]!=(h-1)*ms: continue
                r=sgn*(cl[i+h]-entry)/entry*1e4
                res[h].append(r); (up if sgn>0 else dn)[h].append(r)
    print(f"\n--- {IV} SWEEP bars (top1% volume AND top1% |move|), sign=bar direction, entry=next open ---")
    for h in HOR:
        print(f" +{h*STEP:3d}m ALL {st(res[h])} | UP {st(up[h])} | DN {st(dn[h])}")
