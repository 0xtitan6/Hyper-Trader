import json, math, bisect, sys
import numpy as np
D="/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
LAG=float(sys.argv[1]) if len(sys.argv)>1 else 2000.0   # ms delay before we can act
MINNTL=float(sys.argv[2]) if len(sys.argv)>2 else 20000.0
PCT=float(sys.argv[3]) if len(sys.argv)>3 else 99.0
HOR=[30,120,600]  # seconds

T=[json.loads(l) for l in open(D+"/ws_trades.jsonl")]
M=[json.loads(l) for l in open(D+"/ws_mids.jsonl")]
M.sort(key=lambda x:x[0])
mt=[m[0] for m in M]
coins=sorted({x[0] for x in T})
mid={c:[] for c in coins}; midt={c:[] for c in coins}
for ts,d in M:
    for c,p in d.items():
        if mid.get(c) is not None:
            mid[c].append(float(p)); midt[c].append(ts)
def get_mid(c,ts,maxgap=15000):
    a=midt[c]
    if not a: return None
    i=bisect.bisect_left(a,ts)
    if i>=len(a): return None
    if a[i]-ts>maxgap: return None
    return mid[c][i]

# dedupe by tid, sort by exchange ts
seen=set(); TT=[]
for x in T:
    k=(x[0],x[5])
    if k in seen: continue
    seen.add(k); TT.append(x)
TT.sort(key=lambda x:(x[0],x[4]))
print(f"trades raw={len(T)} dedup={len(TT)} mids={len(M)}")
span=(max(x[4] for x in TT)-min(x[4] for x in TT))/60000
print(f"tape span = {span:.1f} min, coins={coins}")

# build sweeps: same coin+side, consecutive, within 500ms
sweeps=[]
cur=None
for x in TT:
    c,side,px,sz,ts,tid,recv=x
    ntl=float(px)*float(sz)
    if cur and cur[0]==c and cur[1]==side and ts-cur[3]<=500:
        cur[2]+=ntl; cur[3]=ts; cur[5]=max(cur[5],recv); cur[6]+=1
    else:
        if cur: sweeps.append(cur)
        cur=[c,side,ntl,ts,ts,recv,1]   # coin,side,ntl,t_end,t_start,recv_end,nfills
if cur: sweeps.append(cur)
print("sweeps:",len(sweeps))

bycoin={}
for s in sweeps: bycoin.setdefault(s[0],[]).append(s[2])
res={h:[] for h in HOR}; impact=[]; percoin={}
nev=0
for s in sweeps:
    c,side,ntl,tend,tstart,recv,nf=s
    v=bycoin[c]
    if len(v)<200: continue
    thr=np.percentile(v,PCT)
    if ntl<thr or ntl<MINNTL: continue
    sgn=1.0 if side=="B" else -1.0
    m0=get_mid(c,tstart-6000)           # pre-event mid (<=6s before)
    me=get_mid(c,int(recv+LAG))         # our entry mid, LAG ms after we SAW it
    if me is None: continue
    nev+=1
    if m0: impact.append(sgn*(me-m0)/m0*1e4)
    for h in HOR:
        mh=get_mid(c,int(recv+LAG+h*1000))
        if mh is None: continue
        r=sgn*(mh-me)/me*1e4
        res[h].append(r)
        percoin.setdefault(c,{}).setdefault(h,[]).append(r)
def st(x):
    x=np.asarray(x,float); n=len(x)
    if n<5: return f"n={n:4d} (too few)"
    m=x.mean(); s=x.std(ddof=1)
    return f"n={n:4d} mean={m:+7.2f}bp sd={s:6.2f} t={m/(s/math.sqrt(n)):+6.2f} med={np.median(x):+6.2f} win%={100*(x>0).mean():.0f}"
print(f"\n=== WHALE SWEEP follow-through (top {100-PCT:g}% sweeps, >= ${MINNTL:,.0f}, entry = mid {LAG:.0f}ms after we observe the print) ===")
print(f"events with entry mid: {nev}")
print(f"  impact already paid (pre-event mid -> entry mid): {st(impact)}")
for h in HOR:
    print(f"  +{h:4d}s  {st(res[h])}   [bar to beat: +9.00bp]")
print("\n per-coin +30s:")
for c,d in sorted(percoin.items()):
    if 30 in d and len(d[30])>=5:
        x=np.array(d[30]); print(f"   {c:7s} n={len(x):4d} mean={x.mean():+7.2f}bp")
