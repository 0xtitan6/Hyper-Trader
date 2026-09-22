import json,math,datetime as dt,numpy as np
d=json.load(open("/tmp/xmr_bybit_1h.json"))
t=np.array(sorted(int(k) for k in d))
O=np.array([d[str(x)][0] for x in t]); C=np.array([d[str(x)][3] for x in t])
h=np.array([dt.datetime.fromtimestamp(x/1000,dt.UTC).hour for x in t])
R=(C-O)/O*1e4
CUT=int(dt.datetime(2026,2,22,19,tzinfo=dt.UTC).timestamp()*1000)
IS=R[(t>=CUT)&(h==20)]; OOS=R[(t<CUT)&(h==20)]
def st(x): return len(x),x.mean(),x.std(ddof=1)
n1,m1,s1=st(IS); n2,m2,s2=st(OOS)
se=math.sqrt(s1**2/n1+s2**2/n2)
print(f"IS  (HL mining window)  n={n1} mean={m1:+.2f} sd={s1:.1f}")
print(f"OOS (2022-01..2026-02)  n={n2} mean={m2:+.2f} sd={s2:.1f}")
print(f"IS - OOS = {m1-m2:+.2f}bp, se={se:.2f}, Welch t = {(m1-m2)/se:+.2f}  -> the discovery window is NOT the same population")
# block bootstrap on OOS (7-day blocks of daily hr20 obs)
rng=np.random.default_rng(7); B=5000; nb=n2//7
boots=[]
for _ in range(B):
    st_=rng.integers(0,n2-7,nb)
    s=np.concatenate([OOS[i:i+7] for i in st_])
    boots.append(s.mean()-9.84)
boots=np.array(boots)
print(f"\nOOS hr20 NET (cost 9.84bp) block-bootstrap: mean={boots.mean():+.2f}bp 95% CI [{np.percentile(boots,2.5):+.2f},{np.percentile(boots,97.5):+.2f}]  P(net>0)={np.mean(boots>0):.4f}")
print(f"  P(OOS net >= claimed +15.71bp) = {np.mean(boots>=15.71):.5f}")
# regime: segment drift vs hr20 mean
segs=[("2022",(2022,1,14),(2023,1,1)),("2023",(2023,1,1),(2024,1,1)),("2024",(2024,1,1),(2025,1,1)),
      ("2025H1",(2025,1,1),(2025,7,1)),("2025H2",(2025,7,1),(2026,1,1)),
      ("2026pre",(2026,1,1),(2026,2,22)),("HLwin",(2026,2,22),(2026,9,20))]
print("\nsegment   XMR drift bp/day   hr20 mean bp   n")
xs=[];ys=[]
for l,a,b in segs:
    A=int(dt.datetime(*a,tzinfo=dt.UTC).timestamp()*1000);B_=int(dt.datetime(*b,tzinfo=dt.UTC).timestamp()*1000)
    m=(t>=A)&(t<B_)
    drift=sum(R[m&(h==hh)].mean() for hh in range(24))
    x20=R[m&(h==20)]
    xs.append(drift); ys.append(x20.mean())
    print(f"  {l:8} {drift:+9.1f}        {x20.mean():+8.2f}     {len(x20)}")
print(f"  corr(segment daily drift, segment hr20 mean) = {np.corrcoef(xs,ys)[0,1]:+.3f} over {len(xs)} segments")
print(f"  slope: hr20 mean = {np.polyfit(xs,ys,1)[0]:.3f} x daily drift + {np.polyfit(xs,ys,1)[1]:.2f}")
print(f"  (a pure 1/24 share of the drift would be slope 0.042; a 'clock' effect would be slope ~0)")
