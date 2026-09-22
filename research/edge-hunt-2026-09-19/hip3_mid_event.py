import json,math,statistics as st
from collections import defaultdict
P="/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data/hip3_l2.jsonl"
S=defaultdict(list)
for line in open(P):
    r=json.loads(line)
    if r.get("err") or not r.get("b") or not r.get("a"): continue
    bb=float(r["b"][0][0]); ba=float(r["a"][0][0])
    S[r["c"]].append((r["t"],(bb+ba)/2,(ba-bb)/((bb+ba)/2)*1e4))
def tstat(x):
    n=len(x)
    if n<3: return float("nan"),float("nan")
    m=sum(x)/n; sd=st.pstdev(x)*math.sqrt(n/(n-1))
    return m,(m/(sd/math.sqrt(n)) if sd>0 else float("nan"))
print("=== L2 mid event study: any NONZERO mid move -> signed fwd mid return (bps) ===")
print("interval ~8.3s. h=1,3,10 => ~8s, 25s, 83s ahead. cost = 9bp + median spread.")
print("%-13s %6s %6s %8s %7s %8s %7s %8s %7s %8s"%("coin","N","nev","f+1","t","f+3","t","f+10","t","cost"))
for c,v in sorted(S.items()):
    mids=[m for _,m,_ in v]; spr=st.median([s for _,_,s in v])
    if len(mids)<30: continue
    idx=[i for i in range(1,len(mids)-11) if mids[i]!=mids[i-1]]
    if len(idx)<8:
        print("%-13s %6d %6d  (no events)"%(c,len(mids),len(idx))); continue
    def fwd(h):
        return [ (1 if mids[i]>mids[i-1] else -1)*(mids[i+h]-mids[i])/mids[i]*1e4 for i in idx]
    a=[tstat(fwd(h)) for h in (1,3,10)]
    print("%-13s %6d %6d %8.2f %7.2f %8.2f %7.2f %8.2f %7.2f %8.2f"%(
      c,len(mids),len(idx),a[0][0],a[0][1],a[1][0],a[1][1],a[2][0],a[2][1],9.0+spr))
