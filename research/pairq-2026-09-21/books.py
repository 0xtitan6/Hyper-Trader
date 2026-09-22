"""Snapshot both legs of every flowing outcome surface and compute the two
economics that matter:

  paired_edge   = 1 - (bidY+tick) - (bidN+tick)   <- we earn this if BOTH fill
  cross_cost_Y  = (bidY+tick) + askN - 1          <- we PAY this if only Y fills
  cross_cost_N  = (bidN+tick) + askY - 1

If cross_cost is reliably positive, hedging a one-sided fill is a locked loss
by construction, not bad luck.
"""
import json, time, urllib.request, sys
INFO = "https://api.hyperliquid.xyz/info"
TICK = 0.0005

def post(body):
    req = urllib.request.Request(INFO, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    for a in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                out = json.loads(r.read().decode())
            time.sleep(0.15); return out
        except Exception:
            if a == 4: return None
            time.sleep(2.0 * (a + 1))

rows = json.load(open("research/pairq-2026-09-21/screen.json"))
flow = sorted([r for r in rows if r["n24"] >= 20], key=lambda r: -r["n24"])
print(f"{len(flow)} surfaces with >=20 trades/24h on the YES leg", file=sys.stderr)

out = []
for i, r in enumerate(flow):
    oid = r["oid"]; legs = {}
    ok = True
    for side in (0, 1):
        b = post({"type": "l2Book", "coin": f"#{10*oid+side}"})
        lv = (b or {}).get("levels") or []
        if len(lv) < 2 or not lv[0] or not lv[1]:
            ok = False; break
        legs[side] = {"bid": float(lv[0][0]["px"]), "ask": float(lv[1][0]["px"]),
                      "bsz": float(lv[0][0]["sz"]), "asz": float(lv[1][0]["sz"])}
    if not ok: continue
    y, n = legs[0], legs[1]
    if min(y["bid"], n["bid"]) < 0.02: continue
    rec = dict(r)
    rec.update({
        "bidY": y["bid"], "askY": y["ask"], "bidN": n["bid"], "askN": n["ask"],
        "paired_edge": 1.0 - (y["bid"] + TICK) - (n["bid"] + TICK),
        "cross_Y": (y["bid"] + TICK) + n["ask"] - 1.0,
        "cross_N": (n["bid"] + TICK) + y["ask"] - 1.0,
        "spreadY": y["ask"] - y["bid"], "spreadN": n["ask"] - n["bid"],
        "midsum": (y["bid"]+y["ask"])/2 + (n["bid"]+n["ask"])/2,
    })
    out.append(rec)
    if i % 25 == 0: print(i, file=sys.stderr)

json.dump(out, open("research/pairq-2026-09-21/books.json", "w"))
print(f"snapshot {len(out)} surfaces")
