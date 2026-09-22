"""Can we pick off a stale barrier quote?

Method, anchored to remove model bias:
  1. Find each moment the barrier top-of-book CHANGES (a requote, t_q).
  2. Calibrate the one-touch implied vol so fair(t_q) == mid(t_q) EXACTLY.
     The model therefore contributes zero level bias; it only propagates the
     underlying's subsequent move.
  3. While the quote sits unchanged, track fair(t) as the underlying moves.
     Signal when fair(t) > ask(t_q): the displayed ask is now stale-cheap.
  4. Score honestly: we bought at the displayed ask; exit is the displayed BID
     later (round trip crosses the spread both ways). Size is the displayed size.
"""
import json, sys, math, time, statistics as st
from collections import defaultdict

TAPE = sys.argv[1]
BAR = {"#12090": ("HYPE", 100.0), "#12120": ("BTC", 95000.0), "#12130": ("BTC", 90000.0)}
EXPIRY = time.mktime(time.strptime("2026-10-01", "%Y-%m-%d"))
MIN_ORDER = 10.0

def N(x): return 0.5*(1+math.erf(x/math.sqrt(2)))
def touch(S, K, sig, T):
    if T <= 0 or sig <= 0: return 0.0
    return min(1.0, 2*N(-abs(math.log(K/S))/(sig*math.sqrt(T))))
def implied(S, K, T, price):
    price = min(max(price, 1e-4), 0.999)
    lo, hi = 0.02, 8.0
    for _ in range(60):
        m = (lo+hi)/2
        if touch(S, K, m, T) < price: lo = m
        else: hi = m
    return (lo+hi)/2

recs = [json.loads(l) for l in open(TAPE)]
utr, books, btr = defaultdict(list), defaultdict(list), defaultdict(list)
for r in recs:
    if r["k"] == "utrade": utr[r["coin"]].append((r["lt"], float(r["px"])))
    elif r["k"] == "btrade": btr[r["coin"]].append((r["lt"], float(r["px"]), float(r["sz"])))
    elif r["k"] in ("rest","book") and r.get("b") and r.get("a"):
        books[r["coin"]].append((r["lt"], float(r["b"][0][0]), float(r["b"][0][1]),
                                 float(r["a"][0][0]), float(r["a"][0][1])))
for d in (utr, books, btr):
    for c in d: d[c].sort()

def step(s, t):
    if not s or s[0][0] > t: return None
    lo, hi = 0, len(s)-1
    while lo < hi:
        m = (lo+hi+1)//2
        if s[m][0] <= t: lo = m
        else: hi = m-1
    return s[lo]

print(f"# tape {TAPE}")
for coin, (und, K) in BAR.items():
    bk, up = books.get(coin, []), utr.get(und, [])
    if len(bk) < 50 or len(up) < 50:
        print(f"\n### {coin}: insufficient data"); continue
    T0 = (EXPIRY - bk[0][0])/(365*24*3600)
    print("\n" + "="*84)
    print(f"### {coin}  {und} touch {K:g}   polls={len(bk)}  perp prints={len(up)}  "
          f"barrier prints={len(btr.get(coin,[]))}")
    spreads = [b[3]-b[1] for b in bk]
    print(f"    spread: median {st.median(spreads)*100:.2f}c  p10 {sorted(spreads)[len(spreads)//10]*100:.2f}c  "
          f"p90 {sorted(spreads)[9*len(spreads)//10]*100:.2f}c")
    asks_usd = [b[3]*b[4] for b in bk]
    print(f"    displayed ASK size: median ${st.median(asks_usd):.0f}  "
          f"p10 ${sorted(asks_usd)[len(asks_usd)//10]:.0f}  "
          f">=$10 on {sum(1 for a in asks_usd if a>=MIN_ORDER)/len(asks_usd)*100:.0f}% of polls")

    # requote segments: consecutive polls with an unchanged top of book
    segs, i = [], 0
    while i < len(bk):
        j = i
        while j+1 < len(bk) and (bk[j+1][1], bk[j+1][3]) == (bk[i][1], bk[i][3]): j += 1
        segs.append((i, j)); i = j+1
    durs = [bk[e][0]-bk[s][0] for s, e in segs]
    print(f"    quote segments: {len(segs)}  median life {st.median(durs):.1f}s  "
          f"p90 {sorted(durs)[int(.9*len(durs))]:.1f}s  max {max(durs):.0f}s")

    sigs, skipped_size = [], 0
    for s, e in segs:
        t_q, bid, bsz, ask, asz = bk[s]
        u_q = step(up, t_q)
        if not u_q: continue
        mid = (bid+ask)/2
        sig = implied(u_q[1], K, T0, mid)
        if not (0.03 < sig < 7.0): continue
        best = None
        k = s
        while k <= e:
            t = bk[k][0]
            u = step(up, t)
            if u:
                fair = touch(u[1], K, sig, T0)
                if fair > ask and (best is None or fair-ask > best[1]):
                    best = (t, fair-ask, u[1])
            k += 1
        if best:
            t_s, edge, u_s = best
            if ask*asz < MIN_ORDER: skipped_size += 1; continue
            outs = {}
            for H in (30, 60, 120, 300):
                bf = step(bk, t_s+H)
                outs[H] = (bf[1]-ask) if bf else None      # exit at the displayed BID
            sigs.append({"t": t_s, "edge": edge, "ask": ask, "usd": ask*asz,
                         "lag": t_s-t_q, "out": outs})

    print(f"    stale-ask signals: {len(sigs)} tradeable (+{skipped_size} rejected: "
          f"ask size < ${MIN_ORDER:.0f} minimum)")
    if not sigs:
        print("    -> no tradeable pickoff opportunity in this sample"); continue
    print(f"    model staleness at signal: median {st.median([s['edge'] for s in sigs])*100:+.2f}c "
          f"({st.median([s['edge'] for s in sigs])*1e4:+.0f} bps of face)")
    print(f"    size available: median ${st.median([s['usd'] for s in sigs]):.0f}")
    print(f"    time from requote to signal: median {st.median([s['lag'] for s in sigs]):.0f}s")
    for H in (30, 60, 120, 300):
        v = [s["out"][H] for s in sigs if s["out"][H] is not None]
        if len(v) < 3: continue
        bps = [x*1e4 for x in v]
        mean = sum(bps)/len(bps)
        se = st.pstdev(bps)/math.sqrt(len(bps)) if len(bps) > 1 else float("nan")
        print(f"    REALISED round trip (buy ask, sell bid) +{H:>3}s: median {st.median(bps):+8.0f} "
              f"| mean {mean:+8.0f} +/- {se:.0f} se | win {sum(1 for x in bps if x>0)}/{len(bps)} bps of face")

# --- does the maker PULL size when the underlying moves? ---
print("\n" + "#"*84)
print("# Does displayed ask size shrink when the underlying moves? (the pull test)")
for coin,(und,K) in BAR.items():
    bk,up = books.get(coin,[]), utr.get(und,[])
    if len(bk)<80 or len(up)<80: continue
    t0,t1 = max(bk[0][0],up[0][0]), min(bk[-1][0],up[-1][0])
    rows=[]
    t=t0+30
    while t<t1:
        ua,ub = step(up,t-30), step(up,t); b = step(bk,t)
        if ua and ub and b:
            rows.append((abs(ub[1]/ua[1]-1), b[3]*b[4]))
        t+=2
    if len(rows)<50: continue
    rows.sort(key=lambda r:r[0])
    q=len(rows)//4
    calm=[r[1] for r in rows[:q]]; busy=[r[1] for r in rows[-q:]]
    print(f"  {coin}: ask$ median  calmest quartile ${st.median(calm):.0f}  "
          f"busiest quartile ${st.median(busy):.0f}   "
          f"(busiest-quartile 30s move >= {rows[-q][0]*100:.3f}%)")
