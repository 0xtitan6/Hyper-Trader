import requests, time, json, os
U="https://api.hyperliquid.xyz/info"
D=os.path.dirname(os.path.abspath(__file__))+"/data"
def post(b,tries=6):
    for i in range(tries):
        try:
            r=requests.post(U,json=b,timeout=40)
            if r.status_code==429: time.sleep(5*(i+1)); continue
            r.raise_for_status(); return r.json()
        except Exception as e:
            print("  retry",i,repr(e)[:90]); time.sleep(2*(i+1))
    return None
now=int(time.time()*1000)
uni=json.load(open(D+"/universe.json"))
coins=[u[0] for u in uni][:40]
print("coins:",coins)
DAY=86400*1000
for name in coins:
    fp=f"{D}/{name}_1h_long.json"
    if os.path.exists(fp): print("have",name); continue
    merged={}
    # two chunks of 180d each -> 360d, each < 5000 candle cap
    for a,b in [(360,180),(180,0)]:
        c=post({"type":"candleSnapshot","req":{"coin":name,"interval":"1h","startTime":now-a*DAY,"endTime":now-b*DAY}})
        time.sleep(0.4)
        if not c: print("  chunk fail",name,a); continue
        for k in c: merged[int(k['t'])]=[int(k['t']),float(k['o']),float(k['h']),float(k['l']),float(k['c']),float(k['v']),k['n']]
    rows=[merged[t] for t in sorted(merged)]
    json.dump(rows,open(fp,"w"))
    print(name,len(rows),"bars",time.strftime("%Y-%m-%d",time.gmtime(rows[0][0]/1000)),"->",time.strftime("%Y-%m-%d",time.gmtime(rows[-1][0]/1000)))
