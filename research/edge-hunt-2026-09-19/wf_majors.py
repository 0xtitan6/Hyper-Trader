import json,os,math
import numpy as np
D="/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
# coins that were already large & listed long before the 52d window -> no top-40-today survivorship
MAJ=["ETH","SOL","BNB","XRP","DOGE","ADA","LINK","AVAX","LTC","UNI","AAVE","NEAR","ARB","HYPE","SUI","CRV","INJ","ENA","WLD","TAO","ONDO","ZRO","ETHFI","kPEPE","FARTCOIN","XMR","ZEC","PAXG"]
def st(x):
    x=np.asarray(x,float); n=len(x)
    if n<5: return f"n={n:5d} few"
    m=x.mean(); s=x.std(ddof=1); return f"n={n:5d} mean={m:+7.2f}bp sd={s:6.1f} t={m/(s/math.sqrt(n)):+6.2f}"
for IV,STEP,LOOK,HOR in [("5m",5,288,[1,2,4]),("15m",15,96,[1,2,4])]:
    ms=STEP*60000
    btc={int(r[0]):r for r in np.array(json.load(open(f"{D}/BTC_{IV}.json")),float)}
    def bf(t0,h):
        a=btc.get(t0+ms); b=btc.get(t0+h*ms)
        return None if (a is None or b is None) else (b[4]-a[1])/a[1]*1e4
    SWN={h:[] for h in HOR}; BAN={h:[] for h in HOR}
    SGN={h:[] for h in HOR}; UPN={h:[] for h in HOR}; DNN={h:[] for h in HOR}
    used=[]
    for c in MAJ:
        fp=f"{D}/{c}_{IV}.json"
        if not os.path.exists(fp): continue
        a=np.array(json.load(open(fp)),float)
        if len(a)<LOOK+200: continue
        used.append(c)
        t,o,hi,lo,cl,v,ntr=[a[:,i] for i in range(7)]
        ntl=v*cl; ret=np.abs(cl-o)/o
        for i in range(LOOK,len(a)-max(HOR)-1):
            if t[i+1]-t[i]!=ms: continue
            sw=((ntl[i-LOOK:i]<ntl[i]).mean()>=0.99) and ((ret[i-LOOK:i]<ret[i]).mean()>=0.99)
            entry=o[i+1]; d=cl[i]-o[i]; sgn=1.0 if d>0 else (-1.0 if d<0 else 0.0)
            for h in HOR:
                if t[i+h]-t[i+1]!=(h-1)*ms: continue
                r=(cl[i+h]-entry)/entry*1e4; b=bf(int(t[i]),h)
                if b is None: continue
                if sw:
                    SWN[h].append(r-b)
                    if sgn: SGN[h].append(sgn*(r-b)); (UPN if sgn>0 else DNN)[h].append(r-b)
                else: BAN[h].append(r-b)
    print(f"\n=== {IV} MAJORS ONLY ({len(used)} coins, no survivorship): btc-neutral fwd after SWEEP bar ===")
    for h in HOR:
        print(f" +{h*STEP:3d}m SWEEP-unsigned {st(SWN[h])} | BASE {st(BAN[h])}")
        print(f"        SIGNED-by-direction {st(SGN[h])}  <-- the hypothesis (need > +9bp)")
        print(f"        after UP-sweep {st(UPN[h])} | after DOWN-sweep {st(DNN[h])}")
