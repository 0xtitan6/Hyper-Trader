import json,math,datetime as dt,numpy as np
hl=json.load(open("data/XMR_1h_long.json"))
H={int(r[0]):(r[1],r[4]) for r in hl}
b=json.load(open("/tmp/xmr_bybit_1h.json"))
B={int(k):(v[0],v[3]) for k,v in b.items()}
com=sorted(set(H)&set(B))
rh=np.array([(H[t][1]-H[t][0])/H[t][0]*1e4 for t in com])
rb=np.array([(B[t][1]-B[t][0])/B[t][0]*1e4 for t in com])
print(f"overlap bars {len(com)}  corr(HL bar return, Bybit bar return) = {np.corrcoef(rh,rb)[0,1]:+.4f}")
h=np.array([dt.datetime.fromtimestamp(t/1000,dt.UTC).hour for t in com])
print(f"hr20 only: n={np.sum(h==20)} corr={np.corrcoef(rh[h==20],rb[h==20])[0,1]:+.4f}  HL mean {rh[h==20].mean():+.2f}bp  Bybit mean {rb[h==20].mean():+.2f}bp")
