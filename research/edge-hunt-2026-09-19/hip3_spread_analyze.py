import json,math,statistics as st
from collections import defaultdict
P="/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data/hip3_l2.jsonl"
snaps=defaultdict(list); errs=defaultdict(int)
for line in open(P):
    r=json.loads(line)
    if r.get("err"): errs[r["c"]]+=1; continue
    if not r["b"] or not r["a"]: errs[r["c"]]+=1; continue
    snaps[r["c"]].append(r)

def depth_cost(levels,mid,notional,side):
    # VWAP cost in bps vs mid to take `notional` USD
    rem=notional; cost=0.0; filled=0.0
    for px,sz,n in levels:
        px=float(px); sz=float(sz); avail=px*sz
        take=min(rem,avail)
        cost+=take; filled+=take/px
        rem-=take
        if rem<=1e-9: break
    if rem>1e-6: return None  # book too thin
    vwap=cost/filled
    return (vwap-mid)/mid*1e4 if side=="a" else (mid-vwap)/mid*1e4

print("%-13s %5s %7s %7s %7s %8s %8s %9s %9s %9s %9s"%(
 "coin","n","spr_med","spr_mean","spr_p90","bidUSD0","askUSD0","rt$100","rt$1k","rt$10k","bookUSD"))
rows={}
for c,ss in sorted(snaps.items()):
    sp=[]; b0=[]; a0=[]; rt={100:[],1000:[],10000:[]}; tot=[]
    mids=[]
    for r in ss:
        bb=float(r["b"][0][0]); ba=float(r["a"][0][0]); mid=(bb+ba)/2
        sp.append((ba-bb)/mid*1e4); mids.append((r["t"],mid))
        b0.append(bb*float(r["b"][0][1])); a0.append(ba*float(r["a"][0][1]))
        tot.append(sum(float(p)*float(s) for p,s,_ in r["b"])+sum(float(p)*float(s) for p,s,_ in r["a"]))
        for N in rt:
            ca=depth_cost(r["a"],mid,N,"a"); cb=depth_cost(r["b"],mid,N,"b")
            rt[N].append(None if (ca is None or cb is None) else ca+cb)
    def med(x):
        x=[v for v in x if v is not None]
        return st.median(x) if x else float("nan")
    def frac_ok(x): 
        return sum(1 for v in x if v is not None)/len(x)
    print("%-13s %5d %7.2f %7.2f %7.2f %8.0f %8.0f %9s %9s %9s %9.0f"%(
      c,len(ss),med(sp),sum(sp)/len(sp),sorted(sp)[int(0.9*len(sp))-1],med(b0),med(a0),
      "%.1f/%.0f%%"%(med(rt[100]),100*frac_ok(rt[100])),
      "%.1f/%.0f%%"%(med(rt[1000]),100*frac_ok(rt[1000])),
      "%.1f/%.0f%%"%(med(rt[10000]),100*frac_ok(rt[10000])),
      med(tot)))
    rows[c]={"sp":sp,"mids":mids,"rt":{k:med(v) for k,v in rt.items()},
             "rtok":{k:frac_ok(v) for k,v in rt.items()}}
json.dump({"errs":dict(errs)},open("/dev/stdout","w")); print()

# --- mid jump / staleness stats
print("\n=== mid dynamics (sample interval ~8.3s) ===")
print("%-13s %6s %7s %8s %8s %8s %8s %8s"%("coin","n","frz%","|d|med","|d|p95","maxjump","ac1","jump>cost%"))
for c,d in sorted(rows.items()):
    m=[v for _,v in d["mids"]]
    if len(m)<20: continue
    ret=[(m[i+1]-m[i])/m[i]*1e4 for i in range(len(m)-1)]
    absr=sorted(abs(x) for x in ret)
    frz=sum(1 for x in ret if abs(x)<1e-9)/len(ret)*100
    spmed=st.median(d["sp"])
    cost=9.0+spmed
    jc=sum(1 for x in absr if x>cost)/len(absr)*100
    # lag-1 autocorr of returns
    mu=sum(ret)/len(ret)
    num=sum((ret[i]-mu)*(ret[i+1]-mu) for i in range(len(ret)-1))
    den=sum((x-mu)**2 for x in ret)
    ac1=num/den if den>0 else float("nan")
    print("%-13s %6d %7.1f %8.2f %8.2f %8.2f %8.3f %8.1f"%(
      c,len(ret),frz,st.median(absr),absr[int(0.95*len(absr))-1],absr[-1],ac1,jc))
