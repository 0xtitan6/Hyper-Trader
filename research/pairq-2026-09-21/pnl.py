"""Outcome-market PnL for each maker, from cash flows.

Settlement and 'Merge Outcome' arrive as fills, so a closed book nets out
without needing external marks. Residual inventory is reported separately and
marked at 0.5 +/- so we can see how much of the answer depends on it.
"""
import json, collections
F=json.load(open("research/pairq-2026-09-21/maker_fills.json"))
rows=[]
for a,fl in F.items():
    of=[f for f in fl if f["coin"].startswith("#")]
    cash=0.0; fees=0.0; pos=collections.Counter(); notion=0.0
    nmk=ntk=0; bydir=collections.Counter(); tmin=1e18; tmax=0
    for f in of:
        sz=float(f["sz"]); px=float(f["px"]); v=sz*px
        sgn = -1 if f["side"]=="B" else 1
        cash += sgn*v
        pos[f["coin"]] += (sz if f["side"]=="B" else -sz)
        fees += float(f.get("fee","0") or 0)
        notion += v; bydir[f.get("dir")]+=1
        if f.get("crossed"): ntk+=1
        else: nmk+=1
        tmin=min(tmin,f["time"]); tmax=max(tmax,f["time"])
    resid = {k:v for k,v in pos.items() if abs(v)>1e-6}
    resid_sh = sum(abs(v) for v in resid.values())
    rows.append(dict(addr=a,n=len(of),cash=cash,fees=fees,pnl=cash-fees,
                     notional=notion,nmk=nmk,ntk=ntk,resid_legs=len(resid),
                     resid_sh=resid_sh,days=(tmax-tmin)/86400e3,bydir=dict(bydir)))

rows.sort(key=lambda r:-r["notional"])
print(f"{'address':>44} {'fills':>6} {'notional':>11} {'mkr%':>5} {'PnL':>10} {'bps':>7} {'residSh':>9} {'days':>5}")
tot=dict(n=0,notional=0.0,pnl=0.0,resid=0.0)
for r in rows:
    bps = r["pnl"]/r["notional"]*1e4 if r["notional"] else 0
    print(f"{r['addr']:>44} {r['n']:>6} {r['notional']:>11,.0f} "
          f"{r['nmk']/(r['nmk']+r['ntk'])*100:>4.0f}% {r['pnl']:>10,.2f} {bps:>6.1f} "
          f"{r['resid_sh']:>9,.0f} {r['days']:>5.1f}")
    tot["n"]+=r["n"]; tot["notional"]+=r["notional"]; tot["pnl"]+=r["pnl"]; tot["resid"]+=r["resid_sh"]
print(f"\nAGGREGATE: {tot['n']:,} outcome fills, ${tot['notional']:,.0f} notional, "
      f"PnL ${tot['pnl']:,.2f} = {tot['pnl']/tot['notional']*1e4:+.1f} bps of notional")
print(f"residual open shares across all: {tot['resid']:,.0f} "
      f"(worst case +/- ${tot['resid']:,.0f} if every one settles at 1 or 0)")
print(f"profitable makers: {sum(1 for r in rows if r['pnl']>0)}/{len(rows)}")
print("\ndirs:", collections.Counter(k for r in rows for k,v in r["bydir"].items() for _ in range(v)).most_common())
json.dump(rows,open("research/pairq-2026-09-21/pnl_rows.json","w"))
