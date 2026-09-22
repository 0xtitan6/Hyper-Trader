"""KILL TEST: is the hour-20 'drift' just bid-ask bounce in the candle OPEN price?
close(h-1)->close(h) uses two closes, both subject to the same bounce, so the bias cancels.
open(h)->close(h) does NOT: if the first print of the hour lands at the bid, open is
biased low and open->close is biased positive by ~half a spread.
"""
import json, os, math, glob, datetime as dt
import numpy as np
D = os.path.dirname(os.path.abspath(__file__)) + "/data"
FEE=9.0
raw={}
for f in sorted(glob.glob(f"{D}/*_1h_long.json")):
    c=os.path.basename(f).replace("_1h_long.json","")
    rows=json.load(open(f))
    if len(rows)<4800: continue
    raw[c]={int(r[0]):r for r in rows}
COINS=sorted(raw)
common=None
for c,m in raw.items():
    s=set(m); common=s if common is None else (common&s)
grid=np.array(sorted(common))
d=np.diff(grid)==3600000; runs,st=[],0
for i,ok in enumerate(d):
    if not ok: runs.append((st,i)); st=i+1
runs.append((st,len(grid)-1)); b0,b1=max(runs,key=lambda r:r[1]-r[0]); grid=grid[b0:b1+1]
O={c:np.array([raw[c][t][1] for t in grid]) for c in COINS}
C={c:np.array([raw[c][t][4] for t in grid]) for c in COINS}
hours=np.array([dt.datetime.fromtimestamp(t/1000,dt.UTC).hour for t in grid])
mon=np.array([dt.datetime.fromtimestamp(t/1000,dt.UTC).strftime("%Y-%m") for t in grid])
ROC={c:(C[c]-O[c])/O[c]*1e4 for c in COINS}                    # open->close (bounce-biased)
RCC={c:np.concatenate([[np.nan],np.diff(C[c])/C[c][:-1]*1e4]) for c in COINS}  # close->close
def tt(x):
    x=np.asarray(x,float); x=x[~np.isnan(x)]; n=len(x); m=x.mean(); s=x.std(ddof=1)
    return n,m,s,m/(s/math.sqrt(n))

print("=== average open->close MINUS close->close, pooled over ALL hours (the bounce bias) ===")
for c in ["XMR","ZEC","XPL","BTC","ETH","PAXG"]:
    a=np.nanmean(ROC[c]); b=np.nanmean(RCC[c])
    print(f"  {c:<6} mean open->close {a:+6.2f}bp   mean close->close {b:+6.2f}bp   "
          f"bias {a-b:+6.2f}bp/bar")
idxoc=np.nanmean(np.vstack([ROC[c] for c in COINS]),axis=0)
idxcc=np.nanmean(np.vstack([RCC[c] for c in COINS]),axis=0)
print(f"  INDEX  mean open->close {np.nanmean(idxoc):+6.2f}bp   close->close "
      f"{np.nanmean(idxcc):+6.2f}bp   bias {np.nanmean(idxoc)-np.nanmean(idxcc):+6.2f}bp/bar")

print("\n=== hour-20, both definitions ===")
print(f"{'coin':<8} {'OC mean':>8} {'OC t':>6} | {'CC mean':>8} {'CC t':>6} | {'CC net-9':>8}")
ccs=[]
for c in COINS:
    n1,m1,_,t1=tt(ROC[c][hours==20]); n2,m2,_,t2=tt(RCC[c][hours==20])
    ccs.append((c,m2,t2))
    if c in ("XMR","ZEC","XPL","BTC","ETH","ENA","INJ","TAO","NEAR","CRV","ZRO","VVV","HYPE","PAXG"):
        print(f"{c:<8} {m1:>+8.2f} {t1:>+6.2f} | {m2:>+8.2f} {t2:>+6.2f} | {m2-FEE:>+8.2f}")
ts=np.array([r[2] for r in ccs]); ms=np.array([r[1] for r in ccs])
print(f"\nclose->close hour-20 across {len(COINS)} coins: mean effect {ms.mean():+.2f}bp, "
      f"mean t {ts.mean():+.2f}, frac t>0 {np.mean(ts>0):.2f}, frac t>2 {np.mean(ts>2):.2f}")
n,m,s,t=tt(idxcc[hours==20]); print(f"INDEX hour-20 close->close: n={n} {m:+.2f}bp t={t:+.2f} net-9 {m-FEE:+.2f}")
n,m,s,t=tt(idxoc[hours==20]); print(f"INDEX hour-20 open->close : n={n} {m:+.2f}bp t={t:+.2f} net-9 {m-FEE:+.2f}")

print("\n=== full 864-grid on close->close, top 10 |t| ===")
allt=[]
for c in COINS:
    for h in range(24):
        n,m,s,t=tt(RCC[c][hours==h]); allt.append((abs(t),t,c,h,m))
allt.sort(reverse=True)
for a,t,c,h,m in allt[:10]:
    print(f"  {c:<9} hr {h:02d} mean={m:+8.2f}bp t={t:+5.2f} net-9={m-FEE:+8.2f}")

print("\n=== permutation null, close->close grid ===")
M=np.vstack([RCC[c] for c in COINS]); M=M[:,1:]; hh=hours[1:]
rng=np.random.default_rng(3); maxts=[]
for it in range(300):
    Ms=np.roll(M,rng.integers(1,M.shape[1]),axis=1); best=0.0
    for ci in range(M.shape[0]):
        row=Ms[ci]
        for h in range(24):
            y=row[hh==h]; tv=abs(y.mean()/(y.std(ddof=1)/math.sqrt(len(y))))
            if tv>best: best=tv
    maxts.append(best)
maxts=np.array(maxts)
print(f"max|t| null p50={np.percentile(maxts,50):.2f} p95={np.percentile(maxts,95):.2f} max={maxts.max():.2f}")
print(f"observed best {allt[0][2]} hr{allt[0][3]:02d} |t|={allt[0][0]:.2f} -> FW p={np.mean(maxts>=allt[0][0]):.3f}")
for a,t,c,h,m in allt[:4]:
    print(f"   {c} hr{h:02d} |t|={a:.2f} FW p={np.mean(maxts>=a):.3f}")

print("\n=== XMR hour-20 close->close detail ===")
x=RCC["XMR"][hours==20]; x=x[~np.isnan(x)]; n,m,s,t=tt(x); srt=np.sort(x)
print(f"n={n} mean={m:+.2f}bp t={t:+.2f} median={np.median(x):+.2f} hit={np.mean(x>0):.3f}")
print(f"drop 5 best -> {srt[:-5].mean():+.2f} t={tt(srt[:-5])[3]:+.2f}")
mm=mon[hours==20][-len(x):]
print("by month:"," ".join(f"{k}:{np.mean(x[mm==k]):+.0f}" for k in sorted(set(mm))))
half=len(x)//2
print(f"split-half: H1 {x[:half].mean():+.2f}bp t={tt(x[:half])[3]:+.2f} | H2 {x[half:].mean():+.2f}bp t={tt(x[half:])[3]:+.2f}")
