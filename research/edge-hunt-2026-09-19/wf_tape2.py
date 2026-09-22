import json,math,bisect,sys,collections
import numpy as np
D="/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
LAG=float(sys.argv[1]) if len(sys.argv)>1 else 1000.0
PCT=float(sys.argv[2]) if len(sys.argv)>2 else 99.0
MINNTL=float(sys.argv[3]) if len(sys.argv)>3 else 5000.0
HOR=[5,15,30,60,120,300,600]
B=collections.defaultdict(lambda:([],[],[]))   # coin -> (recv_ts, mid, spread_bp)
n=0
for l in open(D+"/ws_bbo.jsonl"):
    c,t,bid,ask,recv=json.loads(l)
    if ask<=bid: continue
    ts,m,s=B[c]; ts.append(recv); m.append((bid+ask)/2); s.append((ask-bid)/((bid+ask)/2)*1e4); n+=1
for c in B:
    z=sorted(zip(*B[c])); B[c]=([x[0] for x in z],[x[1] for x in z],[x[2] for x in z])
print("bbo rows",n,{c:len(B[c][0]) for c in B})
def gm(c,ts,gap=8000):
    a=B[c][0]
    if not a: return None,None
    i=bisect.bisect_left(a,ts)
    if i>=len(a) or a[i]-ts>gap: return None,None
    return B[c][1][i],B[c][2][i]
T=[json.loads(l) for l in open(D+"/ws_trades.jsonl")]
T.sort(key=lambda x:(x[0],x[4]))
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
res={h:[] for h in HOR}; imp=[]; spr=[]; nev=0; sizes=[]
percoin=collections.defaultdict(lambda:{h:[] for h in HOR})
for c,side,ntl,tend,tstart,recv,nf in sweeps:
    v=bycoin[c]
    if len(v)<150: continue
    if ntl<np.percentile(v,PCT) or ntl<MINNTL: continue
    sgn=1.0 if side=="B" else -1.0
    me,sp=gm(c,int(recv+LAG))
    if me is None: continue
    m0,_=gm(c,int(recv-3000),gap=4000)
    nev+=1; sizes.append(ntl); spr.append(sp)
    if m0: imp.append(sgn*(me-m0)/m0*1e4)
    for h in HOR:
        mh,_=gm(c,int(recv+LAG+h*1000))
        if mh is None: continue
        r=sgn*(mh-me)/me*1e4
        res[h].append(r); percoin[c][h].append(r)
def st(x):
    x=np.asarray(x,float);n=len(x)
    if n<10: return f"n={n:4d} (too few)"
    m=x.mean();s=x.std(ddof=1)
    return f"n={n:4d} mean={m:+7.2f}bp sd={s:6.2f} t={m/(s/math.sqrt(n)):+6.2f} med={np.median(x):+6.2f} win%={100*(x>0).mean():4.1f}"
print(f"\n=== LIVE TAPE: whale sweeps, top {100-PCT:g}% per coin, >=${MINNTL:,.0f}; entry = MID {LAG:.0f}ms after we observe the print ===")
print(f"events={nev}  median sweep notional=${np.median(sizes):,.0f}  p90=${np.percentile(sizes,90):,.0f}  max=${max(sizes):,.0f}")
print(f"mean spread at entry = {np.mean(spr):.2f}bp   (taker round trip = 9.00bp)")
print(f"impact already paid before we can act (mid -3s -> mid +{LAG:.0f}ms): {st(imp)}")
for h in HOR: print(f"  +{h:4d}s signed-by-aggressor  {st(res[h])}   [bar: +9.00bp]")
print("\nper-coin +30s:")
for c,d in sorted(percoin.items()):
    if len(d[30])>=10: x=np.array(d[30]); print(f"   {c:7s} n={len(x):4d} mean={x.mean():+7.2f}bp t={x.mean()/(x.std(ddof=1)/math.sqrt(len(x))):+5.2f}")
