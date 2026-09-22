import requests, json, time, sys, os

COINS = ["BTC","ETH","SOL","HYPE","DOGE","XRP","SUI","LTC"]
OUT = "/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data/l2_snaps.jsonl"
DUR = float(sys.argv[1]) if len(sys.argv)>1 else 2400.0  # seconds
URL = "https://api.hyperliquid.xyz/info"
S = requests.Session()

t_end = time.time() + DUR
n=0; err=0
f = open(OUT, "a", buffering=1)
while time.time() < t_end:
    for c in COINS:
        try:
            t0=time.time()
            r = S.post(URL, json={"type":"l2Book","coin":c}, timeout=8)
            d = r.json()
            lv = d["levels"]
            # keep top 20 levels px/sz each side + exchange time + local recv time
            rec = {"c":c,"t":d["time"],"lt":int(t0*1000),
                   "b":[[l["px"],l["sz"],l["n"]] for l in lv[0][:20]],
                   "a":[[l["px"],l["sz"],l["n"]] for l in lv[1][:20]]}
            f.write(json.dumps(rec)+"\n")
            n+=1
        except Exception as e:
            err+=1
            if err<10: print("ERR",c,repr(e)[:120], flush=True)
        time.sleep(0.33)
print("done snaps=%d err=%d"%(n,err), flush=True)
