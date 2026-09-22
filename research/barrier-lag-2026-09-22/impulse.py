"""Impulse response: how much of an underlying move does the barrier quote
incorporate, and after how long?

For each time t:
    x = predicted fair change from the underlying over [t-W, t]  (delta * dU)
    y = actual barrier mid change over [t, t+h]
beta(h) = OLS slope of y on x = the FRACTION of the fair move the book picks up
h seconds LATER. This is a high-n test of the lag itself:
    beta(h) ~ 0 for all h  -> book ignores the underlying (wide-spread no-op)
    beta rises to ~1       -> book lags; the h where it plateaus is the lag
    beta(h) < 0            -> already incorporated before t (book leads)
Also reports the contemporaneous share for reference.
"""
import json, sys, math, time, statistics as st
from collections import defaultdict

TAPE = sys.argv[1]
BAR = {"#12090": ("HYPE", 100.0), "#12120": ("BTC", 95000.0), "#12130": ("BTC", 90000.0)}
EXPIRY = time.mktime(time.strptime("2026-10-01", "%Y-%m-%d"))
W = 30

def N(x): return 0.5*(1+math.erf(x/math.sqrt(2)))
def n_(x): return math.exp(-x*x/2)/math.sqrt(2*math.pi)
def touch(S,K,s,T): return min(1.0, 2*N(-abs(math.log(K/S))/(s*math.sqrt(T)))) if s>0 and T>0 else 0.0
def implied(S,K,T,p):
    p=min(max(p,1e-4),0.999); lo,hi=0.02,8.0
    for _ in range(60):
        m=(lo+hi)/2
        if touch(S,K,m,T)<p: lo=m
        else: hi=m
    return (lo+hi)/2

recs=[json.loads(l) for l in open(TAPE)]
utr,books=defaultdict(list),defaultdict(list)
for r in recs:
    if r["k"]=="utrade": utr[r["coin"]].append((r["lt"],float(r["px"])))
    elif r["k"] in ("rest","book") and r.get("b") and r.get("a"):
        books[r["coin"]].append((r["lt"],float(r["b"][0][0]),float(r["a"][0][0])))
for d in (utr,books):
    for c in d: d[c].sort()
def step(s,t):
    if not s or s[0][0]>t: return None
    lo,hi=0,len(s)-1
    while lo<hi:
        m=(lo+hi+1)//2
        if s[m][0]<=t: lo=m
        else: hi=m-1
    return s[lo]
def ols(x,y):
    n=len(x)
    if n<20: return float("nan"),float("nan"),n
    mx,my=sum(x)/n,sum(y)/n
    sxx=sum((v-mx)**2 for v in x); sxy=sum((x[i]-mx)*(y[i]-my) for i in range(n))
    if sxx==0: return float("nan"),float("nan"),n
    b=sxy/sxx
    resid=[y[i]-(my+b*(x[i]-mx)) for i in range(n)]
    s2=sum(r*r for r in resid)/max(1,n-2)
    return b, math.sqrt(s2/sxx), n

for coin,(und,K) in BAR.items():
    bk,up=books.get(coin,[]),utr.get(und,[])
    if len(bk)<80 or len(up)<80: continue
    T0=(EXPIRY-bk[0][0])/(365*24*3600)
    u0=up[len(up)//2][1]; m0=st.median([(b[1]+b[2])/2 for b in bk])
    sig=implied(u0,K,T0,m0)
    z=abs(math.log(K/u0))/(sig*math.sqrt(T0)); delta=2*n_(z)/(u0*sig*math.sqrt(T0))
    print("\n"+"="*80)
    print(f"### {coin} {und} touch {K:g}  implied vol {sig*100:.1f}%  delta {delta:.3e}/$1")
    t0,t1=max(bk[0][0],up[0][0]),min(bk[-1][0],up[-1][0])
    # contemporaneous
    xs,ys=[],[]
    t=t0+W
    while t<t1:
        ua,ub=step(up,t-W),step(up,t); ba,bb=step(bk,t-W),step(bk,t)
        if ua and ub and ba and bb:
            xs.append(delta*(ub[1]-ua[1])); ys.append((bb[1]+bb[2])/2-(ba[1]+ba[2])/2)
        t+=2
    b,se,n=ols(xs,ys)
    print(f"    contemporaneous share of fair move already in the quote: "
          f"beta={b:+.3f} +/- {se:.3f} (n={n})")
    print(f"    {'h':>5} {'beta(h)':>9} {'se':>7} {'t':>7}   fraction of the fair move picked up h sec LATER")
    for h in (5,10,20,30,60,120,300):
        xs,ys=[],[]
        t=t0+W
        while t<t1-h:
            ua,ub=step(up,t-W),step(up,t); ba,bb=step(bk,t),step(bk,t+h)
            if ua and ub and ba and bb:
                xs.append(delta*(ub[1]-ua[1])); ys.append((bb[1]+bb[2])/2-(ba[1]+ba[2])/2)
            t+=2
        b,se,n=ols(xs,ys)
        tt=b/se if se and not math.isnan(se) and se>0 else float("nan")
        print(f"    {h:>5} {b:>+9.3f} {se:>7.3f} {tt:>7.2f}   n={n}")
