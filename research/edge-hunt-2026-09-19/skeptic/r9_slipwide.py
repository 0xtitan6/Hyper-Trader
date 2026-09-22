import requests,time,json,statistics
U="https://api.hyperliquid.xyz/info"
def post(b,tries=5):
    for i in range(tries):
        try:
            r=requests.post(U,json=b,timeout=30)
            if r.status_code==429: time.sleep(5*(i+1)); continue
            r.raise_for_status(); return r.json()
        except Exception: time.sleep(2*(i+1))
    return None
def vwap(lv,n):
    rem=n; qty=0.0
    for l in lv:
        px=float(l["px"]); avail=px*float(l["sz"]); take=min(avail,rem); qty+=take/px; rem-=take
        if rem<=1e-9: break
    return None if rem>1e-9 else n/qty
S=[]
for k in range(26):
    b=post({"type":"l2Book","coin":"XMR"})
    if b:
        bid,ask=b["levels"][0],b["levels"][1]
        bb=float(bid[0]["px"]); ba=float(ask[0]["px"]); mid=(bb+ba)/2
        r={"ts":time.time(),"sp":(ba-bb)/mid*1e4,
           "bidbook":sum(float(l["px"])*float(l["sz"]) for l in bid),
           "askbook":sum(float(l["px"])*float(l["sz"]) for l in ask),
           "worstbid_bp":(mid-float(bid[-1]["px"]))/mid*1e4}
        for n in (640,2000,10000):
            va=vwap(ask,n); vb=vwap(bid,n)
            r[f"rt{n}"]=None if (va is None or vb is None) else ((va-mid)+(mid-vb))/mid*1e4
        S.append(r)
    time.sleep(18)
json.dump(S,open("/tmp/xmr_wide.json","w"))
print("n snaps",len(S))
for n in (640,2000,10000):
    v=[s[f"rt{n}"] for s in S if s[f"rt{n}"]]; miss=len(S)-len(v)
    print(f"${n:>6} RT slip: n={len(v)} median {statistics.median(v):.2f} mean {statistics.mean(v):.2f} min {min(v):.2f} max {max(v):.2f}  unfillable(20 lvls) {miss}/{len(S)}" if v else f"${n}: all unfillable")
sp=[s["sp"] for s in S]; print(f"spread: median {statistics.median(sp):.2f}bp mean {statistics.mean(sp):.2f} min {min(sp):.2f} max {max(sp):.2f}")
bb=[s["bidbook"] for s in S]; print(f"visible bid book $: median {statistics.median(bb):,.0f} min {min(bb):,.0f} max {max(bb):,.0f}; frac<$10k {sum(1 for v in bb if v<10000)/len(bb):.2f}")
