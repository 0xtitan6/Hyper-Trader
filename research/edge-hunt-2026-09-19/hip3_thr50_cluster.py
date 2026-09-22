import json,math,statistics as st,datetime as dt
from collections import defaultdict
D=json.load(open("/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data/hip3_1m.json"))
def insess(ms):
    d=dt.datetime.fromtimestamp(ms/1000,dt.timezone.utc)
    if d.weekday()>=5: return False
    mn=d.hour*60+d.minute
    return 13*60+30<=mn<20*60
def tstat(x):
    n=len(x)
    if n<2: return float("nan"),float("nan"),n
    m=sum(x)/n; sd=st.pstdev(x)*math.sqrt(n/(n-1)) if n>1 else 0
    return m,(m/(sd/math.sqrt(n)) if sd>0 else float("nan")),n
POOL=[c for c in D if c.startswith(("xyz:","io:"))]
raw=[]
for c in POOL:
    ks=D[c]; t=[k["t"] for k in ks]; px=[float(k["c"]) for k in ks]
    for i in range(1,len(px)-16):
        if t[i]-t[i-1]!=60000 or not insess(t[i]): continue
        r=(px[i]-px[i-1])/px[i-1]*1e4
        if abs(r)<50: continue
        s=1 if r>0 else -1
        if t[i+15]-t[i]!=15*60000: continue
        raw.append((t[i],c,s*(px[i+15]-px[i])/px[i]*1e4,s*(px[i+5]-px[i])/px[i]*1e4))
raw.sort()
print("all overlapping events n=%d"%len(raw))
# 1) non-overlapping: within a coin, require >=15min since last accepted event
last=defaultdict(lambda:-1e18); no=[]
for t,c,f15,f5 in raw:
    if t-last[c]>=15*60000:
        no.append((t,c,f15,f5)); last[c]=t
m,tt,n=tstat([x[2] for x in no]); print("NON-OVERLAPPING h=15: mean %+7.2f t %+5.2f n=%d  (net of 9bp: %+.2f)"%(m,tt,n,m-9))
m,tt,n=tstat([x[3] for x in no]); print("NON-OVERLAPPING h= 5: mean %+7.2f t %+5.2f n=%d  (net of 9bp: %+.2f)"%(m,tt,n,m-9))
# 2) cluster by (coin, day): average within cluster, t across clusters
for h,ix in (("h=15",2),("h=5",3)):
    cl=defaultdict(list)
    for t,c,f15,f5 in raw:
        day=dt.datetime.fromtimestamp(t/1000,dt.timezone.utc).strftime("%m-%d")
        cl[(c,day)].append((f15,f5)[0 if ix==2 else 1])
    means=[sum(v)/len(v) for v in cl.values()]
    m,tt,n=tstat(means)
    print("CLUSTER(coin,day) %s: mean-of-cluster-means %+7.2f t %+5.2f n_clusters=%d  net %+.2f"%(h,m,tt,n,m-9))
    print("   clusters:",sorted([(k[0],k[1],round(sum(v)/len(v),1),len(v)) for k,v in cl.items()],key=lambda z:z[2]))
