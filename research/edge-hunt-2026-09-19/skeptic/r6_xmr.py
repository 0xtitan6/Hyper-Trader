import json,math,numpy as np,datetime as dt
coins=json.load(open("/tmp/coins.json")); hrs=np.load("/tmp/hrs.npy"); T=np.load("/tmp/T.npy")
M=np.load("/tmp/oc.npy"); CC=np.load("/tmp/cc.npy")
i=coins.index("XMR")
x=M[i]; xc=CC[i]
m20=hrs==20
g=x[m20]; t=np.array(T)[m20]
days=np.array([dt.datetime.fromtimestamp(v/1000,dt.UTC).strftime("%Y-%m-%d") for v in t])
mon=np.array([d[:7] for d in days])
def st(y):
    n=len(y); mu=y.mean(); se=y.std(ddof=1)/math.sqrt(n); return n,mu,se,mu/se
print("n=%d gross mean %+.2fbp se %.2f t %+.2f  sd %.1fbp"%(*st(g),g.std(ddof=1)))
print("close->close hr20: n=%d mean %+.2f t %+.2f"%(st(xc[m20])[0],st(xc[m20])[1],st(xc[m20])[3]))
for C,lbl in [(9.84,"claimed all-in 9.84"),(11.39,"my single snap 11.39"),(12.02,"my 12-snap median 12.02"),(15.5,"$10k 15.5")]:
    net=g-C; n,mu,se,tv=st(net)
    print(f"  cost {C:5.2f} ({lbl:<24}) net mean {mu:+6.2f}bp t={tv:+5.2f}  median {np.median(net):+6.2f}  hit {np.mean(net>0):.3f}  P&L@$640 ${mu/1e4*640:.2f}/day")
print("\ngross hit rate %.3f  median gross %+.2f  10%%-trim %+.2f"%(np.mean(g>0),np.median(g),np.mean(np.sort(g)[20:-20])))
print("\ntop-10 days (gross bp): ",[f"{days[k]}:{g[k]:+.0f}" for k in np.argsort(-g)[:10]])
s=g.sum()
for k in (1,3,5,10,20):
    print(f"  drop top {k:2d} days: mean {(s-np.sort(g)[-k:].sum())/(len(g)-k):+6.2f}bp gross -> net@12.02 {(s-np.sort(g)[-k:].sum())/(len(g)-k)-12.02:+6.2f}bp  (top{k} = {np.sort(g)[-k:].sum()/s*100:4.1f}% of sum)")
print("\nby month (gross / net@12.02 / n):")
for mm in sorted(set(mon)):
    y=g[mon==mm]; print(f"  {mm} n={len(y):3d} gross {y.mean():+7.2f} net {y.mean()-12.02:+7.2f} t={st(y)[3]:+5.2f}" if len(y)>2 else f"  {mm} n={len(y)}")
print("\nquarters of the sample (52 trades each):")
for q in range(4):
    y=g[q*52:(q+1)*52]; n,mu,se,tv=st(y)
    print(f"  Q{q+1} {days[q*52]}..{days[min((q+1)*52-1,len(g)-1)]} n={n} gross {mu:+7.2f} t={tv:+5.2f} -> net@12.02 {mu-12.02:+7.2f} t={(mu-12.02)/se:+5.2f}")
print("\nlast 52 / 90 days:")
for k in (52,90,104):
    y=g[-k:]; n,mu,se,tv=st(y)
    print(f"  last {k}: gross {mu:+7.2f} t={tv:+5.2f} -> net@12.02 {mu-12.02:+7.2f} t={(mu-12.02)/se:+5.2f}")
# drop best month
bm=max(set(mon),key=lambda mm:g[mon==mm].mean() if (mon==mm).sum()>5 else -1e9)
y=g[mon!=bm]; n,mu,se,tv=st(y)
print(f"\ndrop best month ({bm}): n={n} gross {mu:+.2f} t={tv:+.2f} -> net@12.02 {mu-12.02:+.2f} t={(mu-12.02)/se:+.2f}")
# XMR trade counts / volume by hour (staleness check)
raw=json.load(open("/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data/XMR_1h_long.json"))
rm={int(r[0]):r for r in raw}
ntr=np.array([rm[v][6] for v in T]); vol=np.array([rm[v][5] for v in T])
print("\nXMR per-hour trade count / base volume (staleness check):")
for h in (7,12,19,20,21):
    print(f"  hr{h:02d}: trades/bar {ntr[hrs==h].mean():7.1f}  vol {vol[hrs==h].mean():9.1f} XMR  (all-hours mean trades {ntr.mean():.1f}, vol {vol.mean():.1f})")
