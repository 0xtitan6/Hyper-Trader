import requests,time,json,statistics
U="https://api.hyperliquid.xyz/info"
def post(b,tries=5):
    for i in range(tries):
        try:
            r=requests.post(U,json=b,timeout=30)
            if r.status_code==429: time.sleep(5*(i+1)); continue
            r.raise_for_status(); return r.json()
        except Exception as e: time.sleep(2*(i+1))
    return None
def vwap(levels,notional):
    rem=notional; qty=0.0
    for lv in levels:
        px=float(lv["px"]); sz=float(lv["sz"]); avail=px*sz
        take=min(avail,rem); qty+=take/px; rem-=take
        if rem<=1e-9: break
    if rem>1e-9: return None
    return notional/qty
snaps=[]
for k in range(12):
    b=post({"type":"l2Book","coin":"XMR"})
    if not b: time.sleep(1); continue
    bids,asks=b["levels"][0],b["levels"][1]
    bb=float(bids[0]["px"]); ba=float(asks[0]["px"]); mid=(bb+ba)/2
    sp=(ba-bb)/mid*1e4
    dtop=float(bids[0]["px"])*float(bids[0]["sz"]); atop=float(asks[0]["px"])*float(asks[0]["sz"])
    dbid=sum(float(l["px"])*float(l["sz"]) for l in bids); dask=sum(float(l["px"])*float(l["sz"]) for l in asks)
    row={"sp":sp,"mid":mid,"nlev":(len(bids),len(asks)),"topbid$":dtop,"topask$":atop,"bookbid$":dbid,"bookask$":dask}
    for n in (640,2000,5000,10000):
        va=vwap(asks,n); vb=vwap(bids,n)
        row[f"rt{n}"]=None if (va is None or vb is None) else ((va-mid)+(mid-vb))/mid*1e4
    snaps.append(row)
    print(f"snap{k}: sp={sp:.2f}bp lev={row['nlev']} topbid=${dtop:,.0f} topask=${atop:,.0f} fullbook=${dbid:,.0f}/${dask:,.0f} "
          + " ".join(f"RT${n//1000 if n>=1000 else n}{'k' if n>=1000 else ''}="+(f"{row[f'rt{n}']:.2f}" if row[f'rt{n}'] else "THIN") for n in (640,2000,5000,10000)))
    time.sleep(2.0)
for n in (640,2000,5000,10000):
    v=[s[f"rt{n}"] for s in snaps if s[f"rt{n}"]]
    miss=sum(1 for s in snaps if not s[f"rt{n}"])
    if v: print(f"\n${n}: RT slip median {statistics.median(v):.2f}bp  mean {statistics.mean(v):.2f}  min {min(v):.2f} max {max(v):.2f}  unfillable {miss}/{len(snaps)}")
    else: print(f"\n${n}: unfillable in all {len(snaps)} snaps")
print("spread median %.2fbp"%statistics.median([s["sp"] for s in snaps]))
json.dump(snaps,open("/tmp/xmr_snaps.json","w"))
