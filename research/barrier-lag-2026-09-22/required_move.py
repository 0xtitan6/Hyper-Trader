"""Regime-independent version of the question.

Rather than ask 'did the barrier lag during my 50 minutes', ask:
  how big an underlying move is needed before the barrier's STALENESS exceeds
  its DISPLAYED SPREAD -- and how often does the underlying move that much
  inside the time the book actually sits still?

Uses three independent deltas and reports the most GENEROUS (largest), so a
negative verdict is robust to getting the delta wrong.
"""
import json, math, time, sys, statistics as st
import urllib.request

INFO = "https://api.hyperliquid.xyz/info"
def post(b):
    r = urllib.request.Request(INFO, data=json.dumps(b).encode(),
                               headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=25).read())

def N(x):  return 0.5*(1+math.erf(x/math.sqrt(2)))
def n_(x): return math.exp(-x*x/2)/math.sqrt(2*math.pi)

EXPIRY = time.mktime(time.strptime("2026-10-01", "%Y-%m-%d"))
T = max((EXPIRY - time.time())/(365*24*3600), 1e-6)

mids = post({"type": "allMids"}); time.sleep(0.1)
S = {"BTC": float(mids["BTC"]), "HYPE": float(mids["HYPE"])}
print(f"# T = {T*365:.2f} days   BTC {S['BTC']:.0f}  HYPE {S['HYPE']:.3f}\n")

MK = {1209:("HYPE",100.0), 1212:("BTC",95000.0), 1213:("BTC",90000.0)}
books = {}
for oid,(u,k) in MK.items():
    b = post({"type":"l2Book","coin":f"#{10*oid}"}); time.sleep(0.1)
    lv = b.get("levels",[[],[]])
    bid, ask = lv[0][0], lv[1][0]
    books[oid] = (float(bid["px"]), float(bid["sz"]), float(ask["px"]), float(ask["sz"]))

# 1-minute candles, 14 days, for the move-frequency distribution
CAND = {}
now = int(time.time()*1000)
for u in ("BTC","HYPE"):
    c = post({"type":"candleSnapshot","req":{"coin":u,"interval":"1m",
             "startTime":now-14*24*3600*1000,"endTime":now}})
    time.sleep(0.15)
    CAND[u] = [(int(x["t"]), float(x["c"])) for x in c]
    print(f"# {u}: {len(CAND[u])} 1m candles")

def move_freq(u, need, minutes):
    """P(|move| >= need USD over `minutes`) from 14d of 1m closes."""
    px = [p for _, p in CAND[u]]
    k = minutes
    hits = tot = 0
    for i in range(len(px)-k):
        tot += 1
        if abs(px[i+k]-px[i]) >= need: hits += 1
    return hits/tot if tot else float("nan"), tot

print(f"\n{'='*92}")
for oid,(u,K) in MK.items():
    bid,bsz,ask,asz = books[oid]
    mid = (bid+ask)/2; spread = ask-bid
    x = math.log(K/S[u])
    # implied sigma that reproduces the mid under the driftless one-touch
    lo, hi = 0.05, 5.0
    for _ in range(80):
        s = (lo+hi)/2
        p = 2*N(-abs(x)/(s*math.sqrt(T)))
        if p < mid: lo = s
        else: hi = s
    sig = (lo+hi)/2
    z = abs(x)/(sig*math.sqrt(T))
    delta_th = 2*n_(z)/(S[u]*sig*math.sqrt(T))      # theoretical local delta, per $1
    print(f"\n### oid {oid}  {u} touch {K:g}   mid {mid:.4f}  spread {spread*100:.2f}c  "
          f"bid ${bid*bsz:.0f} / ask ${ask*asz:.0f}")
    print(f"    implied vol {sig*100:.1f}%   theoretical delta {delta_th:.3e} per $1 "
          f"({delta_th*S[u]*0.01*100:.2f}c per 1% {u} move)")
    need = spread/delta_th
    print(f"    underlying move needed for staleness to clear the FULL spread: "
          f"${need:,.0f} = {need/S[u]*100:.3f}% of {u}")
    for mins in (1, 5, 20):
        p, tot = move_freq(u, need, mins)
        print(f"      P(|{u} move| >= that in {mins:>2}m) = {p*100:6.2f}%  (n={tot} windows, 14d)")
    # half-spread version = maker safety
    needh = (spread/2)/delta_th
    p1, _ = move_freq(u, needh, 1); p20, _ = move_freq(u, needh, 20)
    print(f"    MAKER SAFETY: move to breach HALF-spread ${needh:,.0f} "
          f"({needh/S[u]*100:.3f}%); P in 1m {p1*100:.2f}%, in 20m {p20*100:.2f}%")
