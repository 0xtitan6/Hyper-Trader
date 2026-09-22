import json,math,statistics as st,datetime as dt
from collections import Counter,defaultdict
D=json.load(open("/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data/hip3_1m.json"))
def insess(ms):
    d=dt.datetime.fromtimestamp(ms/1000,dt.timezone.utc)
    if d.weekday()>=5: return False
    mn=d.hour*60+d.minute
    return 13*60+30<=mn<20*60
def tstat(x):
    n=len(x)
    if n<3: return float("nan"),float("nan")
    m=sum(x)/n; sd=st.pstdev(x)*math.sqrt(n/(n-1))
    return m,(m/(sd/math.sqrt(n)) if sd>0 else float("nan"))
POOL=[c for c in D if c.startswith(("xyz:","io:"))]
ev=[]
for c in POOL:
    ks=D[c]; t=[k["t"] for k in ks]; px=[float(k["c"]) for k in ks]
    for i in range(1,len(px)-16):
        if t[i]-t[i-1]!=60000 or not insess(t[i]): continue
        r=(px[i]-px[i-1])/px[i-1]*1e4
        if abs(r)<50: continue
        s=1 if r>0 else -1
        f={}
        ok=True
        for h in (1,5,15):
            if t[i+h]-t[i]!=60000*h: ok=False;break
            f[h]=s*(px[i+h]-px[i])/px[i]*1e4
        if ok: ev.append((t[i],c,f))
print("THR=50 in-session pooled events n=%d"%len(ev))
print("by coin:",Counter(c for _,c,_ in ev).most_common())
print("by date:",Counter(dt.datetime.fromtimestamp(t/1000,dt.timezone.utc).strftime("%m-%d") for t,_,_ in ev).most_common())
for h in (1,5,15):
    m,tt=tstat([f[h] for _,_,f in ev]); print("all   h=%2d mean %+7.2f t %+5.2f"%(h,m,tt))
ev.sort()
half=len(ev)//2
for lbl,sub in (("firstH",ev[:half]),("secondH",ev[half:])):
    for h in (1,5,15):
        m,tt=tstat([f[h] for _,_,f in sub]); print("%-7s h=%2d mean %+7.2f t %+5.2f n=%d"%(lbl,h,m,tt,len(sub)))
# leave-one-coin-out on h=15
print("\nleave-one-coin-out, h=15:")
for c in sorted(set(x[1] for x in ev)):
    sub=[f[15] for _,cc,f in ev if cc!=c]
    m,tt=tstat(sub); print("  drop %-12s mean %+7.2f t %+5.2f n=%d"%(c,m,tt,len(sub)))
# median, and net of 9bp cost, and win rate
for h in (1,5,15):
    v=[f[h] for _,_,f in ev]
    print("h=%2d median %+7.2f  win%%(>9bp) %5.1f  mean-9bp %+7.2f"%(h,st.median(v),100*sum(1 for x in v if x>9)/len(v),sum(v)/len(v)-9))
