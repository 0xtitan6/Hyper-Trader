"""Adverse-selection markout on PASSIVE fills, from the public tape.

A maker who buys at the bid earns the half-spread and then loses whatever the
price does next. markout(h) = (mark(t+h) - fill) signed by the maker's side.
If markout is <= 0 at every horizon, quoting this book is not profitable no
matter how the inventory is managed.

Marks use the MEAN trade price in [t+h, t+h+180s] to damp bid/ask bounce.
"""
import json, collections, statistics as st, sys

T=[]
for fn in ("trades.jsonl","trades_all.jsonl"):
    for l in open(f"research/pairq-2026-09-21/{fn}"):
        T.append(json.loads(l))
# dedupe (same trade arrives on both legs and from both collectors); keep YES leg
seen=set(); Y=[]
for t in T:
    c=int(t["coin"][1:])
    if c%2: continue                      # NO leg is the exact mirror
    k=(t["hash"],t["tid"],c)
    if k in seen: continue
    seen.add(k); Y.append(t)
Y.sort(key=lambda t:t["time"])
bysurf=collections.defaultdict(list)
for t in Y: bysurf[int(t["coin"][1:])//10].append(t)
print(f"unique YES-leg trades: {len(Y):,} across {len(bysurf)} surfaces", file=sys.stderr)

CLUSTER={a.lower() for a in json.load(open("research/pairq-2026-09-21/maker_fills.json"))
         if 1000 < len([f for f in json.load(open("research/pairq-2026-09-21/maker_fills.json"))[a]
                        if f["coin"].startswith("#")]) < 3000}

HOR=[5,15,30,60,300,900,3600]
def run(filt, label):
    res=collections.defaultdict(list)
    npf=0
    for oid,tl in bysurf.items():
        times=[t["time"] for t in tl]; pxs=[float(t["px"]) for t in tl]
        for i,t in enumerate(tl):
            if not filt(t): continue
            npf+=1
            px=float(t["px"])
            mside = 1 if t["side"]=="A" else -1     # aggressor sold => maker BOUGHT
            for h in HOR:
                lo=t["time"]+h*1000; hi=lo+180_000
                w=[pxs[j] for j in range(i+1,len(tl)) if lo<=times[j]<=hi]
                if not w: continue
                res[h].append(mside*(st.mean(w)-px)/px*1e4)   # bps of notional
    print(f"\n=== {label} ===   passive fills scored: {npf:,}")
    print(f"{'horizon':>8} {'n':>6} {'median bps':>11} {'mean bps':>10} {'t':>7}")
    for h in HOR:
        v=res[h]
        if len(v)<25: print(f"{h:>7}s {len(v):>6}   (too few)"); continue
        m=st.mean(v); sd=st.stdev(v)
        print(f"{h:>7}s {len(v):>6} {st.median(v):>11.2f} {m:>10.2f} "
              f"{m/(sd/len(v)**0.5):>7.2f}")
    return res

run(lambda t: True, "ALL passive fills")
run(lambda t: not (t["users"][0].lower() in CLUSTER and t["users"][1].lower() in CLUSTER),
    "EXCLUDING cluster-internal trades (independent of the wash-farm)")
run(lambda t: t["users"][0].lower() not in CLUSTER and t["users"][1].lower() not in CLUSTER,
    "NEITHER side in cluster (pure third-party flow)")
