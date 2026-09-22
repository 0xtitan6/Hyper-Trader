"""Live execution cost for the hour-20 candidates: spread + walk-the-book slippage
at $640 and $10,000, plus hourly funding paid on a 1h long."""
import requests, time, json
U="https://api.hyperliquid.xyz/info"
def post(b,tries=5):
    for i in range(tries):
        try:
            r=requests.post(U,json=b,timeout=30)
            if r.status_code==429: time.sleep(5*(i+1)); continue
            r.raise_for_status(); return r.json()
        except Exception as e:
            print("  retry",repr(e)[:80]); time.sleep(2*(i+1))
    return None
COINS=["XMR","ZEC","XPL","ENA","INJ","NEAR","CRV","TAO","ZRO","BTC","ETH","SOL"]
def walk(levels, notional, mid):
    got=0.0; cost=0.0
    for lv in levels:
        px=float(lv["px"]); sz=float(lv["sz"]); avail=px*sz
        take=min(avail, notional-got)
        cost+=take/px*px*0+take   # notional taken
        got+=take
        if got>=notional-1e-9:
            # vwap computed properly below
            break
    # proper vwap
    rem=notional; qty=0.0
    for lv in levels:
        px=float(lv["px"]); sz=float(lv["sz"]); avail=px*sz
        take=min(avail,rem)
        qty+=take/px; rem-=take
        if rem<=1e-9: break
    if rem>1e-9: return None, rem
    vwap=notional/qty
    return vwap, 0.0
print(f"{'coin':<6} {'mid':>10} {'spread bp':>10} {'$640 slip bp':>13} {'$10k slip bp':>13} "
      f"{'RT cost bp':>11} {'fund bp/hr':>11} {'top5 bid $':>11}")
out={}
for c in COINS:
    b=post({"type":"l2Book","coin":c}); time.sleep(0.4)
    if not b: print(c,"no book"); continue
    bids,asks=b["levels"][0],b["levels"][1]
    bb=float(bids[0]["px"]); ba=float(asks[0]["px"]); mid=(bb+ba)/2
    spread=(ba-bb)/mid*1e4
    res={}
    for n in (640,10000):
        va,_=walk(asks,n,mid); vb,_=walk(bids,n,mid)
        if va is None or vb is None: res[n]=None; continue
        res[n]=((va-mid)/mid*1e4 + (mid-vb)/mid*1e4)   # round-trip slippage vs mid
    d=post({"type":"metaAndAssetCtxs"}); time.sleep(0.4)
    fr=None
    for m,cx in zip(d[0]["universe"],d[1]):
        if m["name"]==c: fr=float(cx["funding"])*1e4
    depth5=sum(float(l["px"])*float(l["sz"]) for l in bids[:5])
    s640=res[640]; s10k=res[10000]
    rt = 9.0 + (s640 if s640 else float('nan'))
    out[c]=(spread,s640,s10k,rt,fr)
    print(f"{c:<6} {mid:>10.4f} {spread:>10.2f} "
          f"{(f'{s640:.2f}' if s640 else 'THIN'):>13} {(f'{s10k:.2f}' if s10k else 'THIN'):>13} "
          f"{rt:>11.2f} {(f'{fr:+.3f}' if fr is not None else 'na'):>11} {depth5:>11.0f}")
print("\nRT cost bp = 9bp taker fee + round-trip slippage-vs-mid at $640.")
print("A 1h long also pays 1 funding print: cost = funding bp/hr if positive.")
json.dump(out,open("/tmp/tod_cost.json","w"))
