import json,math,statistics as st,sys
P="/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data/hip3_1m.json"
D=json.load(open(P))
BAR=9.0
def tstat(x):
    n=len(x)
    if n<3: return float("nan"),float("nan")
    m=sum(x)/n
    sd=st.pstdev(x)*math.sqrt(n/(n-1)) if n>1 else 0
    return m,(m/(sd/math.sqrt(n)) if sd>0 else float("nan"))
print("=== 1m candle universe (last 7d) ===")
print("%-13s %7s %7s %7s %8s %8s"%("coin","bars","zero%","|r|med","|r|p95","sd_bps"))
series={}
for c,ks in D.items():
    if not ks: print(c,"EMPTY"); continue
    t=[k["t"] for k in ks]; px=[float(k["c"]) for k in ks]; n=[int(k["n"]) for k in ks]
    # contiguity: only use consecutive-minute pairs
    r=[]
    for i in range(len(px)-1):
        if t[i+1]-t[i]==60000:
            r.append(((px[i+1]-px[i])/px[i]*1e4,i))
    rr=[x for x,_ in r]
    ab=sorted(abs(x) for x in rr)
    if not ab: continue
    print("%-13s %7d %7.1f %7.2f %7.2f %8.2f"%(c,len(ks),100*sum(1 for x in rr if abs(x)<1e-9)/len(rr),
      st.median(ab),ab[int(0.95*len(ab))-1],st.pstdev(rr)))
    series[c]=(t,px,n)

print("\n=== EVENT STUDY: after a 1m jump of |r|>=THR bps, signed forward return (bps) ===")
print("(signed by jump direction: positive = CONTINUATION. Bar to beat = 9bp fees + spread)")
for THR in (10,25,50):
    print("\n-- threshold |r1m| >= %d bps --"%THR)
    print("%-13s %6s %9s %9s %9s %9s %9s"%("coin","n","f+1m","t","f+5m","t","f+15m"))
    for c,(t,px,nn) in sorted(series.items()):
        idx=[i for i in range(1,len(px)-15) if t[i]-t[i-1]==60000 and abs((px[i]-px[i-1])/px[i-1]*1e4)>=THR]
        if len(idx)<10: 
            print("%-13s %6d  (too few)"%(c,len(idx))); continue
        def fwd(h):
            out=[]
            for i in idx:
                if t[i+h]-t[i]!=60000*h: continue
                sgn=1 if px[i]>px[i-1] else -1
                out.append(sgn*(px[i+h]-px[i])/px[i]*1e4)
            return out
        f1=fwd(1); f5=fwd(5); f15=fwd(15)
        m1,t1=tstat(f1); m5,t5=tstat(f5); m15,t15=tstat(f15)
        print("%-13s %6d %9.2f %9.2f %9.2f %9.2f %9.2f"%(c,len(f1),m1,t1,m5,t5,m15))
