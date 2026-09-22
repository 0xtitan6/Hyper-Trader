import json,os,math
import numpy as np
D="/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
MAJ=["ETH","SOL","BNB","XRP","DOGE","ADA","LINK","AVAX","LTC","UNI","AAVE","NEAR","ARB","HYPE","SUI","CRV","INJ","ENA","WLD","TAO","ONDO","ZRO","ETHFI","kPEPE","FARTCOIN","XMR","ZEC","PAXG"]
IV,STEP,LOOK="15m",15,96; ms=STEP*60000; H=2   # hold 2 bars = 30m
btcarr=np.array(json.load(open(f"{D}/BTC_{IV}.json")),float)
btc={int(r[0]):r for r in btcarr}
t0=btcarr[0,0]; t1=btcarr[-1,0]; NQ=6
edges=[t0+(t1-t0)*k/NQ for k in range(NQ+1)]
import datetime
print("BTC by sub-period:")
for k in range(NQ):
    sel=btcarr[(btcarr[:,0]>=edges[k])&(btcarr[:,0]<edges[k+1])]
    ret=(sel[-1,4]-sel[0,1])/sel[0,1]*100
    print(f"  P{k+1} {datetime.datetime.utcfromtimestamp(edges[k]/1000):%m-%d} -> {datetime.datetime.utcfromtimestamp(edges[k+1]/1000):%m-%d}  BTC {ret:+6.2f}%")
buckets={k:{"raw":[],"neu":[]} for k in range(NQ)}
for c in MAJ:
    fp=f"{D}/{c}_{IV}.json"
    if not os.path.exists(fp): continue
    a=np.array(json.load(open(fp)),float)
    if len(a)<LOOK+200: continue
    t,o,hi,lo,cl,v,ntr=[a[:,i] for i in range(7)]
    ntl=v*cl; ret=np.abs(cl-o)/o
    for i in range(LOOK,len(a)-H-2):
        if t[i+1]-t[i]!=ms or t[i+2]-t[i+1]!=ms: continue
        if (ntl[i-LOOK:i]<ntl[i]).mean()<0.99: continue
        if (ret[i-LOOK:i]<ret[i]).mean()<0.99: continue
        if cl[i]>=o[i]: continue
        j=i+1+H
        if t[j]-t[i]!=(1+H)*ms: continue
        ep=cl[i+1]                       # executable entry: one bar after the flush
        r=(cl[j]-ep)/ep*1e4
        ba=btc.get(int(t[i+1])); bb=btc.get(int(t[j]))
        if ba is None or bb is None: continue
        b=(bb[4]-ba[4])/ba[4]*1e4
        k=min(NQ-1,int((t[i]-t0)/(t1-t0)*NQ))
        buckets[k]["raw"].append(r); buckets[k]["neu"].append(r-b)
def st(x,fee):
    x=np.asarray(x,float)-fee;n=len(x)
    if n<5: return f"n={n:4d} few"
    m=x.mean();s=x.std(ddof=1); return f"n={n:4d} mean={m:+7.2f}bp t={m/(s/math.sqrt(n)):+5.2f}"
print("\nBUY after 15m DOWN-flush, entry = close of NEXT bar, hold 30m, majors:")
for k in range(NQ):
    print(f"  P{k+1}: raw net9 {st(buckets[k]['raw'],9)} | btc-neutral net18 {st(buckets[k]['neu'],18)}")
