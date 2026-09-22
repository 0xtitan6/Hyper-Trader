"""Split-half + per-alt detail on the ONE cell with clustered t >= 2:
15m bars, leader ETH (and HYPE), |r_L| >= 10-20bp, hold 1 bar.
Is the +1.76 bp real and stable, or is it a two-week artifact?
"""
import json, os, math
import numpy as np

D = "/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
IV, STEP_MS = "15m", 900000
COINS = ["BTC", "ETH", "SOL", "HYPE", "DOGE", "XRP", "SUI", "LTC", "BNB", "AVAX",
         "LINK", "ADA", "NEAR", "ARB", "WLD", "TAO", "ENA", "UNI", "AAVE", "INJ"]
raw = {}
for c in COINS:
    fp = f"{D}/{c}_{IV}.json"
    if os.path.exists(fp):
        raw[c] = {int(r[0]): r for r in np.array(json.load(open(fp)), float)}
common = None
for c, m in raw.items():
    common = set(m) if common is None else (common & set(m))
common = np.array(sorted(common))
ok = np.diff(common) == STEP_MS
runs, s0 = [], 0
for i, o in enumerate(ok):
    if not o:
        runs.append((s0, i)); s0 = i + 1
runs.append((s0, len(common) - 1))
b0, b1 = max(runs, key=lambda r: r[1] - r[0])
grid = common[b0:b1 + 1]
O = {c: np.array([raw[c][t][1] for t in grid]) for c in raw}
C = {c: np.array([raw[c][t][4] for t in grid]) for c in raw}
R = {c: np.diff(np.log(C[c])) * 1e4 for c in raw}
N = len(grid) - 1
print(f"{IV}: {len(grid)} bars, {len(grid)*STEP_MS/86400000:.1f} days, {len(raw)} coins")


def tt(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    if len(x) < 5:
        return len(x), float('nan'), float('nan')
    m, s = x.mean(), x.std(ddof=1)
    return len(x), m, (m / (s / math.sqrt(len(x))) if s else float('nan'))


for L, thr in (("ETH", 10), ("HYPE", 20), ("BTC", 10)):
    rl = R[L]
    alts = [a for a in COINS if a != L and a in R]
    h = 1
    idx = [i for i in range(N - h - 1) if abs(rl[i]) >= thr]
    M = np.full((len(idx), len(alts)), np.nan)
    for j, A in enumerate(alts):
        oa, ca = O[A], C[A]
        for ii, i in enumerate(idx):
            sgn = 1.0 if rl[i] > 0 else -1.0
            e = oa[i + 2]
            if e > 0:
                M[ii, j] = sgn * (ca[i + 1 + h] - e) / e * 1e4
    ev = np.nanmean(M, axis=1)
    n, m, t = tt(ev)
    print(f"\n=== {L} thr={thr} h=1 : FULL  n_ev={n} {m:+.3f} bp t={t:+.2f} ===")
    half = len(idx) // 2
    for nm, sl in (("first half", slice(0, half)), ("second half", slice(half, None))):
        n2, m2, t2 = tt(ev[sl])
        d0 = grid[idx[sl.start or 0]] // 86400000
        print(f"  {nm:<12} n_ev={n2:>5} {m2:+8.3f} bp t={t2:+6.2f}")
    # per-alt
    pa = [(A, *tt(M[:, j])) for j, A in enumerate(alts)]
    pa.sort(key=lambda r: -r[2])
    print("  per-alt mean bp (naive t, not clustered):")
    print("   " + "  ".join(f"{A}:{m3:+.2f}" for A, _, m3, _ in pa))
    print(f"  alts positive: {sum(1 for r in pa if r[2] > 0)}/{len(pa)}")
    # required cost to break even
    print(f"  break-even needs round-trip cost < {m:.2f} bp "
          f"(= {m/2:.3f} bp per side). Our best real cost ~9.7 bp.")
