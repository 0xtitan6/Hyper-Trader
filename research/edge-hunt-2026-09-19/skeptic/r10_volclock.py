import json,math,numpy as np
coins=json.load(open("/tmp/coins.json")); hrs=np.load("/tmp/hrs.npy"); M=np.load("/tmp/oc.npy")
N=M.shape[1]; half=N//2
A=np.abs(M).mean(0)            # 36-coin mean |open->close| per bar
gm=A.mean()
prof=np.array([A[hrs==h].mean() for h in range(24)])
print("vol clock: loudest hr%02d %.1fbp (%.2fx)  quietest hr%02d %.1fbp (%.2fx)  ratio %.2fx"%(
    prof.argmax(),prof.max(),prof.max()/gm,prof.argmin(),prof.min(),prof.min()/gm,prof.max()/prof.min()))
v1=np.array([A[:half][hrs[:half]==h].mean() for h in range(24)])
v2=np.array([A[half:][hrs[half:]==h].mean() for h in range(24)])
print("split-half corr of vol profile = %+.3f"%np.corrcoef(v1,v2)[0,1])
top=np.argsort(-v1)[:6]; bot=np.argsort(v1)[:6]
print("H1 top6 hours",sorted(top),"-> H2 %.1fbp ; H1 bot6"%v2[top].mean(),sorted(bot),"-> H2 %.1fbp  ratio %.2fx"%(v2[bot].mean(),v2[top].mean()/v2[bot].mean()))
# 12-coin index drift check
IDX12=["BTC","ETH","HYPE","ZEC","SOL","NEAR","XRP","LIT","PUMP","UNI","AAVE","XMR"]
I=M[[coins.index(c) for c in IDX12]].mean(0)
print("\n12-coin index drift by hour: sd=%.1fbp"%I.std(ddof=1))
res=[]
for h in range(24):
    y=I[hrs==h]; mu=y.mean(); t=mu/(y.std(ddof=1)/math.sqrt(len(y))); res.append((h,mu,t,len(y)))
for h,mu,t,n in sorted(res,key=lambda r:-abs(r[2]))[:5]: print(f"  hr{h:02d} {mu:+7.2f}bp t={t:+5.2f} n={n}")
print("  max|t| over 24 = %.2f (expected max of 24 iid normals ~2.40)"%max(abs(r[2]) for r in res))
p1=np.array([I[:half][hrs[:half]==h].mean() for h in range(24)])
p2=np.array([I[half:][hrs[half:]==h].mean() for h in range(24)])
print("  split-half corr of the DRIFT profile = %+.3f"%np.corrcoef(p1,p2)[0,1])
# does cost scale with vol? cross-sectional: coin vol vs measured spread
cost=json.load(open("/tmp/cost36.json"))
vol=np.array([np.abs(M[i]).mean() for i in range(len(coins))])
sp=np.array([cost[c]["spread"] for c in coins]); s640=np.array([cost[c]["s640"] or np.nan for c in coins])
print("\ncross-sectional corr(coin mean |1h move|, live spread bp) = %+.3f ; vs RT slip@640 = %+.3f (n=%d)"%(
    np.corrcoef(vol,sp)[0,1], np.corrcoef(vol[~np.isnan(s640)],s640[~np.isnan(s640)])[0,1], len(coins)))
