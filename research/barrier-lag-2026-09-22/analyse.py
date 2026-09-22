"""Lead-lag analysis: do HIP-4 priceTouch barriers reprice slower than the perp?

Everything is on the LOCAL receive clock (`lt`). No synthesised prices: asks and
sizes are the ones actually displayed.
"""
import json, sys, math, statistics as st
from collections import defaultdict

TAPE = sys.argv[1]
BAR = {"#12090": ("HYPE", 100.0), "#12120": ("BTC", 95000.0), "#12130": ("BTC", 90000.0)}

recs = [json.loads(l) for l in open(TAPE)]
t0 = min(r["lt"] for r in recs); t1 = max(r["lt"] for r in recs)
print(f"# window {t1-t0:.0f}s  records {len(recs)}")

# ---- underlying: event-driven perp prints (fast clock) + 1/s mark ----
utr = defaultdict(list)   # coin -> [(lt, px)]
mark = defaultdict(list)
for r in recs:
    if r["k"] == "utrade":
        utr[r["coin"]].append((r["lt"], float(r["px"])))
    elif r["k"] == "ctx" and r.get("mark"):
        mark[r["coin"]].append((r["lt"], float(r["mark"])))
for c in utr: utr[c].sort(); mark[c].sort()

# ---- barrier books: REST poll (primary) + WS snapshot, merged & deduped ----
books = defaultdict(list)  # coin -> [(lt, bid, bsz, ask, asz)]
for r in recs:
    if r["k"] in ("rest", "book") and r.get("b") and r.get("a"):
        b, a = r["b"][0], r["a"][0]
        books[r["coin"]].append((r["lt"], float(b[0]), float(b[1]), float(a[0]), float(a[1])))
for c in books: books[c].sort()

def step(series, t):
    """Last observation at or before t (no look-ahead)."""
    lo, hi = 0, len(series) - 1
    if not series or series[0][0] > t: return None
    while lo < hi:
        m = (lo + hi + 1) // 2
        if series[m][0] <= t: lo = m
        else: hi = m - 1
    return series[lo]

GRID = 1.0
grid = [t0 + i * GRID for i in range(int((t1 - t0) / GRID))]

def pearson(x, y):
    n = len(x)
    if n < 10: return float("nan")
    mx, my = sum(x)/n, sum(y)/n
    sx = math.sqrt(sum((v-mx)**2 for v in x)); sy = math.sqrt(sum((v-my)**2 for v in y))
    if sx == 0 or sy == 0: return float("nan")
    return sum((x[i]-mx)*(y[i]-my) for i in range(n))/(sx*sy)

print("\n" + "="*78)
for coin, (und, tgt) in BAR.items():
    bk, up = books.get(coin, []), utr.get(und, [])
    if len(bk) < 30 or len(up) < 30:
        print(f"{coin}: insufficient data (book={len(bk)} und={len(up)})"); continue
    print(f"\n### {coin}  {und} touch {tgt:g}   book obs={len(bk)}  perp prints={len(up)}")
    upx0 = up[0][1]; print(f"    {und} {upx0:.4f} -> {up[-1][1]:.4f} "
                           f"({(up[-1][1]/upx0-1)*1e4:+.1f} bps over window)")

    # gridded series
    g_mid, g_u, g_bid, g_ask, g_asz, g_bsz = [], [], [], [], [], []
    for t in grid:
        b = step(bk, t); u = step(up, t)
        if b is None or u is None:
            g_mid.append(None); g_u.append(None); g_bid.append(None)
            g_ask.append(None); g_asz.append(None); g_bsz.append(None); continue
        g_mid.append((b[1]+b[3])/2); g_bid.append(b[1]); g_ask.append(b[3])
        g_bsz.append(b[2]); g_asz.append(b[4]); g_u.append(u[1])

    ok = [i for i in range(len(grid)) if g_mid[i] is not None]
    if len(ok) < 100: print("    too few aligned points"); continue
    i0, i1 = ok[0], ok[-1]

    sp = [ (g_ask[i]-g_bid[i]) for i in range(i0,i1+1) ]
    print(f"    spread: median {st.median(sp)*100:.2f}c  "
          f"ask$ median ${st.median([g_ask[i]*g_asz[i] for i in range(i0,i1+1)]):.0f}  "
          f"bid$ median ${st.median([g_bid[i]*g_bsz[i] for i in range(i0,i1+1)]):.0f}")

    # ---- empirical delta: regress d(mid) on d(underlying) at a long horizon ----
    H = 120
    dm, du = [], []
    for i in range(i0, i1+1-H):
        if g_mid[i+H] is None or g_mid[i] is None: continue
        dm.append(g_mid[i+H]-g_mid[i]); du.append(g_u[i+H]-g_u[i])
    if len(dm) > 20 and st.pstdev(du) > 0:
        cov = sum((du[k]-sum(du)/len(du))*(dm[k]-sum(dm)/len(dm)) for k in range(len(dm)))
        var = sum((v-sum(du)/len(du))**2 for v in du)
        delta = cov/var if var else 0.0
        r = pearson(du, dm)
        print(f"    empirical delta ({H}s horizon, n={len(dm)}): {delta:.3e} /unit  "
              f"corr {r:+.3f}   [1% {und} move => {delta*upx0*0.01*100:+.2f}c]")
    else:
        delta, r = 0.0, float("nan"); print("    delta unmeasurable")

    # ---- cross-correlation of k-second changes at lags ----
    K = 10
    best = None
    print(f"    xcorr of {K}s changes (barrier vs underlying shifted by lag):")
    line = []
    for lag in (-30,-20,-15,-10,-5,-3,-2,-1,0,1,2,3,5,10,15,20,30):
        xs, ys = [], []
        for i in range(i0+max(0,-lag)+K, i1-max(0,lag)):
            j = i + lag
            if j-K < i0 or j > i1: continue
            if None in (g_mid[i], g_mid[i-K], g_u[j], g_u[j-K]): continue
            xs.append(g_mid[i]-g_mid[i-K]); ys.append(g_u[j]-g_u[j-K])
        c = pearson(xs, ys)
        line.append((lag, c, len(xs)))
        if not math.isnan(c) and (best is None or abs(c) > abs(best[1])): best = (lag, c, len(xs))
    print("      " + "  ".join(f"{l:+d}s:{c:+.2f}" for l,c,_ in line if not math.isnan(c)))
    if best: print(f"    PEAK |corr| at lag {best[0]:+d}s  corr {best[1]:+.3f}  n={best[2]}"
                   f"   ({'barrier LAGS underlying' if best[0]<0 else 'barrier LEADS/coincident'})")
