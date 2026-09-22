import json,requests,time,datetime
U="https://api.hyperliquid.xyz/info"
ACC="0xE503186067b1B0Fb973c063054B14c4625434A1a"
def post(b):
    r=requests.post(U,json=b,timeout=20); r.raise_for_status(); time.sleep(0.35); return r.json()
print("== userFees")
f=post({"type":"userFees","user":ACC})
print(json.dumps({k:v for k,v in f.items() if k in ("dailyUserVlm","feeSchedule","userCrossRate","userAddRate","activeReferralDiscount","userSpotCrossRate","userSpotAddRate","activeStakingDiscount")},indent=1)[:2000])
print("== meta XMR")
m=post({"type":"meta"})
for a in m["universe"]:
    if a["name"] in ("XMR","BTC","ETH"):
        print(a)
print("== 1m retention probe")
now=int(time.time()*1000)
for back in (5,10,30):
    c=post({"type":"candleSnapshot","req":{"coin":"XMR","interval":"1m","startTime":now-back*86400000,"endTime":now-(back-1)*86400000}})
    print(back,"days back ->",len(c), datetime.datetime.utcfromtimestamp(c[0][0]/1000) if c else None)
