import json,math,statistics as st,datetime as dt
P="/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data/hip3_1m.json"
D=json.load(open(P))
def tstat(x):
    n=len(x)
    if n<3: return float("nan"),float("nan")
    m=sum(x)/n; sd=st.pstdev(x)*math.sqrt(n/(n-1))
    return m,(m/(sd/math.sqrt(n)) if sd>0 else float("nan"))
def insess(ms):
    d=dt.datetime.utcfromtimestamp(ms/1000)
    if d.weekday()>=5: return False
    mn=d.hour*60+d.minute
    return 13*60+30 <= mn < 20*60
print("=== in-session (Mon-Fri 13:30-20:00 UTC) vs off-session, 1m bars, 7d ===")
print("%-13s %8s %8s %8s %8s %8s %8s"%("coin","n_in","sd_in","zero_in","n_off","sd_off","zero_off"))
S={}
for c,ks in D.items():
    if not ks: continue
    t=[k["t"] for k in ks]; px=[float(k["c"]) for k in ks]
    ri=[];ro=[]
    for i in range(len(px)-1):
        if t[i+1]-t[i]!=60000: continue
        r=(px[i+1]-px[i])/px[i]*1e4
        (ri if insess(t[i+1]) else ro).append(r)
    if not ri or not ro: continue
    print("%-13s %8d %8.2f %8.1f %8d %8.2f %8.1f"%(c,len(ri),st.pstdev(ri),
      100*sum(1 for x in ri if abs(x)<1e-9)/len(ri),len(ro),st.pstdev(ro),
      100*sum(1 for x in ro if abs(x)<1e-9)/len(ro)))
    S[c]=(t,px)

print("\n=== IN-SESSION event study: |r1m|>=THR -> signed forward returns (bps) ===")
for THR in (10,25):
    print("\n-- THR=%d bps, in-session only --"%THR)
    print("%-13s %6s %8s %7s %8s %7s %8s %7s"%("coin","n","f+1m","t","f+5m","t","f+15m","t"))
    for c,(t,px) in sorted(S.items()):
        idx=[i for i in range(1,len(px)-16) if t[i]-t[i-1]==60000 and insess(t[i])
             and abs((px[i]-px[i-1])/px[i-1]*1e4)>=THR]
        if len(idx)<15:
            print("%-13s %6d (too few)"%(c,len(idx))); continue
        def fwd(h):
            o=[]
            for i in idx:
                if t[i+h]-t[i]!=60000*h: continue
                s=1 if px[i]>px[i-1] else -1
                o.append(s*(px[i+h]-px[i])/px[i]*1e4)
            return o
        r=[fwd(h) for h in (1,5,15)]
        vals=[tstat(x) for x in r]
        print("%-13s %6d %8.2f %7.2f %8.2f %7.2f %8.2f %7.2f"%(c,len(r[0]),
          vals[0][0],vals[0][1],vals[1][0],vals[1][1],vals[2][0],vals[2][1]))

print("\n=== POOLED across xyz/io liquid names, in-session, THR sweep ===")
print("%-6s %7s %9s %7s %9s %7s %9s %7s"%("THR","n","f+1m","t","f+5m","t","f+15m","t"))
POOL=[c for c in S if c.startswith(("xyz:","io:"))]
for THR in (5,10,15,25,50,100):
    acc={1:[],5:[],15:[]}
    for c in POOL:
        t,px=S[c]
        idx=[i for i in range(1,len(px)-16) if t[i]-t[i-1]==60000 and insess(t[i])
             and abs((px[i]-px[i-1])/px[i-1]*1e4)>=THR]
        for h in acc:
            for i in idx:
                if t[i+h]-t[i]!=60000*h: continue
                s=1 if px[i]>px[i-1] else -1
                acc[h].append(s*(px[i+h]-px[i])/px[i]*1e4)
    if len(acc[1])<20: print("%-6d %7d (too few)"%(THR,len(acc[1]))); continue
    v=[tstat(acc[h]) for h in (1,5,15)]
    print("%-6d %7d %9.2f %7.2f %9.2f %7.2f %9.2f %7.2f"%(THR,len(acc[1]),
      v[0][0],v[0][1],v[1][0],v[1][1],v[2][0],v[2][1]))

print("\n=== how long must you HOLD for a 1-sigma move to equal the 9bp fee? ===")
print("(sd_1m in bps, in-session; minutes_to_9bp = (9/sd_1m)^2)")
print("%-13s %8s %12s"%("coin","sd_1m","min_to_9bp"))
for c,(t,px) in sorted(S.items()):
    ri=[]
    for i in range(len(px)-1):
        if t[i+1]-t[i]!=60000: continue
        if insess(t[i+1]): ri.append((px[i+1]-px[i])/px[i]*1e4)
    if len(ri)<50: continue
    sd=st.pstdev(ri)
    print("%-13s %8.2f %12.1f"%(c,sd,(9.0/sd)**2))
