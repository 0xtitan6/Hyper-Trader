"""Time-of-day drift & vol on HL 1h candles. Everything in bps. Bar = 9bp round trip."""
import json, os, math, datetime as dt
import numpy as np

D = os.path.dirname(os.path.abspath(__file__)) + "/data"
COINS = ["BTC","ETH","HYPE","ZEC","SOL","NEAR","XRP","LIT","PUMP","UNI","AAVE","XMR"]
FEE = 9.0

raw = {c: {int(r[0]): r for r in json.load(open(f"{D}/{c}_1h_long.json"))} for c in COINS}
common = None
for c, m in raw.items():
    s = set(m); common = s if common is None else (common & s)
grid = np.array(sorted(common))
# longest contiguous hourly run
d = np.diff(grid) == 3600000
runs, st = [], 0
for i, ok in enumerate(d):
    if not ok: runs.append((st, i)); st = i + 1
runs.append((st, len(grid) - 1))
b0, b1 = max(runs, key=lambda r: r[1] - r[0])
grid = grid[b0:b1+1]
print(f"aligned contiguous 1h bars: {len(grid)} = {len(grid)/24:.1f} days  "
      f"{dt.datetime.utcfromtimestamp(grid[0]/1000)} -> {dt.datetime.utcfromtimestamp(grid[-1]/1000)}")

O = {c: np.array([raw[c][t][1] for t in grid]) for c in COINS}
H = {c: np.array([raw[c][t][2] for t in grid]) for c in COINS}
L = {c: np.array([raw[c][t][3] for t in grid]) for c in COINS}
C = {c: np.array([raw[c][t][4] for t in grid]) for c in COINS}
V = {c: np.array([raw[c][t][5] for t in grid]) for c in COINS}
NTRD = {c: np.array([raw[c][t][6] for t in grid]) for c in COINS}

hours = np.array([dt.datetime.utcfromtimestamp(t/1000).hour for t in grid])
dows  = np.array([dt.datetime.utcfromtimestamp(t/1000).weekday() for t in grid])  # 0=Mon

# per-bar tradeable return: enter at bar OPEN, exit at bar CLOSE (both taker).
# This is the honest version: at hour h:00 you know nothing about h, you buy the open.
ROC = {c: (C[c] - O[c]) / O[c] * 1e4 for c in COINS}      # open->close, bps
RCC = {c: np.concatenate([[np.nan], np.diff(np.log(C[c])) * 1e4]) for c in COINS}
PARK = {c: (np.log(H[c]/L[c])**2) / (4*np.log(2)) for c in COINS}   # Parkinson var
TR = {c: (H[c]-L[c]) / O[c] * 1e4 for c in COINS}          # high-low range, bps

# equal-weight index of open->close returns: handles cross-coin correlation properly
IDX = np.nanmean(np.vstack([ROC[c] for c in COINS]), axis=0)
IDXCC = np.nanmean(np.vstack([RCC[c] for c in COINS]), axis=0)

def tt(x):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    n = len(x)
    if n < 5: return n, np.nan, np.nan, np.nan
    m = x.mean(); s = x.std(ddof=1)
    return n, m, s, m/(s/math.sqrt(n))

def bh(pvals, q=0.05):
    """Benjamini-Hochberg: return boolean survives mask."""
    p = np.asarray(pvals); o = np.argsort(p); m = len(p)
    surv = np.zeros(m, bool); k = 0
    for i, idx in enumerate(o):
        if p[idx] <= (i+1)/m*q: k = i+1
    for i, idx in enumerate(o):
        if i < k: surv[idx] = True
    return surv

from math import erf, sqrt
def p2(t):
    if not np.isfinite(t): return 1.0
    return 2*(1-0.5*(1+erf(abs(t)/sqrt(2))))

print("\n" + "="*100)
print("=== 1. DRIFT by UTC hour, equal-weight 12-coin index, open->close return (bps) ===")
print(f"{'hr':>3} {'n':>4} {'mean bp':>9} {'sd':>7} {'t':>6} {'p':>7} {'net vs 9bp':>11} {'ann.hitrate':>11}")
rows = []
for h in range(24):
    x = IDX[hours == h]
    n, m, s, t = tt(x)
    hit = np.mean(x > 0)
    rows.append((h, n, m, s, t, p2(t), hit))
    print(f"{h:>3} {n:>4} {m:>+9.3f} {s:>7.2f} {t:>+6.2f} {p2(t):>7.4f} {m-FEE:>+11.3f} {hit:>11.3f}")
ps = np.array([r[5] for r in rows])
surv = bh(ps)
print(f"\nBonferroni threshold for 24 tests at alpha=0.05: p < {0.05/24:.5f}")
print("Bonferroni survivors:", [rows[i][0] for i in range(24) if ps[i] < 0.05/24] or "NONE")
print("Benjamini-Hochberg q=0.05 survivors:", [rows[i][0] for i in range(24) if surv[i]] or "NONE")
best = max(rows, key=lambda r: abs(r[4]))
print(f"max |t| hour = {best[0]}: mean {best[2]:+.3f}bp t={best[4]:+.2f} (uncorrected p={best[5]:.4f})")
print(f"expected max|t| of 24 iid N(0,1) ~ 2.4;  observed {abs(best[4]):.2f}")

print("\n=== 1b. same, per coin: how many coin-hours beat 9bp AND have t>2? ===")
cnt = 0
percoin_best = []
for c in COINS:
    bs = []
    for h in range(24):
        n, m, s, t = tt(ROC[c][hours == h])
        bs.append((h, n, m, t))
        if m - FEE > 0 and t > 2: cnt += 1
    b = max(bs, key=lambda r: abs(r[3]))
    percoin_best.append((c, b))
    print(f"{c:<6} best|t| hr={b[0]:>2} n={b[1]} mean={b[2]:+8.3f}bp t={b[3]:+5.2f} "
          f"p={p2(b[3]):.4f} bonf(24)={'PASS' if p2(b[3])<0.05/24 else 'fail'}")
print(f"coin-hours with mean>9bp and t>2: {cnt} out of {12*24} (expected by chance at t>2 one-sided: ~{12*24*0.0228:.1f})")

print("\n=== 1c. SPLIT-HALF persistence of the hour-of-day drift profile (index) ===")
half = len(grid)//2
m1 = np.array([tt(IDX[:half][hours[:half]==h])[1] for h in range(24)])
m2 = np.array([tt(IDX[half:][hours[half:]==h])[1] for h in range(24)])
print("first-half  means bp:", " ".join(f"{v:+.2f}" for v in m1))
print("second-half means bp:", " ".join(f"{v:+.2f}" for v in m2))
print(f"corr(first,second) over 24 hours = {np.corrcoef(m1,m2)[0,1]:+.3f}  (n=24 hour points)")
print(f"null 95% band on that corr: +/-{1.96/math.sqrt(24-3):.3f}")
# out-of-sample: trade the best hour from half1 in half2
bh1 = int(np.argmax(np.abs(m1))); sgn = np.sign(m1[bh1])
x = sgn*IDX[half:][hours[half:]==bh1]
n,m,s,t = tt(x)
print(f"OOS: best hour from H1 = {bh1} (sign {sgn:+.0f}, H1 mean {m1[bh1]:+.3f}bp) -> "
      f"H2 mean {m:+.3f}bp n={n} t={t:+.2f} net vs 9bp {m-FEE:+.3f}")

print("\n" + "="*100)
print("=== 2. DAY OF WEEK drift, index, open->close of each 24h UTC day ===")
# build daily returns
days = np.array([dt.datetime.utcfromtimestamp(t/1000).date() for t in grid])
udays = sorted(set(days))
dret, ddow = [], []
for dd in udays:
    msk = days == dd
    if msk.sum() != 24: continue
    r = np.mean([(C[c][msk][-1]-O[c][msk][0])/O[c][msk][0]*1e4 for c in COINS])
    dret.append(r); ddow.append(dd.weekday())
dret = np.array(dret); ddow = np.array(ddow)
print(f"full UTC days: {len(dret)}")
names = "Mon Tue Wed Thu Fri Sat Sun".split()
pd_ = []
for k in range(7):
    n,m,s,t = tt(dret[ddow==k])
    pd_.append(p2(t))
    print(f"{names[k]} n={n:>3} mean={m:+9.2f}bp sd={s:>7.1f} t={t:+5.2f} p={p2(t):.4f} net vs 9bp {m-FEE:+9.2f}")
print(f"Bonferroni for 7 tests: p<{0.05/7:.4f} -> survivors:",
      [names[k] for k in range(7) if pd_[k] < 0.05/7] or "NONE")

print("\n" + "="*100)
print("=== 3. VOLATILITY by UTC hour (this is the real question) ===")
print("mean |open->close| bps, and mean high-low range bps, index-averaged across coins")
absr = np.nanmean(np.vstack([np.abs(ROC[c]) for c in COINS]), axis=0)
rng  = np.nanmean(np.vstack([TR[c] for c in COINS]), axis=0)
vol  = np.nanmean(np.vstack([np.sqrt(PARK[c])*1e4 for c in COINS]), axis=0)
volu = np.nanmean(np.vstack([V[c]*C[c]/np.nanmean(V[c]*C[c]) for c in COINS]), axis=0)
gm_abs, gm_rng = absr.mean(), rng.mean()
print(f"{'hr':>3} {'n':>4} {'|ret|bp':>8} {'ratio':>6} {'t vs mean':>10} {'range bp':>9} {'ratio':>6} {'rel$vol':>8}")
vr = []
for h in range(24):
    msk = hours == h
    n1,m1a,s1,_ = tt(absr[msk])
    other = absr[~msk]
    # Welch t of hour-h |ret| vs all other hours
    m2a = np.nanmean(other); s2 = np.nanstd(other, ddof=1); n2 = len(other)
    tw = (m1a-m2a)/math.sqrt(s1**2/n1 + s2**2/n2)
    n1b,mr,_,_ = tt(rng[msk])
    vr.append((h, n1, m1a, m1a/gm_abs, tw, mr, mr/gm_rng, np.nanmean(volu[msk]), p2(tw)))
    print(f"{h:>3} {n1:>4} {m1a:>8.2f} {m1a/gm_abs:>6.3f} {tw:>+10.2f} {mr:>9.2f} {mr/gm_rng:>6.3f} {np.nanmean(volu[msk]):>8.3f}")
pv = np.array([r[8] for r in vr])
print(f"\nBonferroni 24 tests p<{0.05/24:.5f} -> vol survivors:",
      [vr[i][0] for i in range(24) if pv[i] < 0.05/24] or "NONE")
sv = bh(pv); print("BH q=0.05 vol survivors:", [vr[i][0] for i in range(24) if sv[i]] or "NONE")
hi = max(vr, key=lambda r: r[2]); lo = min(vr, key=lambda r: r[2])
print(f"loudest hour {hi[0]:02d}:00 = {hi[2]:.2f}bp ({hi[3]:.2f}x avg, t={hi[4]:+.2f}) ; "
      f"quietest {lo[0]:02d}:00 = {lo[2]:.2f}bp ({lo[3]:.2f}x avg)")
print(f"loud/quiet ratio = {hi[2]/lo[2]:.2f}x")

print("\n=== 3b. SPLIT-HALF persistence of the VOL profile ===")
v1 = np.array([np.nanmean(absr[:half][hours[:half]==h]) for h in range(24)])
v2 = np.array([np.nanmean(absr[half:][hours[half:]==h]) for h in range(24)])
print("H1 |ret| by hour:", " ".join(f"{v:.1f}" for v in v1))
print("H2 |ret| by hour:", " ".join(f"{v:.1f}" for v in v2))
print(f"corr(H1,H2) vol profile over 24 hours = {np.corrcoef(v1,v2)[0,1]:+.3f}")
# also monthly stability of the top-6 vs bottom-6 hour sets
top6 = set(np.argsort(-v1)[:6]); bot6 = set(np.argsort(v1)[:6])
r_top = np.nanmean(absr[half:][np.isin(hours[half:], list(top6))])
r_bot = np.nanmean(absr[half:][np.isin(hours[half:], list(bot6))])
print(f"OOS (H2): H1-top6 hours |ret|={r_top:.2f}bp  H1-bottom6={r_bot:.2f}bp  ratio={r_top/r_bot:.2f}x")

print("\n=== 3c. per-month stability of loud vs quiet hour sets (index |ret|) ===")
mon = np.array([dt.datetime.utcfromtimestamp(t/1000).strftime("%Y-%m") for t in grid])
for mm in sorted(set(mon)):
    msk = mon == mm
    a = absr[msk]; hh = hours[msk]
    t_ = np.nanmean(a[np.isin(hh, list(top6))]); b_ = np.nanmean(a[np.isin(hh, list(bot6))])
    print(f"  {mm} n={msk.sum():>4} top6={t_:6.2f} bot6={b_:6.2f} ratio={t_/b_:5.2f}x")

print("\n" + "="*100)
print("=== 4. TRADEABLE forms, all net of 9bp round trip ===")
# 4a best single hour long-only / short-only per coin, OOS via split half already above.
# 4b 'trade every day at hour h, both legs taker': net = mean - 9
print("4b. buy index at hour h open, sell at hour h close, every day, net bp/trade:")
netbest = sorted(rows, key=lambda r: -(abs(r[2])))[:5]
for h,n,m,s,t,p,hit in netbest:
    print(f"  hr {h:02d}: gross {m:+.3f}bp  |gross| {abs(m):.3f}  net(|g|-9) {abs(m)-FEE:+.3f}bp  t={t:+.2f} n={n}")
# 4c how large would drift need to be to be detectable? min detectable effect
sd_idx = np.nanstd(IDX, ddof=1)
n_per_hour = len(grid)/24
mde = 2.8*sd_idx/math.sqrt(n_per_hour)   # t=2.8 to clear bonferroni-ish
print(f"\n4c. POWER: index hourly sd = {sd_idx:.1f}bp, n per hour bucket = {n_per_hour:.0f}")
print(f"    min drift detectable at |t|=2.8 (bonferroni-ish 24 tests) = {mde:.2f}bp")
print(f"    ...vs the 9bp fee bar. A 9bp drift would give t = {9/(sd_idx/math.sqrt(n_per_hour)):.2f}")
print(f"    => the test IS powered to see a 9bp/hour drift if it existed.")
# per-coin power
for c in ["BTC","ETH","SOL","HYPE"]:
    s = np.nanstd(ROC[c], ddof=1)
    print(f"    {c}: sd={s:.1f}bp -> a true 9bp hourly drift gives t={9/(s/math.sqrt(n_per_hour)):.2f}")
