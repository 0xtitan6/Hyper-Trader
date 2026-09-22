import requests,time,json,datetime as dt
for sym in ["BTCUSDT","ETHUSDT","SOLUSDT"]:
    out={}; cur=int(time.time()*1000)
    for i in range(60):
        u=f"https://api.bybit.com/v5/market/kline?category=linear&symbol={sym}&interval=60&limit=1000&end={cur}"
        try: d=requests.get(u,timeout=40).json()
        except Exception as e: print("err",e); time.sleep(2); continue
        L=d.get("result",{}).get("list",[])
        if not L: break
        for k in L: out[int(k[0])]=[float(k[1]),float(k[2]),float(k[3]),float(k[4]),float(k[5])]
        mn=min(int(k[0]) for k in L)
        if mn<int(dt.datetime(2022,1,14,tzinfo=dt.UTC).timestamp()*1000) or mn>=cur: break
        cur=mn-1; time.sleep(0.35)
    json.dump({str(k):v for k,v in sorted(out.items())},open(f"/tmp/{sym}_1h.json","w"))
    print(sym,len(out),dt.datetime.fromtimestamp(min(out)/1000,dt.UTC),flush=True)
