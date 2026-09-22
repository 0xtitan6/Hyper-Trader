import json,math,datetime as dt,numpy as np
d=json.load(open("/tmp/xmr_bybit_1h.json"))
t=np.array(sorted(int(k) for k in d))
O=np.array([d[str(x)][0] for x in t]); C=np.array([d[str(x)][3] for x in t])
h=np.array([dt.datetime.fromtimestamp(x/1000,dt.UTC).hour for x in t])
mon=np.array([dt.datetime.fromtimestamp(x/1000,dt.UTC).strftime("%Y-%m") for x in t])
R=(C-O)/O*1e4
months=sorted(set(mon)); COST=9.84
def ms(x):
    x=np.asarray(x,float);n=len(x);m=x.mean();s=x.std(ddof=1);return n,m,(m/(s/math.sqrt(n)) if n>1 else 0)
for MINTRAIN in (12,24):
    print(f"\n### Walk-forward: pick best XMR hour by |t| on ALL prior months (>= {MINTRAIN} months train), trade next month")
    tr=[]
    for i in range(MINTRAIN,len(months)):
        trm=set(months[:i]); tem=months[i]
        mtr=np.isin(mon,list(trm)); mte=mon==tem
        best=None
        for hh in range(24):
            n,m,tv=ms(R[mtr&(h==hh)])
            if best is None or abs(tv)>abs(best[2]): best=(hh,m,tv)
        hh,m,tv=best; sgn=1 if m>0 else -1
        oos=sgn*R[mte&(h==hh)]
        tr.append(oos)
        if i>=len(months)-8:
            print(f"  {tem} pick hr{hh:02d} {'long' if sgn>0 else 'short'} trainT={tv:+.2f}  OOS n={len(oos)} gross={oos.mean():+7.2f} net={oos.mean()-COST:+7.2f}")
    allt=np.concatenate(tr); n,m,tv=ms(allt)
    print(f"  TOTAL top-1 walk-forward: n={n} gross={m:+.2f}bp net={m-COST:+.2f}bp t(net)={(m-COST)/(allt.std(ddof=1)/math.sqrt(n)):+.2f}")
# fixed-hour-20 always-long walk-forward from 2022
x=R[h==20]; n,m,tv=ms(x); print(f"\nXMR hr20 long over ENTIRE 4.7yr Bybit history: n={n} gross={m:+.2f}bp t={tv:+.2f} net={m-COST:+.2f}bp")
cum=np.cumsum(x-COST)
yr=np.array([dt.datetime.fromtimestamp(z/1000,dt.UTC).strftime("%Y-%m") for z in t[h==20]])
print("cumulative net bp of hr20 long, end of each half-year:")
for k in ["2022-06","2022-12","2023-06","2023-12","2024-06","2024-12","2025-06","2025-12","2026-09"]:
    idx=np.where(yr<=k)[0]
    if len(idx): print(f"  thru {k}: {cum[idx[-1]]:+9.0f} bp")
