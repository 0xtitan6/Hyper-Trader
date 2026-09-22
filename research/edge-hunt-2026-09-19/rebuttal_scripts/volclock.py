import json,math,datetime as dt,numpy as np
S={}
for sym,lab in [("BTCUSDT","BTC"),("ETHUSDT","ETH"),("SOLUSDT","SOL")]:
    S[lab]=json.load(open(f"/tmp/{sym}_1h.json"))
S["XMR"]=json.load(open("/tmp/xmr_bybit_1h.json"))
def series(d):
    t=np.array(sorted(int(k) for k in d))
    O=np.array([d[str(x)][0] for x in t]); C=np.array([d[str(x)][3] for x in t])
    h=np.array([dt.datetime.fromtimestamp(x/1000,dt.UTC).hour for x in t])
    return t,(C-O)/O*1e4,h
def prof(t,R,h,a,b):
    A=int(dt.datetime(*a,tzinfo=dt.UTC).timestamp()*1000);B=int(dt.datetime(*b,tzinfo=dt.UTC).timestamp()*1000)
    m=(t>=A)&(t<B)
    return np.array([np.abs(R[m&(h==hh)]).mean() for hh in range(24)])
segs=[("2022",(2022,1,14),(2023,1,1)),("2023",(2023,1,1),(2024,1,1)),("2024",(2024,1,1),(2025,1,1)),
      ("2025",(2025,1,1),(2026,1,1)),("2026",(2026,1,1),(2026,9,20))]
print("VOL CLOCK (mean |open->close| bp) relative to own-segment average, 4-coin equal weight, Bybit 4.7yr")
P={}
for lab,a,b in segs:
    acc=[]
    for c in S:
        t,R,h=series(S[c]); p=prof(t,R,h,a,b); acc.append(p/p.mean())
    P[lab]=np.mean(np.vstack(acc),axis=0)
hdr="hr  "+"  ".join(f"{l:>6}" for l,_,_ in segs); print(hdr)
for hh in range(24):
    print(f"{hh:02d}  "+"  ".join(f"{P[l][hh]:6.3f}" for l,_,_ in segs))
print("\ncross-year correlation of the 24-hour vol profile:")
ks=[l for l,_,_ in segs]
for i in range(len(ks)):
    for j in range(i+1,len(ks)):
        print(f"  corr({ks[i]},{ks[j]}) = {np.corrcoef(P[ks[i]],P[ks[j]])[0,1]:+.3f}")
print("\nper-year loud/quiet: argmax hour, max, argmin hour, min, ratio")
for l in ks:
    p=P[l]; print(f"  {l}: loud hr{int(np.argmax(p)):02d}={p.max():.2f}  quiet hr{int(np.argmin(p)):02d}={p.min():.2f}  ratio={p.max()/p.min():.2f}")
# OOS test: rank hours on 2022-2024, evaluate on 2025-2026
tr=np.mean(np.vstack([P["2022"],P["2023"],P["2024"]]),axis=0)
te=np.mean(np.vstack([P["2025"],P["2026"]]),axis=0)
top6=np.argsort(tr)[-6:]; bot6=np.argsort(tr)[:6]
print(f"\nOOS: hours ranked on 2022-2024, measured 2025-2026:")
print(f"  train top6 {sorted(top6.tolist())} -> test rel vol {te[top6].mean():.3f}")
print(f"  train bot6 {sorted(bot6.tolist())} -> test rel vol {te[bot6].mean():.3f}   ratio={te[top6].mean()/te[bot6].mean():.2f}x")
print(f"  corr(train profile, test profile) = {np.corrcoef(tr,te)[0,1]:+.3f}")
