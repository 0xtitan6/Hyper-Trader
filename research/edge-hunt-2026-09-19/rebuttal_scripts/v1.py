import json,os,math,glob,datetime as dt
import numpy as np
D="data"
rows=json.load(open(f"{D}/XMR_1h_long.json"))
print("bars",len(rows), dt.datetime.fromtimestamp(rows[0][0]/1000,dt.UTC), dt.datetime.fromtimestamp(rows[-1][0]/1000,dt.UTC))
t=np.array([r[0] for r in rows]); O=np.array([r[1] for r in rows]); C=np.array([r[4] for r in rows]); V=np.array([r[5] for r in rows])
# contiguity
gaps=np.where(np.diff(t)!=3600000)[0]
print("gaps:",len(gaps))
h=np.array([dt.datetime.fromtimestamp(x/1000,dt.UTC).hour for x in t])
day=np.array([dt.datetime.fromtimestamp(x/1000,dt.UTC).strftime("%Y-%m-%d") for x in t])
mon=np.array([d[:7] for d in day])
R=(C-O)/O*1e4
def tt(x):
    x=np.asarray(x,float);n=len(x);m=x.mean();s=x.std(ddof=1);return n,m,s,m/(s/math.sqrt(n))
x=R[h==20]
n,m,s,tv=tt(x)
print(f"XMR hr20 open->close: n={n} mean={m:+.3f}bp sd={s:.1f} t={tv:+.3f}")
print("median",np.median(x),"hit",np.mean(x>0))
# price level over window
for mm in sorted(set(mon)):
    idx=mon==mm
    print(mm, f"px {O[idx][0]:8.2f}->{C[idx][-1]:8.2f}", f"hr20 mean {np.mean(R[(h==20)&(mon==mm)]):+7.2f} n={np.sum((h==20)&(mon==mm))}")
# top days contribution
o=np.sort(x)[::-1]
print("top5 sum share", o[:5].sum()/x.sum(), "top10", o[:10].sum()/x.sum())
print("drop top5 mean", np.mean(o[5:]), "t", tt(o[5:])[3])
print("drop top10 mean", np.mean(o[10:]), "t", tt(o[10:])[3])
print("trim10% mean", np.mean(np.sort(x)[21:-21]))
# all 24 hours for XMR
print("\nXMR all hours:")
for hh in range(24):
    xx=R[h==hh]; n_,m_,s_,t_=tt(xx); print(f"  hr{hh:02d} {m_:+7.2f}bp t={t_:+5.2f} n={n_}")
