"""CL 1m shock-frequency probe.

Pulls 30d of 1m candles for xyz:CL and measures how often |ret_1m| > 50 bps —
the threshold identified in research/binary-wall-responsiveness-2026-10-03.md
as the "last-alive" condition under which a maker-fade might still work on
HIP-4 binaryPrice markets.

Read-only. Rate-limited by sleep between requests.
"""
import json
import time
import urllib.request
from datetime import datetime, timezone

INFO = "https://api.hyperliquid.xyz/info"

def post(body):
    req = urllib.request.Request(
        INFO, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())

# HL candleSnapshot caps at 5000 bars. 30d * 1440 min = 43200, so page.
# Pull 5000 bars at a time, going back from now.
now_ms = int(time.time() * 1000)
day_ms = 24 * 3600 * 1000
# 30 days
start = now_ms - 30 * day_ms
end = now_ms

candles = []
cur_start = start
page = 0
while cur_start < end:
    page += 1
    cur_end = min(cur_start + 5000 * 60 * 1000, end)  # 5000 1-min bars
    try:
        res = post({
            "type": "candleSnapshot",
            "req": {
                "coin": "xyz:CL",
                "interval": "1m",
                "startTime": cur_start,
                "endTime": cur_end,
            }
        })
        if isinstance(res, list):
            candles.extend(res)
            print(f"page {page}: {len(res)} bars, start={datetime.fromtimestamp(cur_start/1000, timezone.utc).isoformat()}")
        else:
            print(f"page {page}: non-list resp {str(res)[:200]}")
    except Exception as e:
        print(f"page {page}: err {e}")
    cur_start = cur_end + 1
    time.sleep(0.3)

print(f"total bars: {len(candles)}")

# Dedup by t (open time), sort
seen = {}
for c in candles:
    seen[c["t"]] = c
candles = sorted(seen.values(), key=lambda c: c["t"])
print(f"unique bars: {len(candles)}")

# Compute returns
returns = []
for i in range(1, len(candles)):
    prev = float(candles[i-1]["c"])
    curr = float(candles[i]["c"])
    if prev > 0:
        ret_bps = 10000 * (curr - prev) / prev
        returns.append((candles[i]["t"], ret_bps, curr))

if not returns:
    print("no returns"); raise SystemExit(1)

abs_rets = [abs(r[1]) for r in returns]
abs_rets.sort()
n = len(abs_rets)
def pct(p):
    k = int(p * n)
    k = max(0, min(n-1, k))
    return abs_rets[k]

print(f"\n|ret_1m| distribution over {n} 1-min bars (~{n/1440:.1f} days):")
for p in [0.50, 0.75, 0.90, 0.95, 0.99, 0.999, 1.0]:
    print(f"  p{int(p*1000)/10:>5}: {pct(p):8.2f} bps")

thresholds = [10, 20, 30, 50, 100, 200, 500]
print(f"\nShock-event counts:")
for t in thresholds:
    count = sum(1 for r in abs_rets if r >= t)
    per_day = count / (n/1440)
    print(f"  |ret_1m| >= {t:>4} bps : {count:>5} bars  ({per_day:6.2f}/day)")

# List biggest shocks with timestamps
big = sorted(returns, key=lambda r: -abs(r[1]))[:15]
print(f"\nTop 15 biggest 1-min moves:")
for t, r, c in big:
    print(f"  {datetime.fromtimestamp(t/1000, timezone.utc).isoformat()} {r:+8.1f} bps  close=${c:.3f}")

# Clustering: how often does >=50 bps happen in consecutive minutes?
clusters = 0
in_shock = False
for t, r, c in returns:
    if abs(r) >= 50:
        if not in_shock:
            clusters += 1
            in_shock = True
    else:
        in_shock = False
print(f"\n>=50bps shock clusters (consecutive-run): {clusters}  (~{clusters/(n/1440):.2f}/day)")

# Save returns summary
import os
os.makedirs("research", exist_ok=True)
with open("research/cl_shock_samples.jsonl", "w") as f:
    for t, r, c in returns:
        f.write(json.dumps({"t": t, "ret_bps": r, "close": c}) + "\n")
print(f"\nwrote research/cl_shock_samples.jsonl ({n} rows)")
