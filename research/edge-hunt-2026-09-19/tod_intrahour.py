"""Mechanism check: within hour 20:00-21:00 UTC, where does the XMR move happen?
A discrete jump in the first 15m smells like a scheduled/automated flow (tradeable but
front-runnable) or a data artifact. A smooth hour smells like session flow.
Uses 15m candles (5000-bar archive = ~52 days) -> independent-ish recent subsample."""
import requests,time,json,math,datetime as dt
import numpy as np
U="https://api.hyperliquid.xyz/info"
def post(b):
    for i in range(5):
        r=requests.post(U,json=b,timeout=40)
        if r.status_code==429: time.sleep(5*(i+1)); continue
        r.raise_for_status(); return r.json()
now=int(time.time()*1000)
for coin in ["XMR","ZEC"]:
    c=post({"type":"candleSnapshot","req":{"coin":coin,"interval":"15m","startTime":now-70*86400*1000,"endTime":now}})
    time.sleep(0.4)
    rows=[(int(k['t']),float(k['o']),float(k['c']),float(k['v'])) for k in c]
    print(f"\n=== {coin} 15m: {len(rows)} bars "
          f"{dt.datetime.fromtimestamp(rows[0][0]/1000,dt.UTC)} -> {dt.datetime.fromtimestamp(rows[-1][0]/1000,dt.UTC)} ===")
    H=np.array([dt.datetime.fromtimestamp(r[0]/1000,dt.UTC).hour for r in rows])
    Mi=np.array([dt.datetime.fromtimestamp(r[0]/1000,dt.UTC).minute for r in rows])
    R=np.array([(r[2]-r[1])/r[1]*1e4 for r in rows])
    for hr in (20,7):
        print(f" hour {hr:02d} broken into 15m slices (last ~52 days):")
        tot=0
        for mi in (0,15,30,45):
            y=R[(H==hr)&(Mi==mi)]
            n=len(y); m=y.mean(); t=m/(y.std(ddof=1)/math.sqrt(n)); tot+=m
            print(f"   {hr:02d}:{mi:02d} n={n:>3} {m:+7.2f}bp t={t:+5.2f}")
        print(f"   sum of slices = {tot:+.2f}bp  (1h version on this window)")
        # the full hour on this shorter window, for comparison
    # recent-window 1h check
    c1=post({"type":"candleSnapshot","req":{"coin":coin,"interval":"1h","startTime":now-52*86400*1000,"endTime":now}})
    time.sleep(0.4)
    r1=[(int(k['t']),float(k['o']),float(k['c'])) for k in c1]
    H1=np.array([dt.datetime.fromtimestamp(r[0]/1000,dt.UTC).hour for r in r1])
    R1=np.array([(r[2]-r[1])/r[1]*1e4 for r in r1])
    for hr in (20,7):
        y=R1[H1==hr]; n=len(y); m=y.mean(); t=m/(y.std(ddof=1)/math.sqrt(n))
        print(f" LAST 52 DAYS ONLY: {coin} hr{hr:02d} n={n} {m:+.2f}bp t={t:+.2f} net(9.8)={m-9.8:+.2f}")
