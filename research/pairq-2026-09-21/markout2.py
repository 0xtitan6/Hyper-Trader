"""Markout in bps of FACE ($1/share) — the natural risk unit for a binary.
Earlier pass normalised by px, so legs trading at 0.002 produced 500,000 bps
means. Price-space, winsorised, and with the fee expressed in the same unit."""
import json, collections, statistics as st, sys
T=[]
for fn in ("trades.jsonl","trades_all.jsonl"):
    for l in open(f"research/pairq-2026-09-21/{fn}"): T.append(json.loads(l))
seen=set(); Y=[]
for t in T:
    c=int(t["coin"][1:])
    if c%2: continue
    k=(t["hash"],t["tid"],c)
    if k in seen: continue
    seen.add(k); Y.append(t)
Y.sort(key=lambda t:t["time"])
bysurf=collections.defaultdict(list)
for t in Y: bysurf[int(t["coin"][1:])//10].append(t)

MF=json.load(open("research/pairq-2026-09-21/maker_fills.json"))
CLUSTER={a.lower() for a in MF if 1000<len([f for f in MF[a] if f["coin"].startswith("#")])<3000}
HOR=[5,15,30,60,300,900]

def run(filt,label):
    res=collections.defaultdict(list); npf=0
    for oid,tl in bysurf.items():
        times=[t["time"] for t in tl]; pxs=[float(t["px"]) for t in tl]
        for i,t in enumerate(tl):
            px=float(t["px"])
            if not (0.05<=px<=0.95): continue      # face-value tails are not quotable anyway
            if not filt(t): continue
            npf+=1
            mside=1 if t["side"]=="A" else -1
            for h in HOR:
                lo=t["time"]+h*1000; hi=lo+180_000
                w=[pxs[j] for j in range(i+1,len(tl)) if lo<=times[j]<=hi]
                if w: res[h].append(mside*(st.mean(w)-px)*1e4)
    print(f"\n=== {label} ===  passive fills scored: {npf:,}")
    print(f"{'horizon':>8} {'n':>6} {'median':>8} {'trim.mean':>10} {'t(trim)':>8}")
    for h in HOR:
        v=sorted(res[h])
        if len(v)<40: print(f"{h:>7}s {len(v):>6}   (too few)"); continue
        k=max(1,len(v)//20); tv=v[k:-k]                # 5% winsor each tail
        m=st.mean(tv); sd=st.stdev(tv)
        print(f"{h:>7}s {len(v):>6} {st.median(v):>8.2f} {m:>10.2f} "
              f"{m/(sd/len(tv)**0.5):>8.2f}")
    return res

run(lambda t: True,"ALL passive fills")
run(lambda t: t["users"][0].lower() not in CLUSTER and t["users"][1].lower() not in CLUSTER,
    "PURE THIRD-PARTY FLOW (no reward-farm wallet on either side)")

print("""
COST FLOOR IN THE SAME UNIT (bps of $1 face, at a typical px=0.50):
  our quoted half-spread captured if we are the passive side ... +10.1 bps
      (median book spread 0.202% face => half = 10.1 bps)
  taker fee if we cross to complete       8.97bps x 0.50 face =  -4.5 bps
  settlement fee on the completed basket          13.4bps x 1  = -13.4 bps
  one tick of price improvement given up                       =  -5.0 bps
""")
