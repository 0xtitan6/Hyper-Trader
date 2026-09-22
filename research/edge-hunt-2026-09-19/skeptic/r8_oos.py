import json,math,numpy as np,datetime as dt
coins=json.load(open("/tmp/coins.json")); hrs=np.load("/tmp/hrs.npy"); T=np.load("/tmp/T.npy")
M=np.load("/tmp/oc.npy"); cost36=json.load(open("/tmp/cost36.json"))
COST=np.array([cost36[c]["a640"] if cost36[c]["a640"]==cost36[c]["a640"] else 12.0 for c in coins])
N=M.shape[1]; half=N//2
def cell(ci,h,lo=0,hi=N):
    y=M[ci][lo:hi][hrs[lo:hi]==h]; n=len(y); mu=y.mean(); se=y.std(ddof=1)/math.sqrt(n)
    return n,mu,se,mu/se

print("=== sibling cell XMR hr07 (in-sample t=+4.56, statistically the twin of hr20) ===")
for lbl,lo,hi in [("full",0,N),("H1",0,half),("H2",half,N),("last 52d",N-52*24,N)]:
    n,mu,se,t=cell(coins.index("XMR"),7,lo,hi)
    print(f"  {lbl:<9} n={n:3d} gross {mu:+7.2f} t={t:+5.2f} -> net@11.9 {mu-11.9:+7.2f} t={(mu-11.9)/se:+5.2f}")
print("=== XMR hr20 same split ===")
for lbl,lo,hi in [("full",0,N),("H1",0,half),("H2",half,N),("last 52d",N-52*24,N)]:
    n,mu,se,t=cell(coins.index("XMR"),20,lo,hi)
    print(f"  {lbl:<9} n={n:3d} gross {mu:+7.2f} t={t:+5.2f} -> net@11.9 {mu-11.9:+7.2f} t={(mu-11.9)/se:+5.2f}")

print("\n=== SPLIT-HALF OOS OF THE MINING PROCEDURE (per coin, best hour on H1 -> trade in H2) ===")
tot=[];rows=[]
for ci,c in enumerate(coins):
    best=None
    for h in range(24):
        n,mu,se,t=cell(ci,h,0,half)
        if best is None or abs(t)>abs(best[3]): best=(h,mu,se,t)
    h,mu,se,t=best; sgn=1 if mu>0 else -1
    n2,mu2,se2,t2=cell(ci,h,half,N)
    net=sgn*mu2-COST[ci]
    rows.append((c,h,sgn,t,mu2*sgn,net,n2))
    tot.append(np.array([sgn*v-COST[ci] for v in M[ci][half:][hrs[half:]==h]]))
rows.sort(key=lambda r:-abs(r[3]))
print(f"{'coin':<9}{'hr':>3}{'dir':>4}{'H1 t':>7}{'H2 gross':>10}{'H2 net':>8}")
for c,h,s,t,g2,net,n2 in rows[:12]:
    print(f"{c:<9}{h:>3}{('L' if s>0 else 'S'):>4}{t:>+7.2f}{g2:>+10.2f}{net:>+8.2f}")
A=np.concatenate(tot); print(f"\n  ALL 36 picks pooled OOS: n={len(A)} net mean {A.mean():+.2f}bp t={A.mean()/(A.std(ddof=1)/math.sqrt(len(A))):+.2f}")
g=np.array([r[4] for r in rows]); print(f"  per-coin OOS gross mean {g.mean():+.2f}bp, {np.mean(g>0)*100:.0f}% of 36 picks positive OOS")
nt=np.array([r[5] for r in rows]); print(f"  per-coin OOS net   mean {nt.mean():+.2f}bp, {np.mean(nt>0)*100:.0f}% of 36 picks net-positive")
# top-1 pick across the whole grid on H1
bi=max(((ci,h)+cell(ci,h,0,half) for ci in range(len(coins)) for h in range(24)),key=lambda r:abs(r[5]))
ci,h=bi[0],bi[1]; sgn=1 if bi[3]>0 else -1
n2,mu2,se2,t2=cell(ci,h,half,N)
print(f"  GRID top-1 on H1 = {coins[ci]} hr{h:02d} ({'L' if sgn>0 else 'S'}) H1 t={bi[5]:+.2f} -> H2 gross {sgn*mu2:+.2f}bp net {sgn*mu2-COST[ci]:+.2f}bp t={(sgn*mu2-COST[ci])/se2:+.2f}")

print("\n=== how much in-sample GROSS does pure-noise mining of 864 cells manufacture? ===")
masks=[np.where(hrs==h)[0] for h in range(24)]
rng=np.random.default_rng(3)
L=168; nb=int(np.ceil(N/L)); res=[]
for r in range(400):
    starts=rng.integers(0,N-L,size=nb)
    idx=np.concatenate([np.arange(s,s+L) for s in starts])[:N]
    Ms=M[:,idx]
    me=np.empty((len(coins),24)); se=np.empty((len(coins),24))
    for hh in range(24):
        y=Ms[:,masks[hh]]; me[:,hh]=y.mean(1); se[:,hh]=y.std(1,ddof=1)/math.sqrt(y.shape[1])
    t=me/se; a,b=np.unravel_index(np.argmax(np.abs(t)),t.shape)
    res.append((abs(me[a,b]),abs(t[a,b]),COST[a]))
res=np.array(res)
print(f"  null: |gross| of the max-|t| cell  p50={np.percentile(res[:,0],50):.2f}bp  p90={np.percentile(res[:,0],90):.2f}  p95={np.percentile(res[:,0],95):.2f}")
print(f"  observed XMR hr20 gross = 25.51bp  -> excess over median noise-mining = {25.51-np.percentile(res[:,0],50):+.2f}bp vs the 9bp fee bar")
print(f"  P(noise-mined |gross| >= 25.51) = {np.mean(res[:,0]>=25.51):.3f}")
