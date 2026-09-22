import json,os,math
import numpy as np
D="/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
MAJ=["ETH","SOL","BNB","XRP","DOGE","ADA","LINK","AVAX","LTC","UNI","AAVE","NEAR","ARB","HYPE","SUI","CRV","INJ","ENA","WLD","TAO","ONDO","ZRO","ETHFI","kPEPE","FARTCOIN","XMR","ZEC","PAXG"]
def st(x,fee=0.0):
    x=np.asarray(x,float)-fee; n=len(x)
    if n<5: return f"n={n:5d} few"
    m=x.mean(); s=x.std(ddof=1); return f"n={n:5d} mean={m:+7.2f}bp sd={s:6.1f} t={m/(s/math.sqrt(n)):+6.2f} win%={100*(x>0).mean():4.1f}"
for IV,STEP,LOOK,HOR in [("5m",5,288,[1,2,4,8]),("15m",15,96,[1,2,4])]:
    ms=STEP*60000
    btc={int(r[0]):r for r in np.array(json.load(open(f"{D}/BTC_{IV}.json")),float)}
    def bseg(t0,k,h):   # btc return from open of bar t0+k*ms to close of bar t0+h*ms
        a=btc.get(t0+k*ms); b=btc.get(t0+h*ms)
        return None if (a is None or b is None) else (b[4]-a[1])/a[1]*1e4
    for ENTRY in ["next_open","next_close"]:
        RAW={h:[] for h in HOR}; NEU={h:[] for h in HOR}; H1={h:[] for h in HOR}; H2={h:[] for h in HOR}
        for c in MAJ:
            fp=f"{D}/{c}_{IV}.json"
            if not os.path.exists(fp): continue
            a=np.array(json.load(open(fp)),float)
            if len(a)<LOOK+200: continue
            t,o,hi,lo,cl,v,ntr=[a[:,i] for i in range(7)]
            ntl=v*cl; ret=np.abs(cl-o)/o; midx=(LOOK+len(a))//2
            for i in range(LOOK,len(a)-max(HOR)-2):
                if t[i+1]-t[i]!=ms: continue
                if (ntl[i-LOOK:i]<ntl[i]).mean()<0.99: continue
                if (ret[i-LOOK:i]<ret[i]).mean()<0.99: continue
                if cl[i]>=o[i]: continue                      # DOWN flush only
                if ENTRY=="next_open": ep=o[i+1]; k=1
                else:
                    if t[i+2]-t[i+1]!=ms: continue
                    ep=cl[i+1]; k=2
                for h in HOR:
                    if h<k: continue
                    if t[i+h]-t[i]!=h*ms: continue
                    r=(cl[i+h]-ep)/ep*1e4
                    b=bseg(int(t[i]),k,h)
                    if b is None: continue
                    RAW[h].append(r); NEU[h].append(r-b)
                    (H1 if i<midx else H2)[h].append(r-b)
        print(f"\n=== {IV} MAJORS, BUY after DOWN-flush (top1% vol AND top1% |move|), entry={ENTRY} ===")
        for h in HOR:
            if len(RAW[h])<5: continue
            hold=(h-(1 if ENTRY=='next_open' else 2))*STEP
            print(f" hold {hold:3d}m  RAW {st(RAW[h])}")
            print(f"           NET of 9bp fees {st(RAW[h],9.0)}")
            print(f"           BTC-NEUTRAL {st(NEU[h])} | net of 18bp {st(NEU[h],18.0)}")
            print(f"           h1 {st(H1[h])} | h2 {st(H2[h])}")
