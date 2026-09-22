import json,os,math,time
import numpy as np
D="/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
coins=sorted(set(f.split("_1h_long")[0] for f in os.listdir(D) if f.endswith("_1h_long.json")))
info={}
for c in coins:
    r=json.load(open(f"{D}/{c}_1h_long.json"))
    info[c]=len(r)
for c,n in sorted(info.items(),key=lambda x:-x[1]): print(c,n)
