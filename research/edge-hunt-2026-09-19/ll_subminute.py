"""Where does the lead-lag actually LIVE, in seconds? And what is the real taker bar?

1m candles cannot resolve a lag shorter than 60s. This uses live BBO (event-driven,
server-timestamped) to (a) measure per-coin half-spread -> the TRUE cost bar, and
(b) cross-correlate leader/alt mid returns at 1-second lags out to 60s.
"""
import json, math, sys
import numpy as np

D = "/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
FP = D + "/" + (sys.argv[2] if len(sys.argv) > 2 else "ll_bbo.jsonl")
BIN_MS = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
LEADERS = ["BTC", "ETH", "HYPE"]

rows = []
for line in open(FP):
    try:
        rows.append(json.loads(line))
    except Exception:
        pass
print("bbo rows:", len(rows))
coins = sorted({r[0] for r in rows})
t0 = min(r[1] for r in rows)
t1 = max(r[1] for r in rows)
print(f"span {(t1-t0)/1000:.0f}s = {(t1-t0)/60000:.1f} min, coins {len(coins)}")

# ---- 1. TRUE taker cost per coin: half-spread + 4.5bp fee, each way -------
print("\n=== 1. real round-trip taker cost per coin (2 x fee + 2 x half-spread) ===")
print(f"{'coin':<6} {'updates':>8} {'med spread bp':>14} {'half-sp bp':>11} "
      f"{'TRUE rt cost bp':>16}")
cost = {}
for c in coins:
    sp = np.array([(r[3] - r[2]) / ((r[2] + r[3]) / 2) * 1e4 for r in rows if r[0] == c])
    med = float(np.median(sp))
    cost[c] = 9.0 + med          # 2*4.5 fee + 2*(med/2) spread
    print(f"{c:<6} {len(sp):>8} {med:>14.3f} {med/2:>11.3f} {cost[c]:>16.2f}")

# ---- 2. build aligned mid grid at BIN_MS ---------------------------------
nb = int((t1 - t0) // BIN_MS) + 1
mid = {}
for c in coins:
    arr = np.full(nb, np.nan)
    for r in rows:
        if r[0] != c:
            continue
        arr[int((r[1] - t0) // BIN_MS)] = (r[2] + r[3]) / 2
    # forward fill
    last = np.nan
    for i in range(nb):
        if np.isnan(arr[i]):
            arr[i] = last
        else:
            last = arr[i]
    mid[c] = arr
ok = ~np.isnan(np.vstack([mid[c] for c in coins])).any(axis=0)
first = int(np.argmax(ok))
G = {c: mid[c][first:] for c in coins}
n = len(G[coins[0]])
R = {c: np.diff(np.log(G[c])) * 1e4 for c in coins}
N = n - 1
print(f"\ngrid bins={n} at {BIN_MS}ms -> {N} return obs "
      f"({N*BIN_MS/60000:.1f} min)")

# ---- 3. lagged cross-correlation in SECONDS ------------------------------
print(f"\n=== 2. corr(r_leader[t-k], r_alt[t]) at {BIN_MS}ms bins, k in bins ===")
LAGS = [0, 1, 2, 3, 5, 10, 20, 30, 60]
LAGS = [k for k in LAGS if k < N // 4]
hdr = "".join(f"{('k='+str(k)):>9}" for k in LAGS)
print(f"{'pair':<12}{hdr}")
argmax_tab = []
for L in LEADERS:
    if L not in R:
        continue
    for A in coins:
        if A == L:
            continue
        rl, ra = R[L], R[A]
        vals = []
        for k in LAGS:
            x = rl[:N - k] if k else rl
            y = ra[k:]
            if x.std() == 0 or y.std() == 0:
                vals.append(float("nan")); continue
            vals.append(float(np.corrcoef(x, y)[0, 1]))
        # full scan 0..60 to find argmax
        full = []
        for k in range(0, min(61, N // 4)):
            x = rl[:N - k] if k else rl
            y = ra[k:]
            full.append(np.corrcoef(x, y)[0, 1] if x.std() and y.std() else np.nan)
        am = int(np.nanargmax(full))
        argmax_tab.append((L, A, am, full[am], full[0]))
        print(f"{L}->{A:<8}" + "".join(f"{v:>+9.4f}" for v in vals) +
              f"   argmax k={am} ({full[am]:+.4f})")

print("\n=== 3. where is the peak? (argmax lag in bins) ===")
ams = [a[2] for a in argmax_tab]
print("argmax lag distribution:", {k: ams.count(k) for k in sorted(set(ams))})
print(f"share peaking at k=0 (CONTEMPORANEOUS, unexecutable): "
      f"{ams.count(0)}/{len(ams)}")

# ---- 4. event study in seconds: leader jumps, does alt follow? -----------
print(f"\n=== 4. leader 1-bin move >= thr bp -> alt cumulative move over next h bins")
print(f"    (bins of {BIN_MS}ms). Compare to per-coin TRUE cost above ===")
print(f"{'leader':<6} {'thr':>5} {'h':>4} {'events':>7} {'alt bp':>8} {'clust t':>8}")
for L in LEADERS:
    if L not in R:
        continue
    rl = R[L]
    alts = [a for a in coins if a != L]
    for thr in (2, 5, 10):
        for h in (1, 2, 5, 10, 30):
            if h >= N // 4:
                continue
            idx = [i for i in range(N - h) if abs(rl[i]) >= thr]
            if len(idx) < 5:
                continue
            M = np.full((len(idx), len(alts)), np.nan)
            for j, A in enumerate(alts):
                g = G[A]
                for ii, i in enumerate(idx):
                    sgn = 1.0 if rl[i] > 0 else -1.0
                    e = g[i + 1]
                    if e > 0:
                        M[ii, j] = sgn * (g[i + 1 + h] - e) / e * 1e4
            ev = np.nanmean(M, axis=1)
            ev = ev[np.isfinite(ev)]
            if len(ev) < 5:
                continue
            m = ev.mean(); s = ev.std(ddof=1)
            t = m / (s / math.sqrt(len(ev))) if s > 0 else float("nan")
            print(f"{L:<6} {thr:>5} {h:>4} {len(ev):>7} {m:>+8.3f} {t:>+8.2f}")
