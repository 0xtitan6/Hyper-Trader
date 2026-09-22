"""Bybit XMRUSDT 1m bars for 19:45-21:15 UTC each day of the HL mining window,
to test execution-timing decay inside hour 20."""
import requests,time,json,datetime
S=requests.Session()
def kl(sym,start,end,iv="1"):
    for i in range(6):
        try:
            r=S.get("https://api.bybit.com/v5/market/kline",
                params={"category":"linear","symbol":sym,"interval":iv,"start":start,"end":end,"limit":1000},timeout=25)
            j=r.json()
            if j.get("retCode")==0: return j["result"]["list"]
            time.sleep(2*(i+1))
        except Exception as e: time.sleep(2*(i+1))
    return None
d0=datetime.datetime(2026,2,22,tzinfo=datetime.timezone.utc)
out={}
day=d0
nd=0
while day < datetime.datetime(2026,9,19,tzinfo=datetime.timezone.utc):
    s=int((day+datetime.timedelta(hours=19,minutes=45)).timestamp()*1000)
    e=int((day+datetime.timedelta(hours=21,minutes=15)).timestamp()*1000)
    L=kl("XMRUSDT",s,e)
    if L:
        out[day.strftime("%Y-%m-%d")]=sorted([[int(x[0])]+[float(v) for v in x[1:6]] for x in L],key=lambda z:z[0])
        nd+=1
    day+=datetime.timedelta(days=1)
    time.sleep(0.25)
    if nd%40==0 and nd: print("days",nd,flush=True)
json.dump(out,open("/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/skeptic_exec/xmr_1m_hr20.json","w"))
lens=[len(v) for v in out.values()]
print("days",len(out),"bars/day min/med/max",min(lens),sorted(lens)[len(lens)//2],max(lens))
