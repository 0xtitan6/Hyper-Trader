import json, collections
F=json.load(open("research/pairq-2026-09-21/maker_fills.json"))
M=json.load(open("research/pairq-2026-09-21/marks.json"))
rows=[]
for a,fl in F.items():
    of=[f for f in fl if f["coin"].startswith("#")]
    cash=fees=notion=0.0; pos=collections.Counter(); nmk=ntk=0
    for f in of:
        sz=float(f["sz"]); px=float(f["px"])
        cash += (-sz*px if f["side"]=="B" else sz*px)
        pos[f["coin"]] += (sz if f["side"]=="B" else -sz)
        fees+=float(f.get("fee","0") or 0); notion+=sz*px
        ntk+=bool(f.get("crossed")); nmk+=not bool(f.get("crossed"))
    resid={k:v for k,v in pos.items() if abs(v)>1e-6}
    mv=0.0; unk=0.0
    for k,v in resid.items():
        m=M.get(k)
        if m is None: unk+=abs(v)
        else: mv+=v*m
    rows.append(dict(addr=a,n=len(of),notional=notion,realized=cash-fees,
                     mark=mv,total=cash-fees+mv,resid_sh=sum(abs(v) for v in resid.values()),
                     unk=unk,mkr=nmk/(nmk+ntk)))
rows.sort(key=lambda r:-r["notional"])
print(f"{'address':>44} {'fills':>6} {'notional':>10} {'mkr%':>5} {'cashPnL':>10} {'markResid':>10} {'TOTAL':>10} {'bps':>7}")
for r in rows:
    print(f"{r['addr']:>44} {r['n']:>6} {r['notional']:>10,.0f} {r['mkr']*100:>4.0f}% "
          f"{r['realized']:>10,.2f} {r['mark']:>10,.2f} {r['total']:>10,.2f} "
          f"{r['total']/r['notional']*1e4:>6.1f}")

closed=[r for r in rows if r["resid_sh"]<300]
print(f"\n--- MAKERS WITH ESSENTIALLY CLOSED BOOKS (realized, not opinion): n={len(closed)} ---")
tn=sum(r["notional"] for r in closed); tp=sum(r["total"] for r in closed)
tf=sum(r["n"] for r in closed)
print(f"fills {tf:,}   notional ${tn:,.0f}   PnL ${tp:,.2f}  = {tp/tn*1e4:+.1f} bps of notional")
print(f"profitable: {sum(1 for r in closed if r['total']>0)}/{len(closed)}")
import statistics as st
b=[r["total"]/r["notional"]*1e4 for r in closed]
print(f"per-maker bps: median {st.median(b):+.1f}  mean {st.mean(b):+.1f}  range {min(b):+.1f}..{max(b):+.1f}")
# t-stat on the per-maker bps
sd=st.stdev(b); print(f"t = {st.mean(b)/(sd/len(b)**0.5):+.2f} (n={len(b)} makers)")
