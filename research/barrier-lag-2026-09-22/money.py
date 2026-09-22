"""The economic test: when the underlying moves, is the barrier's DISPLAYED ask
still stale enough to pick off -- and is there size behind it?

No synthesised prices. Asks, bids and sizes are the ones actually shown.
Costs: buys measured 0.00 bps (MEASURED.md n=21,515); exit is maker-sell
7.83 bps of notional or settlement 13.27 bps of face.
"""
import json, sys, math, statistics as st
from collections import defaultdict

TAPE = sys.argv[1]
BAR = {"#12090": ("HYPE", 100.0), "#12120": ("BTC", 95000.0), "#12130": ("BTC", 90000.0)}
EXIT_BPS_NOTIONAL = 7.83
LOOKBACK = 10.0          # underlying move window
HORIZONS = [30, 60, 120] # markout horizons (s)

recs = [json.loads(l) for l in open(TAPE)]
utr, books = defaultdict(list), defaultdict(list)
for r in recs:
    if r["k"] == "utrade": utr[r["coin"]].append((r["lt"], float(r["px"])))
    elif r["k"] in ("rest", "book") and r.get("b") and r.get("a"):
        books[r["coin"]].append((r["lt"], float(r["b"][0][0]), float(r["b"][0][1]),
                                 float(r["a"][0][0]), float(r["a"][0][1])))
for d in (utr, books):
    for c in d: d[c].sort()

def step(s, t):
    if not s or s[0][0] > t: return None
    lo, hi = 0, len(s)-1
    while lo < hi:
        m = (lo+hi+1)//2
        if s[m][0] <= t: lo = m
        else: hi = m-1
    return s[lo]

for coin, (und, tgt) in BAR.items():
    bk, up = books.get(coin, []), utr.get(und, [])
    if len(bk) < 50 or len(up) < 50: continue
    t0, t1 = max(bk[0][0], up[0][0]), min(bk[-1][0], up[-1][0])
    print("\n" + "="*78)
    print(f"### {coin}  {und} touch {tgt:g}")

    # --- how often does the top of book actually change? (the requote clock) ---
    chg = [bk[i][0] for i in range(1, len(bk)) if (bk[i][1], bk[i][3]) != (bk[i-1][1], bk[i-1][3])]
    gaps = [chg[i]-chg[i-1] for i in range(1, len(chg))]
    frac = len(chg)/max(1, len(bk)-1)
    print(f"    top-of-book changed on {len(chg)}/{len(bk)-1} polls ({frac*100:.1f}%); "
          + (f"median gap {st.median(gaps):.1f}s, p90 {sorted(gaps)[int(.9*len(gaps))]:.1f}s"
             if len(gaps) > 5 else "too few changes to time"))

    # --- empirical delta over a long horizon (lag-insensitive) ---
    H = 120; dm, du = [], []
    t = t0
    while t < t1 - H:
        a, b = step(bk, t), step(bk, t+H); ua, ub = step(up, t), step(up, t+H)
        if a and b and ua and ub:
            dm.append((b[1]+b[3])/2 - (a[1]+a[3])/2); du.append(ub[1]-ua[1])
        t += 5
    if len(dm) < 20 or st.pstdev(du) == 0:
        print("    delta unmeasurable -- skipping money test"); continue
    mu_u, mu_m = sum(du)/len(du), sum(dm)/len(dm)
    var = sum((v-mu_u)**2 for v in du)
    delta = sum((du[k]-mu_u)*(dm[k]-mu_m) for k in range(len(dm)))/var if var else 0.0
    sx = math.sqrt(var); sy = math.sqrt(sum((v-mu_m)**2 for v in dm))
    corr = (sum((du[k]-mu_u)*(dm[k]-mu_m) for k in range(len(dm)))/(sx*sy)) if sx and sy else float("nan")
    print(f"    delta={delta:.3e}/unit (n={len(dm)}, corr {corr:+.2f})")
    if delta <= 0 or math.isnan(corr) or corr < 0.1:
        print("    *** barrier does not track underlying in this sample -- money test void ***")
        continue

    # --- event study: underlying moves, can we buy the stale ask? ---
    rows = []
    t = t0 + LOOKBACK
    while t < t1 - max(HORIZONS):
        ua, ub = step(up, t-LOOKBACK), step(up, t)
        b_now, b_then = step(bk, t), step(bk, t-LOOKBACK)
        if not (ua and ub and b_now and b_then): t += 2; continue
        dU = ub[1]-ua[1]
        fair_shift = delta*dU                      # predicted barrier repricing
        mid_then = (b_then[1]+b_then[3])/2
        fair = mid_then + fair_shift
        if fair_shift > 0:                          # underlying moved UP -> buy YES at ask
            px, sz = b_now[3], b_now[4]
            edge_disp = fair - px                   # displayed staleness vs predicted fair
            side = "BUY"
        else:
            t += 2; continue
        mks = {}
        for Hh in HORIZONS:
            bf = step(bk, t+Hh)
            mks[Hh] = ((bf[1]+bf[3])/2 - px) if bf else None
        rows.append({"t": t, "dU": dU, "shift": fair_shift, "px": px, "sz": sz,
                     "usd": px*sz, "edge": edge_disp, "mk": mks})
        t += 2

    if not rows: print("    no qualifying events"); continue
    shifts = sorted(abs(r["shift"]) for r in rows)
    thr = shifts[int(0.90*len(shifts))]             # top decile of predicted repricing
    big = [r for r in rows if r["shift"] >= thr]
    print(f"    events: {len(rows)} sampled, {len(big)} in top decile "
          f"(predicted repricing >= {thr*100:.3f}c)")
    print(f"    median displayed ask size on those events: ${st.median([r['usd'] for r in big]):.0f}")
    ed = [r["edge"] for r in big]
    print(f"    displayed staleness (fair-ask): median {st.median(ed)*100:+.3f}c  "
          f"positive on {sum(1 for e in ed if e>0)}/{len(ed)}")
    for Hh in HORIZONS:
        v = [r["mk"][Hh] for r in big if r["mk"][Hh] is not None]
        if len(v) < 5: continue
        face_bps = [x/1.0*1e4 for x in v]           # 1 share redeems $1.00 -> bps of face
        net = [f - EXIT_BPS_NOTIONAL*st.median([r['px'] for r in big]) for f in face_bps]
        m = st.median(face_bps)
        se = (st.pstdev(face_bps)/math.sqrt(len(face_bps))) if len(face_bps) > 1 else float('nan')
        mean = sum(face_bps)/len(face_bps)
        print(f"    markout +{Hh:>3}s: median {m:+7.1f} bps face | mean {mean:+7.1f} "
              f"+/- {se:.1f} se | win {sum(1 for x in face_bps if x>0)}/{len(face_bps)} | n={len(face_bps)}")

    # --- maker safety: time for predicted repricing to exceed the half-spread ---
    hs = st.median([(b[3]-b[1])/2 for b in bk])
    hits = []
    t = t0
    while t < t1 - 120:
        u_ref = step(up, t)
        if not u_ref: t += 5; continue
        tt, hit = t+1, None
        while tt < t+120:
            u2 = step(up, tt)
            if u2 and abs(delta*(u2[1]-u_ref[1])) >= hs: hit = tt-t; break
            tt += 1
        hits.append(hit if hit else 120)
        t += 5
    if hits:
        surv = sum(1 for h in hits if h >= 120)/len(hits)
        print(f"    maker safety: half-spread {hs*100:.2f}c; median time for the underlying "
              f"to move it {st.median(hits):.0f}s; quote survives 120s {surv*100:.0f}% (n={len(hits)})")
