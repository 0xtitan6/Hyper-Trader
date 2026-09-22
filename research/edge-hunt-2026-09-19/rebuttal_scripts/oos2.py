import json,math,datetime as dt,numpy as np
d=json.load(open("/tmp/xmr_bybit_1h.json"))
t=np.array(sorted(int(k) for k in d))
O=np.array([d[str(x)][0] for x in t]); C=np.array([d[str(x)][3] for x in t])
h=np.array([dt.datetime.fromtimestamp(x/1000,dt.UTC).hour for x in t])
day=np.array([dt.datetime.fromtimestamp(x/1000,dt.UTC).strftime("%Y-%m-%d") for x in t])
R=(C-O)/O*1e4
def ms(x):
    x=np.asarray(x,float);n=len(x);m=x.mean();s=x.std(ddof=1);return n,m,m/(s/math.sqrt(n))
def win(a,b): 
    A=int(dt.datetime(*a,tzinfo=dt.UTC).timestamp()*1000); B=int(dt.datetime(*b,tzinfo=dt.UTC).timestamp()*1000)
    return (t>=A)&(t<B)
def prof(mask):
    return np.array([R[mask&(h==hh)].mean() for hh in range(24)])
segs={
 "2022":win((2022,1,14),(2023,1,1)),"2023":win((2023,1,1),(2024,1,1)),
 "2024":win((2024,1,1),(2025,1,1)),"2025":win((2025,1,1),(2026,1,1)),
 "2026H1(pre-HL)":win((2026,1,1),(2026,2,22)),"HLwindow":win((2026,2,22),(2026,9,20)),
}
P={k:prof(v) for k,v in segs.items()}
print("XMR hour-of-day DRIFT PROFILE persistence (Bybit, 4.7yr) -- corr between segments:")
ks=list(P)
for i in range(len(ks)):
    for j in range(i+1,len(ks)):
        print(f"  corr({ks[i]:>14},{ks[j]:>14}) = {np.corrcoef(P[ks[i]],P[ks[j]])[0,1]:+.3f}")
print("\nPre-2025 pooled (2022-01..2024-12) vs 2025-on pooled:")
pre=win((2022,1,14),(2025,1,1)); post=win((2025,1,1),(2026,9,20))
for lab,mk in [("pre2025",pre),("2025on",post)]:
    n,m,tv=ms(R[mk&(h==20)]); print(f"  {lab} hr20: n={n} {m:+.2f}bp t={tv:+.2f} net={m-9.84:+.2f}")
print(f"  corr of 24h profile pre2025 vs 2025on = {np.corrcoef(prof(pre),prof(post))[0,1]:+.3f}")
# recent OOS only: 2025-01-01 -> 2026-02-22 (fully outside HL mining window)
rec=win((2025,1,1),(2026,2,22))
print("\nRECENT-OOS 2025-01-01 -> 2026-02-22 (outside HL window), all 24 hours:")
res=[]
for hh in range(24):
    n,m,tv=ms(R[rec&(h==hh)]); res.append((hh,n,m,tv))
for hh,n,m,tv in res: print(f"  hr{hh:02d} n={n} {m:+7.2f}bp t={tv:+6.2f}"+("  <<<hr20" if hh==20 else ""))
print("  max|t|:",max(res,key=lambda r:abs(r[3])))
# de-trend hr20: excess over same-day mean of other 23h, per segment
print("\nDE-TRENDED hr20 (excess over same-day mean of other 23 hours):")
for lab,mk in [("2022-2024",pre),("2025-on",post),("HLwindow",segs["HLwindow"]),("OOS<2026-02-22",win((2022,1,14),(2026,2,22)))]:
    ex=[]
    for D in sorted(set(day[mk])):
        m2=mk&(day==D)
        if m2.sum()!=24: continue
        v=R[m2]; hh=h[m2]
        ex.append(v[hh==20][0]-v[hh!=20].mean())
    n,m,tv=ms(ex); print(f"  {lab:16} n={n:5d} {m:+7.2f}bp t={tv:+6.2f}")
# daily drift of XMR per segment (regime check)
print("\nXMR mean daily drift (sum of 24 hourly bp) per segment:")
for k,v in segs.items():
    print(f"  {k:16} {prof(v).sum():+8.1f} bp/day   px {O[v][0]:.1f} -> {C[v][-1]:.1f}")
