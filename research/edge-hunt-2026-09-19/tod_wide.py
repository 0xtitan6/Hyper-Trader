"""Hour-20 'US cash close' coherence test across 40 coins + full 40x24 mining scope."""
import json, os, math, glob, datetime as dt
import numpy as np
D = os.path.dirname(os.path.abspath(__file__)) + "/data"
FEE = 9.0
files = sorted(glob.glob(f"{D}/*_1h_long.json"))
raw = {}
for f in files:
    c = os.path.basename(f).replace("_1h_long.json","")
    rows = json.load(open(f))
    if len(rows) < 4800: continue      # need the full ~208d archive
    raw[c] = {int(r[0]): r for r in rows}
COINS = sorted(raw)
print(f"coins with full archive: {len(COINS)}: {COINS}")
common=None
for c,m in raw.items():
    s=set(m); common = s if common is None else (common & s)
grid=np.array(sorted(common))
d=np.diff(grid)==3600000; runs,st=[],0
for i,ok in enumerate(d):
    if not ok: runs.append((st,i)); st=i+1
runs.append((st,len(grid)-1)); b0,b1=max(runs,key=lambda r:r[1]-r[0]); grid=grid[b0:b1+1]
print(f"aligned bars {len(grid)} = {len(grid)/24:.1f} days")
O={c:np.array([raw[c][t][1] for t in grid]) for c in COINS}
C={c:np.array([raw[c][t][4] for t in grid]) for c in COINS}
hours=np.array([dt.datetime.fromtimestamp(t/1000,dt.UTC).hour for t in grid])
mon=np.array([dt.datetime.fromtimestamp(t/1000,dt.UTC).strftime("%Y-%m") for t in grid])
ROC={c:(C[c]-O[c])/O[c]*1e4 for c in COINS}
def tt(x):
    x=np.asarray(x,float); n=len(x); m=x.mean(); s=x.std(ddof=1); return n,m,s,m/(s/math.sqrt(n))

print("\n=== A. hour 20:00 UTC (= 16:00 ET, US cash close) across ALL coins ===")
print(f"{'coin':<10} {'n':>4} {'mean bp':>9} {'t':>6} {'med':>7} {'hit':>5} {'trim10':>8} {'net-9':>7}")
h20=[]
for c in COINS:
    x=ROC[c][hours==20]; n,m,s,t=tt(x); k=n//10
    tr=np.mean(np.sort(x)[k:-k])
    h20.append((c,n,m,t,np.median(x),np.mean(x>0),tr))
    print(f"{c:<10} {n:>4} {m:>+9.2f} {t:>+6.2f} {np.median(x):>+7.2f} {np.mean(x>0):>5.3f} {tr:>+8.2f} {m-FEE:>+7.2f}")
ts=np.array([r[3] for r in h20])
print(f"\nhour-20 t-stats: mean={ts.mean():+.2f} frac t>0: {np.mean(ts>0):.2f} "
      f"frac t>2: {np.mean(ts>2):.2f} (expect 0.02 under null)")
print("Under the null, mean t across coins ~0 (coins are correlated so this is not 40 independent tests).")

print("\n=== B. FULL mining scope: %d coins x 24 hours = %d tests ==="%(len(COINS),len(COINS)*24))
allt=[]
for c in COINS:
    for h in range(24):
        x=ROC[c][hours==h]; n,m,s,t=tt(x); allt.append((abs(t),t,c,h,m))
allt.sort(reverse=True)
print(f"Bonferroni threshold p<{0.05/(len(COINS)*24):.2e} -> |t| > ~{4.5:.1f}")
print("top 10 |t| coin-hours:")
for a,t,c,h,m in allt[:10]:
    print(f"  {c:<10} hr {h:02d}  mean={m:+8.2f}bp t={t:+5.2f} net-9={m-FEE:+8.2f}")

print("\n=== C. permutation null for max|t| over the FULL %dx24 grid ==="%len(COINS))
M=np.vstack([ROC[c] for c in COINS])
rng=np.random.default_rng(11)
maxts=[]
for it in range(300):
    sh=rng.integers(1,M.shape[1]); Ms=np.roll(M,sh,axis=1)
    best=0.0
    for ci in range(len(COINS)):
        row=Ms[ci]
        for h in range(24):
            y=row[hours==h]; tv=abs(y.mean()/(y.std(ddof=1)/math.sqrt(len(y))))
            if tv>best: best=tv
    maxts.append(best)
maxts=np.array(maxts)
obs=allt[0][0]
print(f"300 circular-shift nulls: max|t| p50={np.percentile(maxts,50):.2f} "
      f"p90={np.percentile(maxts,90):.2f} p95={np.percentile(maxts,95):.2f} p99={np.percentile(maxts,99):.2f} max={maxts.max():.2f}")
print(f"observed best = {allt[0][2]} hr{allt[0][3]:02d} |t|={obs:.2f}  "
      f"family-wise p = {np.mean(maxts>=obs):.3f}")
for a,t,c,h,m in allt[:5]:
    print(f"   {c} hr{h:02d} |t|={a:.2f} -> FW p={np.mean(maxts>=a):.3f}")

print("\n=== D. vol-by-hour, wide universe (mean |open->close| bp) ===")
absr=np.nanmean(np.vstack([np.abs(ROC[c]) for c in COINS]),axis=0)
gm=absr.mean()
prof=[(h,np.mean(absr[hours==h]),np.mean(absr[hours==h])/gm) for h in range(24)]
for h,v,r in prof: print(f"  hr {h:02d}: {v:7.2f}bp  {r:.3f}x")
hi=max(prof,key=lambda r:r[1]); lo=min(prof,key=lambda r:r[1])
print(f"loudest {hi[0]:02d}:00 {hi[1]:.2f}bp {hi[2]:.2f}x ; quietest {lo[0]:02d}:00 {lo[1]:.2f}bp {lo[2]:.2f}x ; ratio {hi[1]/lo[1]:.2f}x")
half=len(grid)//2
v1=np.array([np.mean(absr[:half][hours[:half]==h]) for h in range(24)])
v2=np.array([np.mean(absr[half:][hours[half:]==h]) for h in range(24)])
print(f"split-half corr of vol profile = {np.corrcoef(v1,v2)[0,1]:+.3f} (24 points)")
