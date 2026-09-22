import json,math,numpy as np

coins=json.load(open("/tmp/coins.json")); hrs=np.load("/tmp/hrs.npy"); M=np.load("/tmp/oc.npy")
g=M[coins.index("XMR")][hrs==20]
z=(g-g.mean())/g.std();print("n=%d skew=%.2f kurt=%.2f (normal 0/3) -> t-test is fragile"%(len(g),(z**3).mean(),(z**4).mean()))
for C in (9.84,11.90,15.40):
    net=g-C
    k=int((net>0).sum()); n=len(net)
    p=sum(math.comb(n,j) for j in range(k,n+1))/2**n
    r=np.argsort(np.argsort(np.abs(net)))+1; Wp=r[net>0].sum(); mu=n*(n+1)/4; sd=math.sqrt(n*(n+1)*(2*n+1)/24)
    wz=(Wp-mu)/sd; wpv=0.5*math.erfc(wz/math.sqrt(2))
    rng=np.random.default_rng(5); L=7; nb=int(np.ceil(len(net)/L)); bs=[]
    for _ in range(5000):
        s=rng.integers(0,len(net)-L,size=nb)
        bs.append(np.concatenate([net[a:a+L] for a in s])[:len(net)].mean())
    bs=np.array(bs)
    print(f"cost {C:5.2f}: net mean {net.mean():+6.2f}bp  net median {np.median(net):+6.2f}  hit {k}/{len(net)}={k/len(net):.3f} (binom p={p:.3f})"
          f"  Wilcoxon z={wz:+.2f} p={wpv:.3f}  block-boot 95%CI [{np.percentile(bs,2.5):+.2f},{np.percentile(bs,97.5):+.2f}] P(<=0)={np.mean(bs<=0):.4f}")
