"""Sample XMR (+BTC/ETH ref) L2 repeatedly: spread distribution + true walk-the-book
round-trip slippage-vs-mid at $640 / $2k / $10k / $25k. 40 snapshots ~ 3.5 min."""
import requests,time,json,statistics as st
U="https://api.hyperliquid.xyz/info"
def post(b,tries=6):
    for i in range(tries):
        try:
            r=requests.post(U,json=b,timeout=30)
            if r.status_code==429: time.sleep(5*(i+1)); continue
            r.raise_for_status(); return r.json()
        except Exception as e: time.sleep(2*(i+1))
    return None
def walk(levels,notional):
    rem=notional; qty=0.0
    for lv in levels:
        px=float(lv["px"]); sz=float(lv["sz"]); avail=px*sz
        take=min(avail,rem); qty+=take/px; rem-=take
        if rem<=1e-9: break
    if rem>1e-9: return None
    return notional/qty
NOT=[640,2000,10000,25000]
rows={c:[] for c in ("XMR","BTC","ETH")}
for k in range(40):
    for c in rows:
        b=post({"type":"l2Book","coin":c})
        if not b: continue
        bids,asks=b["levels"][0],b["levels"][1]
        bb=float(bids[0]["px"]); ba=float(asks[0]["px"]); mid=(bb+ba)/2
        rec={"t":time.time(),"mid":mid,"spread_bp":(ba-bb)/mid*1e4,
             "nlev":(len(bids),len(asks)),
             "bidtop5":sum(float(l['px'])*float(l['sz']) for l in bids[:5]),
             "asktop5":sum(float(l['px'])*float(l['sz']) for l in asks[:5]),
             "biddepth_all":sum(float(l['px'])*float(l['sz']) for l in bids),
             "askdepth_all":sum(float(l['px'])*float(l['sz']) for l in asks)}
        for n in NOT:
            va=walk(asks,n); vb=walk(bids,n)
            rec[f"rt_{n}"]=None if (va is None or vb is None) else ((va-mid)+(mid-vb))/mid*1e4
        rows[c].append(rec)
        time.sleep(0.35)
json.dump(rows,open("/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/skeptic_exec/l2_samples.json","w"))
for c,rs in rows.items():
    sp=[r["spread_bp"] for r in rs]
    print(f"\n=== {c}  n={len(rs)} snapshots  mid~{st.mean([r['mid'] for r in rs]):.4f}")
    print(f"  spread bp: mean {st.mean(sp):.3f} median {st.median(sp):.3f} min {min(sp):.3f} max {max(sp):.3f} p90 {sorted(sp)[int(.9*len(sp))]:.3f}")
    print(f"  levels returned: {rs[0]['nlev']}  top5 bid ${st.mean([r['bidtop5'] for r in rs]):,.0f}  all-level bid ${st.mean([r['biddepth_all'] for r in rs]):,.0f}")
    for n in NOT:
        v=[r[f"rt_{n}"] for r in rs if r[f"rt_{n}"] is not None]
        nf=sum(1 for r in rs if r[f"rt_{n}"] is None)
        print(f"  RT slip vs mid ${n}: mean {st.mean(v):.2f}bp median {st.median(v):.2f} max {max(v):.2f}  (unfillable in book {nf}/{len(rs)})" if v else f"  RT ${n}: unfillable in visible book {nf}/{len(rs)}")
