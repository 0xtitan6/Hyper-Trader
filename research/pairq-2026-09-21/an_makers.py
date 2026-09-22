import json, collections, statistics as st
F=json.load(open("research/pairq-2026-09-21/maker_fills.json"))
legs=set(); tot=0; outf=0
for a,fl in F.items():
    for f in fl:
        tot+=1
        if f["coin"].startswith("#"): outf+=1; legs.add(f["coin"])
print(f"total fills {tot}, outcome-leg fills {outf} ({outf/tot*100:.1f}%), distinct legs {len(legs)}")
mk=collections.Counter(); 
for a,fl in F.items():
    for f in fl:
        if f["coin"].startswith("#"):
            mk[a]+=1
for a,n in mk.most_common(): print(f"  {a} {n} outcome fills")
json.dump(sorted(legs),open("research/pairq-2026-09-21/legs.json","w"))
