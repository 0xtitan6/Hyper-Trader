"""Same lead-lag trade as ll_candle.py section 2, but with HONEST sample size.

Pooling 19 alts at the same timestamp is pseudo-replication: the alts are 0.24-0.65
contemporaneously correlated, so 19 alt-observations at one BTC spike are ~1 draw,
not 19. Here we form the equal-weight basket return per EVENT and t-stat over events.
Also reports how many distinct events and a per-alt breakdown.
"""
import json, os, math, sys
import numpy as np

D = "/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
IV = sys.argv[1] if len(sys.argv) > 1 else "1m_long"
STEP_MS = {"1m_long": 60000, "1m": 60000, "5m": 300000, "15m": 900000}[IV]
COINS = ["BTC", "ETH", "SOL", "HYPE", "DOGE", "XRP", "SUI", "LTC", "BNB", "AVAX",
         "LINK", "ADA", "NEAR", "ARB", "WLD", "TAO", "ENA", "UNI", "AAVE", "INJ"]
LEADERS = ["BTC", "ETH", "HYPE"]
FEE = 9.0

raw = {}
for c in COINS:
    fp = f"{D}/{c}_{IV}.json"
    if os.path.exists(fp):
        raw[c] = {int(r[0]): r for r in np.array(json.load(open(fp)), float)}
common = None
for c, m in raw.items():
    common = set(m) if common is None else (common & set(m))
common = np.array(sorted(common))
step_ok = np.diff(common) == STEP_MS
runs, start = [], 0
for i, ok in enumerate(step_ok):
    if not ok:
        runs.append((start, i)); start = i + 1
runs.append((start, len(common) - 1))
b0, b1 = max(runs, key=lambda r: r[1] - r[0])
grid = common[b0:b1 + 1]
O = {c: np.array([raw[c][t][1] for t in grid]) for c in raw}
C = {c: np.array([raw[c][t][4] for t in grid]) for c in raw}
R = {c: np.diff(np.log(C[c])) * 1e4 for c in raw}
N = len(grid) - 1
print(f"IV={IV} bars={len(grid)} ({len(grid)*STEP_MS/86400000:.2f}d) obs={N}")


def tt(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 5:
        return n, float("nan"), float("nan")
    m = x.mean()
    s = x.std(ddof=1)
    return n, m, (m / (s / math.sqrt(n)) if s > 0 else float("nan"))


print("\n=== EVENT-CLUSTERED: one observation per timestamp (EW basket of alts) ===")
print(f"{'leader':<6} {'thr':>4} {'h':>2} | {'naive n':>8} {'naive t':>8} "
      f"| {'events':>7} {'bp':>8} {'clust t':>8} {'net-9':>8} | {'alts>0':>7}")
for L in LEADERS:
    rl = R[L]
    alts = [a for a in COINS if a != L and a in R]
    for thr in (10, 20, 30, 40):
        for h in (1, 2, 5):
            idx = [i for i in range(N - h - 1) if abs(rl[i]) >= thr]
            if not idx:
                continue
            # per-alt pnl series aligned on events
            M = np.full((len(idx), len(alts)), np.nan)
            for j, A in enumerate(alts):
                oa, ca = O[A], C[A]
                for ii, i in enumerate(idx):
                    sgn = 1.0 if rl[i] > 0 else -1.0
                    e = oa[i + 2]
                    if e > 0:
                        M[ii, j] = sgn * (ca[i + 1 + h] - e) / e * 1e4
            flat = M[np.isfinite(M)]
            nn, nm, nt = tt(flat)
            ev = np.nanmean(M, axis=1)          # EW basket per event
            en, em, et = tt(ev)
            per_alt = np.nanmean(M, axis=0)
            pos = int((per_alt > 0).sum())
            print(f"{L:<6} {thr:>4} {h:>2} | {nn:>8} {nt:>+8.2f} | {en:>7} {em:>+8.3f} "
                  f"{et:>+8.2f} {em-FEE:>+8.3f} | {pos:>2}/{len(alts):<4}")

# --- how concentrated in time are the "events"? ---
print("\n=== event concentration (BTC |r|>=20bp) ===")
rl = R["BTC"]
idx = [i for i in range(N - 6) if abs(rl[i]) >= 20]
print("n events:", len(idx))
if idx:
    days = np.array([grid[i] // 86400000 for i in idx])
    for d in sorted(set(days)):
        print("  day", int(d), "events", int((days == d).sum()))
    # autocorrelation of event times: are they clustered in bursts?
    gaps = np.diff(np.array(idx))
    print("  consecutive-minute events:", int((gaps == 1).sum()),
          "median gap (min):", float(np.median(gaps)))
