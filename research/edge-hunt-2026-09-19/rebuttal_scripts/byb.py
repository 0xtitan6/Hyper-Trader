import requests,time,json,datetime as dt
out={}
end=int(time.time()*1000)
cur=end
for i in range(200):
    u=f"https://api.bybit.com/v5/market/kline?category=linear&symbol=XMRUSDT&interval=60&limit=1000&end={cur}"
    r=requests.get(u,timeout=40); d=r.json()
    L=d.get("result",{}).get("list",[])
    if not L: print("empty stop",d.get("retMsg")); break
    for k in L: out[int(k[0])]=[float(k[1]),float(k[2]),float(k[3]),float(k[4]),float(k[5])]
    mn=min(int(k[0]) for k in L)
    print(i,len(out),dt.datetime.fromtimestamp(mn/1000,dt.UTC),flush=True)
    if mn>=cur: break
    cur=mn-1
    time.sleep(0.35)
json.dump({str(k):v for k,v in sorted(out.items())},open("/tmp/xmr_bybit_1h.json","w"))
print("TOTAL",len(out))
