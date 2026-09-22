import json,math,datetime as dt,numpy as np
d=json.load(open("/tmp/xmr_bybit_1h.json"))
t=np.array(sorted(int(k) for k in d))
O=np.array([d[str(x)][0] for x in t]); C=np.array([d[str(x)][3] for x in t])
gaps=np.sum(np.diff(t)!=3600000); print("bars",len(t),"gaps",gaps,
   dt.datetime.fromtimestamp(t[0]/1000,dt.UTC),"->",dt.datetime.fromtimestamp(t[-1]/1000,dt.UTC))
h=np.array([dt.datetime.fromtimestamp(x/1000,dt.UTC).hour for x in t])
R=(C-O)/O*1e4
CUT=int(dt.datetime(2026,2,22,19,tzinfo=dt.UTC).timestamp()*1000)
def tt(x):
    x=np.asarray(x,float);n=len(x);m=x.mean();s=x.std(ddof=1);return n,m,s,(m/(s/math.sqrt(n)) if n>1 else 0)
def rep(mask,label):
    print(f"\n=== {label}  ({np.sum(mask)} bars = {np.sum(mask)/24:.0f} days) ===")
    res=[]
    for hh in range(24):
        x=R[mask&(h==hh)]; n,m,s,tv=tt(x); res.append((hh,n,m,tv))
    for hh,n,m,tv in res:
        star="  <<<" if hh in (20,7) else ""
        print(f"  hr{hh:02d} n={n:5d} {m:+8.2f}bp t={tv:+6.2f}{star}")
    mx=max(res,key=lambda r:abs(r[3])); print("  max|t| hour",mx)
# validation window (same as HL mining window)
rep((t>=CUT),"BYBIT in-sample window 2026-02-22 -> now (validate vs HL)")
rep((t<CUT),"BYBIT TRUE OOS 2022-01-14 -> 2026-02-22")
# yearly hr20
print("\nBybit XMR hr20 by calendar year:")
yr=np.array([dt.datetime.fromtimestamp(x/1000,dt.UTC).year for x in t])
for y in sorted(set(yr)):
    x=R[(h==20)&(yr==y)]; n,m,s,tv=tt(x); print(f"  {y}: n={n:4d} {m:+8.2f}bp t={tv:+6.2f}  net(9.84)={m-9.84:+7.2f}")
print("\nBybit XMR hr07 by calendar year:")
for y in sorted(set(yr)):
    x=R[(h==7)&(yr==y)]; n,m,s,tv=tt(x); print(f"  {y}: n={n:4d} {m:+8.2f}bp t={tv:+6.2f}")
