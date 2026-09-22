import requests, time, json, os, sys
U="https://api.hyperliquid.xyz/info"
OUT=os.path.dirname(os.path.abspath(__file__))+"/data"
os.makedirs(OUT,exist_ok=True)
COINS=["BTC","ETH","HYPE","ZEC","SOL","NEAR","XRP","LIT","PUMP","UNI"]
DAYS=60
now=int(time.time()//3600*3600*1000)   # top of current hour
start=now-DAYS*86400*1000

def post(body,tries=6):
    for i in range(tries):
        try:
            r=requests.post(U,json=body,timeout=30)
            if r.status_code==429:
                time.sleep(3*(i+1)); continue
            r.raise_for_status(); return r.json()
        except Exception as e:
            print("  retry",i,e); time.sleep(2*(i+1))
    raise RuntimeError("fail "+json.dumps(body)[:120])

for c in COINS:
    fp=f"{OUT}/{c}_1m.json"
    if not os.path.exists(fp):
        allc={}; end=now
        while end>start:
            r=post({"type":"candleSnapshot","req":{"coin":c,"interval":"1m","startTime":start,"endTime":end}})
            time.sleep(0.35)
            if not r: break
            for k in r: allc[k['t']]=k
            new_end=min(x['t'] for x in r)-1
            print(f"{c} got {len(r)} total {len(allc)} end->{new_end}")
            if new_end>=end: break
            end=new_end
        rows=[[k['t'],float(k['o']),float(k['h']),float(k['l']),float(k['c']),float(k['v']),k['n']] for k in sorted(allc.values(),key=lambda x:x['t'])]
        json.dump(rows,open(fp,"w"))
        print(c,"candles",len(rows))
    fp2=f"{OUT}/{c}_funding.json"
    if not os.path.exists(fp2):
        allf={}; st=start
        while True:
            r=post({"type":"fundingHistory","coin":c,"startTime":st,"endTime":now})
            time.sleep(0.35)
            if not r: break
            for k in r: allf[k['time']]=float(k['fundingRate'])
            mx=max(x['time'] for x in r)
            if mx<=st or len(r)<500: break
            st=mx+1
        rows=sorted(allf.items())
        json.dump(rows,open(fp2,"w"))
        print(c,"funding",len(rows))
print("DONE")
