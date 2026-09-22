import json,os,math
import numpy as np
D="/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
coins=sorted(set(f.split("_1h_long")[0] for f in os.listdir(D) if f.endswith("_1h_long.json")))
coins=[c for c in coins if len(json.load(open(f"{D}/{c}_1h_long.json")))>=5000]
# build aligned contiguous grid on common timestamps
T=None
raw={}
for c in coins:
    r=json.load(open(f"{D}/{c}_1h_long.json"))
    raw[c]={int(x[0]):x for x in r}
    s=set(raw[c].keys())
    T=s if T is None else (T & s)
T=sorted(T)
print("coins",len(coins),"common bars",len(T))
import datetime
f=lambda ms: datetime.datetime.utcfromtimestamp(ms/1000).strftime("%Y-%m-%d %H:%M")
print("range",f(T[0]),"->",f(T[-1]))
# check contiguity
gaps=[(T[i+1]-T[i]) for i in range(len(T)-1)]
print("unique gaps(ms)",sorted(set(gaps))[:5], "n non-1h gaps", sum(1 for g in gaps if g!=3600000))
hrs=np.array([datetime.datetime.utcfromtimestamp(t/1000).hour for t in T])
oc={}; cc={}
for c in coins:
    o=np.array([raw[c][t][1] for t in T]); cl=np.array([raw[c][t][4] for t in T])
    oc[c]=(cl/o-1)*1e4
    prev=np.concatenate([[np.nan],cl[:-1]])
    cc[c]=(cl/prev-1)*1e4
np.save("/tmp/T.npy",np.array(T)); np.save("/tmp/hrs.npy",hrs)
json.dump(coins,open("/tmp/coins.json","w"))
np.save("/tmp/oc.npy",np.array([oc[c] for c in coins]))
np.save("/tmp/cc.npy",np.array([cc[c] for c in coins]))

def tstat(x):
    x=x[~np.isnan(x)]
    return x.mean(), x.std(ddof=1)/math.sqrt(len(x)), x.mean()/(x.std(ddof=1)/math.sqrt(len(x))), len(x)
print("\n--- XMR by hour (open->close) ---")
x=oc["XMR"]
for h in range(24):
    m,se,t,n=tstat(x[hrs==h])
    flag="  <<<" if abs(t)>3 else ""
    print(f"hr{h:02d} n={n} mean={m:+7.2f}bp se={se:5.2f} t={t:+5.2f}{flag}")
m,se,t,n=tstat(x)
print(f"XMR all bars: mean={m:+.2f}bp/hr sd={x[~np.isnan(x)].std(ddof=1):.1f}bp -> {m*24:+.1f}bp/day")
