import json, statistics as st
B = json.load(open("research/pairq-2026-09-21/books.json"))
def med(xs): return st.median(xs) if xs else float("nan")

pe = [b["paired_edge"] for b in B]
cx = [b["cross_Y"] for b in B] + [b["cross_N"] for b in B]

print(f"n surfaces = {len(B)}   (cross observations n = {len(cx)})\n")
print("PAIRED EDGE  (earned only if BOTH legs fill passively)")
print(f"  median {med(pe)*100:+.3f}%   mean {st.mean(pe)*100:+.3f}%"
      f"   >0: {sum(1 for x in pe if x>0)}/{len(pe)}")
print("\nONE-SIDED COMPLETION COST  (pay this when one leg fills and we cross)")
print(f"  median {med(cx)*100:+.3f}%   mean {st.mean(cx)*100:+.3f}%"
      f"   >0 (a LOSS): {sum(1 for x in cx if x>0)}/{len(cx)}"
      f"   <=0 (profitable cross): {sum(1 for x in cx if x<=0)}/{len(cx)}")
print(f"  p10 {sorted(cx)[len(cx)//10]*100:+.3f}%  p90 {sorted(cx)[9*len(cx)//10]*100:+.3f}%")

print("\nBREAKEVEN PAIRED-FILL RATE  p* = C / (E + C)")
E, C = med(pe), med(cx)
print(f"  using medians E={E*100:.3f}%  C={C*100:.3f}%  ->  p* = {C/(E+C)*100:.1f}%")

def cat(d):
    if "priceTouch" in d or "binaryPrice" in d: return "crypto barrier"
    if "NFL" in d: return "NFL"
    if "participant:" in d: return "team/participant"
    if "priceBinary" in d: return "price binary"
    return "other"
print("\nBY CATEGORY")
print(f"{'category':>16} {'n':>3} {'medEdge':>9} {'medCross':>9} {'p*':>7} {'medSprd':>8}")
seen = {}
for b in B: seen.setdefault(cat(b["desc"]), []).append(b)
for k, v in sorted(seen.items(), key=lambda kv: -len(kv[1])):
    e = med([x["paired_edge"] for x in v])
    c = med([x["cross_Y"] for x in v] + [x["cross_N"] for x in v])
    s = med([x["spreadY"] for x in v] + [x["spreadN"] for x in v])
    ps = c/(e+c)*100 if (e+c) != 0 else float("nan")
    print(f"{k:>16} {len(v):>3} {e*100:>8.3f}% {c*100:>8.3f}% {ps:>6.1f}% {s*100:>7.3f}%")

print("\nIS THE BOOK COHERENT?  (askN vs 1-bidY)  -- if askN == 1-bidY exactly,")
print("the cross cost is EXACTLY one tick and the loss is arithmetic, not flow.")
coh = [abs(b["askN"] - (1 - b["bidY"])) for b in B] + [abs(b["askY"] - (1 - b["bidN"])) for b in B]
print(f"  median |askComplement - (1-bidLeg)| = {med(coh)*100:.4f}%  n={len(coh)}")
print(f"  within 0.1%: {sum(1 for x in coh if x<0.001)}/{len(coh)}")
print(f"  median midsum = {med([b['midsum'] for b in B]):.5f}")
