import json,math,bisect,collections
import numpy as np
D="/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
HOR=[15,30,60,120]
B=collections.defaultdict(lambda:([],[]))
for l in open(D+"/ws_bbo.jsonl"):
    c,t,bid,ask,recv=json.loads(l)
    if ask<=bid: continue
    B[c][0].append(recv); B[c][1].append((bid+ask)/2)
for c in B:
    z=sorted(zip(*B[c])); B[c]=([x[0] for x in z],[x[1] for x in z])
def gm(c,ts,gap=8000):
    a=B[c][0]
    if not a: return None
    i=bisect.bisect_left(a,ts)
    return None if (i>=len(a) or a[i]-ts>gap) else B[c][1][i]
T=[json.loads(l) for l in open(D+"/ws_trades.jsonl")]
T.sort(key=lambda x:(x[0],x[4],x[6]))
sweeps=[];cur=None
for c,side,px,sz,ts,tid,recv in T:
    ntl=float(px)*float(sz)
    if cur and cur[0]==c and cur[1]==side and ts-cur[3]<=500:
        cur[2]+=ntl;cur[3]=ts;cur[5]=max(cur[5],recv);cur[6]+=1
    else:
        if cur: sweeps.append(cur)
        cur=[c,side,ntl,ts,ts,recv,1]
if cur: sweeps.append(cur)
def st(x):
    x=np.asarray(x,float);n=len(x)
    if n<8: return f"n={n:4d} (too few)"
    m=x.mean();s=x.std(ddof=1);se=s/math.sqrt(n)
    return f"n={n:4d} mean={m:+7.2f}bp se={se:5.2f} t={m/se:+6.2f} 95%CI_hi={m+1.96*se:+6.2f}"
BUCK=[(2000,10000),(10000,50000),(50000,200000),(200000,1e6),(1e6,1e12)]
print("=== follow-through by SWEEP SIZE (BBO mids, entry 1s after observation, signed by aggressor) ===")
print("    bar to beat: +9.00bp | maker-only bar: +3.00bp (not available to us)")
for lo,hi in BUCK:
    rows={h:[] for h in HOR}; n=0
    for c,side,ntl,tend,tstart,recv,nf in sweeps:
        if not (lo<=ntl<hi): continue
        sgn=1.0 if side=="B" else -1.0
        me=gm(c,int(recv+1000))
        if me is None: continue
        n+=1
        for h in HOR:
            mh=gm(c,int(recv+1000+h*1000))
            if mh is not None: rows[h].append(sgn*(mh-me)/me*1e4)
    lab=f"${lo/1000:.0f}k-{'inf' if hi>1e11 else f'${hi/1000:.0f}k'}"
    print(f"\n  sweep {lab:16s} events={n}")
    for h in HOR: print(f"    +{h:4d}s {st(rows[h])}")
