import requests,time,json,os
U="https://api.hyperliquid.xyz/info"
D="/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
COINS=["BTC","ETH","SOL","HYPE","DOGE","XRP","SUI","LTC","BNB","AVAX","LINK","ADA","NEAR","ARB","WLD","TAO","ENA","UNI","AAVE","INJ"]
def post(b,tries=6):
    for i in range(tries):
        try:
            r=requests.post(U,json=b,timeout=30)
            if r.status_code==429: time.sleep(4*(i+1)); continue
            r.raise_for_status(); return r.json()
        except Exception as e:
            print("  retry",i,repr(e)[:80]); time.sleep(2*(i+1))
    return None
now=int(time.time()*1000)
CH=4900*60000
for c in COINS:
    fp=f"{D}/{c}_1m_long.json"
    if os.path.exists(fp): print("skip",c); continue
    rows={}
    end=now
    for k in range(9):   # ~44k minutes ~ 30 days
        r=post({"type":"candleSnapshot","req":{"coin":c,"interval":"1m","startTime":end-CH,"endTime":end}})
        time.sleep(0.4)
        if not r: break
        for k2 in r: rows[k2['t']]=[k2['t'],float(k2['o']),float(k2['h']),float(k2['l']),float(k2['c']),float(k2['v']),k2['n']]
        end=min(rows)-60000 if rows else end-CH
    out=sorted(rows.values())
    json.dump(out,open(fp,"w"))
    print(c,len(out),out[0][0],out[-1][0],flush=True)
