"""Pull full public fill history for the addresses that MAKE this book, and
compute their outcome-market PnL from cash flows + terminal leg values.

They are running the strategy we are asking about, with more size and better
latency. If they lose, we lose."""
import json, time, urllib.request, sys, collections
INFO="https://api.hyperliquid.xyz/info"
def post(body, retries=6):
    req=urllib.request.Request(INFO, data=json.dumps(body).encode(),
                               headers={"Content-Type":"application/json"})
    for a in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                out=json.loads(r.read().decode())
            time.sleep(0.35); return out
        except Exception as e:
            if a==retries-1:
                print("FAIL",e,file=sys.stderr); return None
            time.sleep(3.0*(a+1))

T=[json.loads(l) for l in open("research/pairq-2026-09-21/trades.jsonl")]
vol=collections.Counter(); cnt=collections.Counter()
for t in T:
    mk = t["users"][1] if t["side"]=="B" else t["users"][0]
    vol[mk]+=float(t["sz"])*float(t["px"]); cnt[mk]+=1
tops=[a for a,_ in vol.most_common(12)]
OURS="0xe503186067b1b0fb973c063054b14c4625434a1a"
tops=[a for a in tops if a.lower()!=OURS][:10]
print("top makers by maker-volume (6h tape):",file=sys.stderr)
for a in tops: print(f"  {a} ${vol[a]:,.0f} / {cnt[a]} fills",file=sys.stderr)

now=int(time.time()*1000)
START=now-30*24*3600*1000
allf={}
for a in tops:
    fills=[]; st=START
    for page in range(12):
        r=post({"type":"userFillsByTime","user":a,"startTime":st,"endTime":now})
        if not isinstance(r,list) or not r: break
        fills+=r
        if len(r)<2000: break
        nt=max(f["time"] for f in r)
        if nt<=st: break
        st=nt+1
    allf[a]=fills
    print(f"{a}: {len(fills)} fills 30d",file=sys.stderr)
json.dump(allf,open("research/pairq-2026-09-21/maker_fills.json","w"))
print("saved")
