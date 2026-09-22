"""Robustness: is the one Bonferroni-surviving drift (XMR 20:00 UTC) real, or outliers?"""
import json, os, math, datetime as dt
import numpy as np
D = os.path.dirname(os.path.abspath(__file__)) + "/data"
COINS = ["BTC","ETH","HYPE","ZEC","SOL","NEAR","XRP","LIT","PUMP","UNI","AAVE","XMR"]
FEE = 9.0
raw = {c: {int(r[0]): r for r in json.load(open(f"{D}/{c}_1h_long.json"))} for c in COINS}
common = None
for c,m in raw.items():
    s=set(m); common = s if common is None else (common & s)
grid=np.array(sorted(common))
d=np.diff(grid)==3600000; runs,st=[],0
for i,ok in enumerate(d):
    if not ok: runs.append((st,i)); st=i+1
runs.append((st,len(grid)-1)); b0,b1=max(runs,key=lambda r:r[1]-r[0]); grid=grid[b0:b1+1]
O={c:np.array([raw[c][t][1] for t in grid]) for c in COINS}
C={c:np.array([raw[c][t][4] for t in grid]) for c in COINS}
hours=np.array([dt.datetime.fromtimestamp(t/1000,dt.UTC).hour for t in grid])
mon=np.array([dt.datetime.fromtimestamp(t/1000,dt.UTC).strftime("%Y-%m") for t in grid])
ROC={c:(C[c]-O[c])/O[c]*1e4 for c in COINS}
def tt(x):
    x=np.asarray(x,float); n=len(x); m=x.mean(); s=x.std(ddof=1); return n,m,s,m/(s/math.sqrt(n))

print("MULTIPLE TESTING SCOPE: 12 coins x 24 hours = 288 tests.")
print("Bonferroni threshold = 0.05/288 = %.2e\n"%(0.05/288))

for coin,h in [("XMR",20),("ZEC",20),("BTC",20),("NEAR",0)]:
    msk=(hours==h)
    x=ROC[coin][msk]; mm=mon[msk]
    n,m,s,t=tt(x)
    print(f"--- {coin} {h:02d}:00 UTC ---")
    print(f"  n={n} mean={m:+.2f}bp sd={s:.1f} t={t:+.2f} net vs 9bp={m-FEE:+.2f}")
    print(f"  median={np.median(x):+.2f}bp  hitrate={np.mean(x>0):.3f}  "
          f"10%trim mean={np.mean(np.sort(x)[n//10:-(n//10)]):+.2f}bp")
    srt=np.sort(x)
    print(f"  drop 5 best days -> mean={srt[:-5].mean():+.2f}bp t={tt(srt[:-5])[3]:+.2f}")
    print(f"  drop 3 best days -> mean={srt[:-3].mean():+.2f}bp t={tt(srt[:-3])[3]:+.2f}")
    print(f"  top5 days bp: {np.round(srt[-5:],1)}   bot5: {np.round(srt[:5],1)}")
    # contribution share of top 5
    tot=x.sum(); print(f"  top-5 days are {srt[-5:].sum()/tot*100:.0f}% of the total sum")
    half=len(x)//2
    n1,m1,_,t1=tt(x[:half]); n2,m2,_,t2=tt(x[half:])
    print(f"  split-half: H1 n={n1} {m1:+.2f}bp t={t1:+.2f} | H2 n={n2} {m2:+.2f}bp t={t2:+.2f}")
    print("  by month:", " ".join(f"{k}:{np.mean(x[mm==k]):+.0f}" for k in sorted(set(mm))))
    # adjacent hours - a real session effect should smear
    for hh in (h-2,h-1,h,h+1,h+2):
        hh%=24
        y=ROC[coin][hours==hh]; print(f"    hr {hh:02d}: {y.mean():+7.2f}bp t={tt(y)[3]:+5.2f}")
    print()

print("=== index hour-20 robustness (the max-|t| pooled hour) ===")
IDX=np.nanmean(np.vstack([ROC[c] for c in COINS]),axis=0)
x=IDX[hours==20]; n,m,s,t=tt(x); srt=np.sort(x)
print(f"n={n} mean={m:+.2f} t={t:+.2f} median={np.median(x):+.2f} hit={np.mean(x>0):.3f}")
print(f"drop 5 best -> {srt[:-5].mean():+.2f}bp t={tt(srt[:-5])[3]:+.2f}; drop 10 best -> {srt[:-10].mean():+.2f}bp t={tt(srt[:-10])[3]:+.2f}")
print(f"top-5 days = {srt[-5:].sum()/x.sum()*100:.0f}% of total")
mm=mon[hours==20]; print("by month:"," ".join(f"{k}:{np.mean(x[mm==k]):+.0f}" for k in sorted(set(mm))))

print("\n=== permutation test: how often does the BEST of 288 coin-hour t-stats exceed 4.73? ===")
rng=np.random.default_rng(7)
# block bootstrap: shuffle the DAY labels jointly across coins (preserves cross-coin corr,
# destroys hour-of-day alignment) by circularly shifting each coin's series by a random
# multiple of 1 hour - conservative, keeps autocorrelation
M=np.vstack([ROC[c] for c in COINS])
maxts=[]
for it in range(400):
    sh=rng.integers(1,M.shape[1])
    Ms=np.roll(M,sh,axis=1)
    best=0
    for ci in range(len(COINS)):
        for h in range(24):
            y=Ms[ci][hours==h]; tv=abs(y.mean()/(y.std(ddof=1)/math.sqrt(len(y))))
            best=max(best,tv)
    maxts.append(best)
maxts=np.array(maxts)
print(f"400 circular-shift nulls: max|t| distribution mean={maxts.mean():.2f} "
      f"p50={np.percentile(maxts,50):.2f} p95={np.percentile(maxts,95):.2f} max={maxts.max():.2f}")
print(f"fraction of nulls with max|t| >= 4.73 (XMR h20): {np.mean(maxts>=4.73):.3f}")
print(f"fraction of nulls with max|t| >= 2.25 (index h20): {np.mean(maxts>=2.25):.3f}")
