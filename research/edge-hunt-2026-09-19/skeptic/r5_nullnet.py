import json,math,numpy as np
coins=json.load(open("/tmp/coins.json")); hrs=np.load("/tmp/hrs.npy")
M=np.load("/tmp/oc.npy")   # 36 x 5000 open->close bp
cost36=json.load(open("/tmp/cost36.json"))
N=M.shape[1]; masks=[np.where(hrs==h)[0] for h in range(24)]
# per-coin all-in cost at $640 (fee 9 + measured RT slip + max(funding,0)); fall back to 12 if THIN
COST=np.array([cost36[c]["a640"] if cost36[c]["a640"]==cost36[c]["a640"] else 12.0 for c in coins])
XMR=coins.index("XMR")
print("cost@640 bp: XMR %.2f  median %.2f  min %.2f (%s)  max %.2f"%(
    COST[XMR],np.median(COST),COST.min(),coins[int(np.argmin(COST))],COST.max()))

def grid_stats(Mx):
    means=np.empty((Mx.shape[0],24)); ses=np.empty((Mx.shape[0],24))
    for h in range(24):
        y=Mx[:,masks[h]]; n=y.shape[1]
        means[:,h]=y.mean(1); ses[:,h]=y.std(1,ddof=1)/math.sqrt(n)
    return means,ses

m0,s0=grid_stats(M)
t0=m0/s0
net0=np.abs(m0)-COST[:,None]
nt0=net0/s0
ci,hi=np.unravel_index(np.argmax(np.abs(t0)),t0.shape)
print("\nOBSERVED best |t| cell: %s hr%02d  gross %+.2fbp t=%+.2f  net %+.2fbp net-t %+.2f"%(
    coins[ci],hi,m0[ci,hi],t0[ci,hi],net0[ci,hi],nt0[ci,hi]))
cj,hj=np.unravel_index(np.argmax(net0),net0.shape)
print("OBSERVED best NET cell : %s hr%02d  gross %+.2fbp  net %+.2fbp net-t %+.2f"%(
    coins[cj],hj,m0[cj,hj],net0[cj,hj],nt0[cj,hj]))

# ---- proper null: stationary block bootstrap, common block starts across coins ----
def run_null(L,reps,seed):
    rng=np.random.default_rng(seed)
    nb=int(np.ceil(N/L))
    out=[]
    for r in range(reps):
        starts=rng.integers(0,N-L,size=nb)
        idx=np.concatenate([np.arange(s,s+L) for s in starts])[:N]
        Ms=M[:,idx]
        m,s=grid_stats(Ms); t=m/s; net=np.abs(m)-COST[:,None]; nt=net/s
        a,b=np.unravel_index(np.argmax(np.abs(t)),t.shape)
        out.append((np.abs(t).max(), net.max(), nt.max(), net[a,b], nt[a,b]))
    return np.array(out)

for L in (168,336):
    R=run_null(L,400,7+L)
    lbl=f"block L={L}h ({L//24}d), 400 reps"
    print(f"\n--- NULL {lbl} ---")
    for name,col,obs in [("max|gross t|",0,abs(t0[ci,hi])),
                         ("max net bp",1,net0[cj,hj]),
                         ("max net-t",2,nt0[cj,hj]),
                         ("net bp OF the max-|t| cell",3,net0[ci,hi]),
                         ("net-t  OF the max-|t| cell",4,nt0[ci,hi])]:
        v=R[:,col]
        print(f"  {name:<28} null p50={np.percentile(v,50):+7.2f} p90={np.percentile(v,90):+7.2f} "
              f"p95={np.percentile(v,95):+7.2f} max={v.max():+7.2f} | observed={obs:+7.2f}  FW p={np.mean(v>=obs):.3f}")
