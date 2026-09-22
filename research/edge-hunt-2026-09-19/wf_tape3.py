import json,math,bisect,sys,collections
import numpy as np
D="/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
LAG=float(sys.argv[1]) if len(sys.argv)>1 else 1000.0
PCT=float(sys.argv[2]) if len(sys.argv)>2 else 99.0
MINNTL=float(sys.argv[3]) if len(sys.argv)>3 else 20000.0
HOR=[5,15,30,60,120,300,600]
T=[json.loads(l) for l in open(D+"/ws_trades.jsonl")]
T.sort(key=lambda x:(x[0],x[4],x[6]))
# per-coin trade-derived mid proxy: (last buy-aggressor px + last sell-aggressor px)/2
P=collections.defaultdict(lambda:([],[]))
lastB={}; lastA={}
for c,side,px,sz,ts,tid,recv in T:
    p=float(px)
    if side=="B": lastB[c]=p
    else: lastA[c]=p
    if c in lastB and c in lastA:
        ts_,m_=P[c]; ts_.append(recv); m_.append((lastB[c]+lastA[c])/2)
def gp(c,ts,gap=20000):
    a=P[c][0]
    if not a: return None
    i=bisect.bisect_left(a,ts)
    if i>=len(a) or a[i]-ts>gap: return None
    return P[c][1][i]
sweeps=[];cur=None
for c,side,px,sz,ts,tid,recv in T:
    ntl=float(px)*float(sz)
    if cur and cur[0]==c and cur[1]==side and ts-cur[3]<=500:
        cur[2]+=ntl;cur[3]=ts;cur[5]=max(cur[5],recv);cur[6]+=1
    else:
        if cur: sweeps.append(cur)
        cur=[c,side,ntl,ts,ts,recv,1]
if cur: sweeps.append(cur)
bycoin=collections.defaultdict(list)
for s in sweeps: bycoin[s[0]].append(s[2])
span=(max(x[6] for x in T)-min(x[6] for x in T))/60000
print(f"tape {len(T)} trades over {span:.1f} min, {len(sweeps)} sweeps, coins={sorted(bycoin)}")
res={h:[] for h in HOR}; imp=[]; sizes=[]; nev=0
pc=collections.defaultdict(lambda:collections.defaultdict(list))
byside={"B":{h:[] for h in HOR},"A":{h:[] for h in HOR}}
for c,side,ntl,tend,tstart,recv,nf in sweeps:
    v=bycoin[c]
    if len(v)<150: continue
    if ntl<np.percentile(v,PCT) or ntl<MINNTL: continue
    sgn=1.0 if side=="B" else -1.0
    me=gp(c,int(recv+LAG))
    if me is None: continue
    m0=gp(c,int(recv-5000),gap=6000)
    nev+=1; sizes.append(ntl)
    if m0: imp.append(sgn*(me-m0)/m0*1e4)
    for h in HOR:
        mh=gp(c,int(recv+LAG+h*1000))
        if mh is None: continue
        r=sgn*(mh-me)/me*1e4
        res[h].append(r); pc[c][h].append(r); byside[side][h].append(r)
def st(x):
    x=np.asarray(x,float);n=len(x)
    if n<10: return f"n={n:4d} (too few)"
    m=x.mean();s=x.std(ddof=1); se=s/math.sqrt(n)
    return f"n={n:4d} mean={m:+7.2f}bp se={se:5.2f} sd={s:6.2f} t={m/se:+6.2f} 95%CI[{m-1.96*se:+6.2f},{m+1.96*se:+6.2f}]"
print(f"\n=== LIVE TAPE (trade-derived mid): top {100-PCT:g}% sweeps per coin, >=${MINNTL:,.0f}, entry = {LAG:.0f}ms after we observe the print ===")
print(f"events={nev} median=${np.median(sizes):,.0f} p90=${np.percentile(sizes,90):,.0f} max=${max(sizes):,.0f}")
print(f"impact already gone by entry: {st(imp)}")
for h in HOR: print(f"  +{h:4d}s  {st(res[h])}  [bar +9.00]")
print("\n  buy-sweeps only:"); 
for h in [15,30,60,300]: print(f"   +{h:4d}s {st(byside['B'][h])}")
print("  sell-sweeps only (sign flipped so + = follow-through down):")
for h in [15,30,60,300]: print(f"   +{h:4d}s {st(byside['A'][h])}")
print("\nper-coin +30s:")
for c,d in sorted(pc.items()):
    if len(d[30])>=10: x=np.array(d[30]); print(f"   {c:7s} n={len(x):4d} mean={x.mean():+7.2f}bp t={x.mean()/(x.std(ddof=1)/math.sqrt(len(x))):+5.2f}")
