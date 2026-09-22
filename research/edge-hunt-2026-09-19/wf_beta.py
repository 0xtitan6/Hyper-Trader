import json,os,math,sys
import numpy as np
D="/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
uni=[u[0] for u in json.load(open(D+"/universe.json"))]
IV=sys.argv[1]; STEP={"5m":5,"15m":15}[IV]; LOOK={"5m":288,"15m":96}[IV]
HOR=[1,2,4,6]; ms=STEP*60000
def st(x):
    x=np.asarray(x,float); n=len(x)
    if n<5: return f"n={n:5d} few"
    m=x.mean(); s=x.std(ddof=1); return f"n={n:5d} mean={m:+7.2f}bp sd={s:6.1f} t={m/(s/math.sqrt(n)):+6.2f}"
# market proxy: BTC fwd return by timestamp
btc=np.array(json.load(open(f"{D}/BTC_{IV}.json")),float)
bt={int(r[0]):r for r in btc}
def btc_fwd(t0,h):
    a=bt.get(t0+ms); b=bt.get(t0+h*ms)
    if a is None or b is None: return None
    return (b[4]-a[1])/a[1]*1e4
UNS={h:[] for h in HOR}; NEU={h:[] for h in HOR}
BASE_UNS={h:[] for h in HOR}; BASE_NEU={h:[] for h in HOR}
for c in uni:
    if c=="BTC": continue
    fp=f"{D}/{c}_{IV}.json"
    if not os.path.exists(fp): continue
    a=np.array(json.load(open(fp)),float)
    if len(a)<LOOK+200: continue
    t,o,hi,lo,cl,v,ntr=[a[:,i] for i in range(7)]
    ntl=v*cl
    for i in range(LOOK,len(a)-max(HOR)-1):
        if t[i+1]-t[i]!=ms: continue
        spike=(ntl[i-LOOK:i]<ntl[i]).mean()*100 >= 99
        entry=o[i+1]
        for h in HOR:
            if t[i+h]-t[i+1]!=(h-1)*ms: continue
            r=(cl[i+h]-entry)/entry*1e4
            bf=btc_fwd(int(t[i]),h)
            if bf is None: continue
            (UNS if spike else BASE_UNS)[h].append(r)
            (NEU if spike else BASE_NEU)[h].append(r-bf)
print(f"\n=== {IV}: UNSIGNED fwd return after top-1% volume bar vs all other bars (alts only, BTC = market proxy) ===")
for h in HOR:
    print(f" +{h*STEP:3d}m SPIKE raw {st(UNS[h])} | BASE raw {st(BASE_UNS[h])}")
    print(f"        SPIKE btc-neutral {st(NEU[h])} | BASE btc-neutral {st(BASE_NEU[h])}")
    a=np.array(UNS[h]);b=np.array(BASE_UNS[h])
    dm=a.mean()-b.mean(); se=math.sqrt(a.var(ddof=1)/len(a)+b.var(ddof=1)/len(b))
    a2=np.array(NEU[h]);b2=np.array(BASE_NEU[h])
    dm2=a2.mean()-b2.mean(); se2=math.sqrt(a2.var(ddof=1)/len(a2)+b2.var(ddof=1)/len(b2))
    print(f"        DIFF raw {dm:+7.2f}bp t={dm/se:+5.2f} | DIFF btc-neutral {dm2:+7.2f}bp t={dm2/se2:+5.2f}")
