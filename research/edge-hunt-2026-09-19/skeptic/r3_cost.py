import requests,time,json
U="https://api.hyperliquid.xyz/info"
def post(b,tries=5):
    for i in range(tries):
        try:
            r=requests.post(U,json=b,timeout=30)
            if r.status_code==429: time.sleep(5*(i+1)); continue
            r.raise_for_status(); return r.json()
        except Exception as e: time.sleep(2*(i+1))
    return None
coins=json.load(open("/tmp/coins.json"))
d=post({"type":"metaAndAssetCtxs"}); time.sleep(0.4)
fund={m["name"]:float(cx["funding"])*1e4 for m,cx in zip(d[0]["universe"],d[1])}
oi={m["name"]:float(cx["openInterest"])*float(cx["markPx"]) for m,cx in zip(d[0]["universe"],d[1])}
def vwap(levels,notional):
    rem=notional; qty=0.0
    for lv in levels:
        px=float(lv["px"]); sz=float(lv["sz"]); avail=px*sz
        take=min(avail,rem); qty+=take/px; rem-=take
        if rem<=1e-9: break
    if rem>1e-9: return None
    return notional/qty
out={}
print(f"{'coin':<9}{'mid':>12}{'sprd bp':>9}{'slip640':>9}{'slip10k':>9}{'fund/hr':>9}{'all-in640':>10}{'all-in10k':>10}{'OI $M':>8}")
for c in coins:
    b=post({"type":"l2Book","coin":c}); time.sleep=getattr(time,'sleep'); time.sleep(0.35)
    if not b: print(c,"nobook"); continue
    bids,asks=b["levels"][0],b["levels"][1]
    bb=float(bids[0]["px"]); ba=float(asks[0]["px"]); mid=(bb+ba)/2
    sp=(ba-bb)/mid*1e4
    res={}
    for n in (640,10000):
        va=vwap(asks,n); vb=vwap(bids,n)
        res[n]=None if (va is None or vb is None) else ((va-mid)+(mid-vb))/mid*1e4
    fr=fund.get(c,0.125)
    a640=9.0+(res[640] if res[640] else float('nan'))+max(fr,0)
    a10k=9.0+(res[10000] if res[10000] else float('nan'))+max(fr,0)
    out[c]={"mid":mid,"spread":sp,"s640":res[640],"s10k":res[10000],"fund":fr,"a640":a640,"a10k":a10k,"oi":oi.get(c)}
    print(f"{c:<9}{mid:>12.5f}{sp:>9.2f}{(f'{res[640]:.2f}' if res[640] else 'THIN'):>9}{(f'{res[10000]:.2f}' if res[10000] else 'THIN'):>9}{fr:>+9.3f}{a640:>10.2f}{a10k:>10.2f}{(oi.get(c) or 0)/1e6:>8.1f}")
json.dump(out,open("/tmp/cost36.json","w"))
