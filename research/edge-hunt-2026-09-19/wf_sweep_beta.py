import json,os,math
import numpy as np
D="/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
uni=[u[0] for u in json.load(open(D+"/universe.json"))]
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
    SW={h:[] for h in HOR}; SWN={h:[] for h in HOR}
    BA={h:[] for h in HOR}; BAN={h:[] for h in HOR}
    halves={0:{h:[] for h in HOR},1:{h:[] for h in HOR}}
    for c in uni:
        if c=="BTC": continue
        fp=f"{D}/{c}_{IV}.json"
        if not os.path.exists(fp): continue
        a=np.array(json.load(open(fp)),float)
        if len(a)<LOOK+200: continue
        t,o,hi,lo,cl,v,ntr=[a[:,i] for i in range(7)]
        ntl=v*cl; ret=np.abs(cl-o)/o; mid=(LOOK+len(a))//2
        for i in range(LOOK,len(a)-max(HOR)-1):
            if t[i+1]-t[i]!=ms: continue
            sw=((ntl[i-LOOK:i]<ntl[i]).mean()>=0.99) and ((ret[i-LOOK:i]<ret[i]).mean()>=0.99)
            entry=o[i+1]
            for h in HOR:
                if t[i+h]-t[i+1]!=(h-1)*ms: continue
                r=(cl[i+h]-entry)/entry*1e4
                b=bf(int(t[i]),h)
                if b is None: continue
                if sw:
                    SW[h].append(r); SWN[h].append(r-b); halves[0 if i<mid else 1][h].append(r-b)
                else:
                    BA[h].append(r); BAN[h].append(r-b)
    print(f"\n=== {IV}: UNSIGNED fwd return after a SWEEP bar (top1% vol AND top1% |move|), alts only ===")
    for h in HOR:
        print(f" +{h*STEP:3d}m SWEEP raw {st(SW[h])} | SWEEP btc-neutral {st(SWN[h])}")
        print(f"        BASE  raw {st(BA[h])} | BASE  btc-neutral {st(BAN[h])}")
        print(f"        half1 {st(halves[0][h])} | half2 {st(halves[1][h])}")
