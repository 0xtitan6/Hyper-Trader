"""Cross-coin lead-lag on HL 1m (and 5m) candles.

Q: does BTC/ETH/HYPE lead alts by 1-5 minutes by enough to beat 9bp round trip?
"""
import json, os, math, sys
import numpy as np

D = "/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
IV = sys.argv[1] if len(sys.argv) > 1 else "1m_long"
STEP_MS = {"1m_long": 60000, "1m": 60000, "5m": 300000, "15m": 900000}[IV]

COINS = ["BTC", "ETH", "SOL", "HYPE", "DOGE", "XRP", "SUI", "LTC", "BNB", "AVAX",
         "LINK", "ADA", "NEAR", "ARB", "WLD", "TAO", "ENA", "UNI", "AAVE", "INJ"]
LEADERS = ["BTC", "ETH", "HYPE"]

# ---- load + align on a common timestamp grid --------------------------------
raw = {}
for c in COINS:
    fp = f"{D}/{c}_{IV}.json"
    if not os.path.exists(fp):
        print("MISSING", c)
        continue
    a = np.array(json.load(open(fp)), float)
    raw[c] = {int(r[0]): r for r in a}

common = None
for c, m in raw.items():
    s = set(m)
    common = s if common is None else (common & s)
common = np.array(sorted(common))
# keep only the longest contiguous run so lags are real time-lags
step_ok = np.diff(common) == STEP_MS
runs, start = [], 0
for i, ok in enumerate(step_ok):
    if not ok:
        runs.append((start, i)); start = i + 1
runs.append((start, len(common) - 1))
b0, b1 = max(runs, key=lambda r: r[1] - r[0])
grid = common[b0:b1 + 1]
print(f"IV={IV} coins={len(raw)} aligned contiguous bars={len(grid)} "
      f"= {len(grid)*STEP_MS/86400000:.2f} days")

O = {c: np.array([raw[c][t][1] for t in grid]) for c in raw}
C = {c: np.array([raw[c][t][4] for t in grid]) for c in raw}
# close-to-close log return in bps
R = {c: np.diff(np.log(C[c])) * 1e4 for c in raw}
# open->close ("intrabar") and close->open, used for execution realism
N = len(grid) - 1
print("return obs per coin:", N)


def tstat(x):
    x = np.asarray(x, float)
    n = len(x)
    if n < 10:
        return n, float("nan"), float("nan"), float("nan")
    m = x.mean(); s = x.std(ddof=1)
    return n, m, s, m / (s / math.sqrt(n))


# ---- 1. lagged cross-correlation matrix ------------------------------------
print("\n=== 1. corr(r_leader[t-k], r_alt[t]) — k=0 is CONTEMPORANEOUS, not lead-lag ===")
print(f"{'pair':<12} {'k=0':>8} {'k=1':>8} {'k=2':>8} {'k=3':>8} {'k=4':>8} {'k=5':>8} "
      f"| {'rev k=1':>8} {'rev k=2':>8}")
MAXK = 5
corr_tab = {}
for L in LEADERS:
    for A in COINS:
        if A == L or A not in R:
            continue
        rl, ra = R[L], R[A]
        row = []
        for k in range(MAXK + 1):
            x = rl[:N - k] if k else rl
            y = ra[k:]
            row.append(np.corrcoef(x, y)[0, 1])
        rev = []
        for k in (1, 2):
            rev.append(np.corrcoef(ra[:N - k], rl[k:])[0, 1])
        corr_tab[(L, A)] = (row, rev)
        print(f"{L}->{A:<8} " + " ".join(f"{v:+8.4f}" for v in row) +
              " | " + " ".join(f"{v:+8.4f}" for v in rev))

# 95% CI on a correlation with N obs, under the null rho=0: ~1.96/sqrt(N)
print(f"\nnull 95% band on any single corr with N={N}: +/-{1.96/math.sqrt(N):.4f}")

# ---- 2. the actual trade: leader moves in bar t, we buy alt for bar t+1 ----
# Entry realism: you only know bar t's close AT the boundary. Best case you are
# filled at bar t+1's OPEN. Exit at bar t+1..t+h close. Both legs taker => 9bp.
print("\n=== 2. TRADEABLE: signal = sign(leader bar-t return) when |ret| >= thresh")
print("    entry = alt bar t+1 OPEN (taker), exit = alt bar t+h CLOSE (taker) ===")
print(f"{'leader':<6} {'thresh':>7} {'h':>2} {'n':>6} {'gross bp':>9} {'sd':>7} "
      f"{'t':>7} {'net vs 9bp':>11}")
FEE = 9.0
results = []
for L in LEADERS:
    rl = R[L]
    for thresh in (0, 10, 20, 40, 80):
        for h in (1, 2, 5):
            pnl = []
            for A in COINS:
                if A == L or A not in R:
                    continue
                ra_open = O[A]
                cl = C[A]
                # bar index i -> signal from R[L][i] (close of grid[i] vs grid[i+1]... )
                # R[c][i] = log(C[i+1]/C[i]); so signal known at time grid[i+1]
                for i in range(N - h - 1):
                    s = rl[i]
                    if abs(s) < thresh:
                        continue
                    sgn = 1.0 if s > 0 else -1.0
                    entry = ra_open[i + 2]          # open of bar AFTER signal bar closes
                    ex = cl[i + 1 + h]
                    if entry <= 0:
                        continue
                    pnl.append(sgn * (ex - entry) / entry * 1e4)
            n, m, sd, t = tstat(pnl)
            results.append((L, thresh, h, n, m, sd, t))
            print(f"{L:<6} {thresh:>7} {h:>2} {n:>6} {m:>+9.3f} {sd:>7.1f} {t:>+7.2f} "
                  f"{m-FEE:>+11.3f}")

# ---- 3. sharpest form: beta shortfall (alt under-reacted -> catch-up?) -----
print("\n=== 3. BETA SHORTFALL: alt under-reacts to leader in bar t, catches up in t+1? ===")
print("    shortfall_t = beta*r_L[t] - r_A[t] ; trade sign(shortfall), same execution")
print(f"{'leader':<6} {'pct':>5} {'h':>2} {'n':>6} {'gross bp':>9} {'sd':>7} {'t':>7} "
      f"{'net vs 9bp':>11}")
for L in LEADERS:
    rl = R[L]
    for pct in (50, 80, 90, 95):
        for h in (1, 2):
            pnl = []
            for A in COINS:
                if A == L or A not in R:
                    continue
                ra = R[A]
                beta = np.polyfit(rl, ra, 1)[0]
                sf = beta * rl - ra
                thr = np.percentile(np.abs(sf), pct)
                ra_open, cl = O[A], C[A]
                for i in range(N - h - 1):
                    if abs(sf[i]) < thr:
                        continue
                    sgn = 1.0 if sf[i] > 0 else -1.0
                    entry = ra_open[i + 2]
                    ex = cl[i + 1 + h]
                    if entry <= 0:
                        continue
                    pnl.append(sgn * (ex - entry) / entry * 1e4)
            n, m, sd, t = tstat(pnl)
            print(f"{L:<6} {pct:>5} {h:>2} {n:>6} {m:>+9.3f} {sd:>7.1f} {t:>+7.2f} "
                  f"{m-FEE:>+11.3f}")

# ---- 4. best case ceiling: how big is the follow move even with perfect fill?
print("\n=== 4. CEILING: perfect close-of-bar-t fill (NOT achievable), h=1 ===")
print(f"{'leader':<6} {'thresh':>7} {'n':>6} {'gross bp':>9} {'t':>7} {'net vs 9bp':>11}")
for L in LEADERS:
    rl = R[L]
    for thresh in (0, 20, 40, 80):
        pnl = []
        for A in COINS:
            if A == L or A not in R:
                continue
            ra = R[A]
            for i in range(N - 2):
                if abs(rl[i]) < thresh:
                    continue
                sgn = 1.0 if rl[i] > 0 else -1.0
                pnl.append(sgn * ra[i + 1])
        n, m, sd, t = tstat(pnl)
        print(f"{L:<6} {thresh:>7} {n:>6} {m:>+9.3f} {t:>+7.2f} {m-FEE:>+11.3f}")
