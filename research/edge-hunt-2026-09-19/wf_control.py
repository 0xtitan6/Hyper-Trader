import json, os, math
import numpy as np
D="/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
uni=[u[0] for u in json.load(open(D+"/universe.json"))]
HOR=[1,2,5,10,30]; LOOK=1440
def load(c):
    fp=f"{D}/{c}_1m.json"
    return np.array(json.load(open(fp)),dtype=float) if os.path.exists(fp) else None
def st(x):
    x=np.asarray(x,float); n=len(x)
    if n<5: return f"n={n} few"
    m=x.mean(); s=x.std(ddof=1); return f"n={n:6d} mean={m:+7.2f}bp t={m/(s/math.sqrt(n)):+6.2f}"

# bucket every bar by its volume percentile rank (trailing 1440), report signed fwd ret
BUCK=[(0,50),(50,90),(90,99),(99,99.9),(99.9,100.1)]
res={b:{h:[] for h in HOR} for b in range(len(BUCK))}
tot=0
for c in uni:
    a=load(c)
    if a is None or len(a)<LOOK+100: continue
    t,o,hi,lo,cl,v,ntr=[a[:,i] for i in range(7)]
    ntl=v*cl
    for i in range(LOOK,len(a)-31):
        if t[i+1]-t[i]!=60000: continue
        d=cl[i]-o[i]
        if d==0: continue
        w=ntl[i-LOOK:i]
        pr=(w<ntl[i]).mean()*100
        bi=None
        for k,(a0,a1) in enumerate(BUCK):
            if a0<=pr<a1: bi=k; break
        if bi is None: continue
        sgn=1.0 if d>0 else -1.0
        entry=o[i+1]
        tot+=1
        for h in HOR:
            j=i+h
            if t[j]-t[i+1]!=(h-1)*60000: continue
            res[bi][h].append(sgn*(cl[j]-entry)/entry*1e4)
print("CONTROL: signed fwd return by trailing volume percentile bucket (sign = spike-bar direction)")
print("total bars scanned:",tot)
for k,(a0,a1) in enumerate(BUCK):
    print(f"\n vol pct [{a0},{a1}):")
    for h in HOR: print(f"   +{h:2d}m  {st(res[k][h])}")

# unconditional market drift control: unsigned mean fwd return, and mean |move| of spike bars
print("\nUNCONDITIONAL drift (unsigned, all bars, +10m):")
dr=[]
for c in uni:
    a=load(c)
    if a is None: continue
    t,o,cl=a[:,0],a[:,1],a[:,4]
    for i in range(LOOK,len(a)-31,7):
        if t[i+1]-t[i]!=60000 or t[i+10]-t[i+1]!=9*60000: continue
        dr.append((cl[i+10]-o[i+1])/o[i+1]*1e4)
print("  ",st(dr))
