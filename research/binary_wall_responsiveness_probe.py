"""binaryPrice incumbent-wall responsiveness probe.

Follow-up from research/binary-price-depth-2026-09-30.md: the 09-30 report
called the top-book incumbent on binaryPrice markets a "calibrated fixed
policy" because best-bid did not change over 40 s on the top-5. Open
question: is the incumbent actually frozen, or just slow? We now observe
the three live xyz:CL binaryPrice markets over 5 minutes alongside xyz:CL
mid. If the incumbent reprices in step with CL moves, maker-fade is still
alive; if not, the 09-30 verdict holds.

Read-only. No orders. 10s interval, ~4 calls/iter, 0.15s sleep between
calls to stay well under HL rate limits.
"""
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("research/binary_wall_responsiveness_samples.jsonl")
INFO = "https://api.hyperliquid.xyz/info"
BINS = ["#73540", "#73550", "#77420"]  # xyz:CL@100, @82, @91.5
ITERS = 30
INTERVAL_S = 10


def post(body):
    req = urllib.request.Request(
        INFO,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def cl_mid():
    m = post({"type": "allMids", "dex": "xyz"})
    return float(m.get("xyz:CL", "0"))


def book(coin):
    b = post({"type": "l2Book", "coin": coin})
    levels = b.get("levels", [[], []])
    bid = ask = bid_sz = ask_sz = None
    if levels[0]:
        bid = float(levels[0][0]["px"])
        bid_sz = float(levels[0][0]["sz"])
    if levels[1]:
        ask = float(levels[1][0]["px"])
        ask_sz = float(levels[1][0]["sz"])
    return bid, ask, bid_sz, ask_sz


def main():
    OUT.parent.mkdir(exist_ok=True)
    f = OUT.open("w")
    print(f"start {datetime.now(timezone.utc).isoformat()}", file=sys.stderr)
    for i in range(ITERS):
        t0 = time.time()
        row = {"iter": i, "ts": time.time()}
        try:
            row["cl_mid"] = cl_mid()
            time.sleep(0.15)
            for c in BINS:
                b_bid, b_ask, b_bsz, b_asz = book(c)
                row[c] = {"bid": b_bid, "ask": b_ask, "bsz": b_bsz, "asz": b_asz}
                time.sleep(0.15)
        except Exception as e:
            row["err"] = str(e)
        f.write(json.dumps(row) + "\n")
        f.flush()
        elapsed = time.time() - t0
        sleep_for = max(0.0, INTERVAL_S - elapsed)
        time.sleep(sleep_for)
    f.close()
    print(f"wrote {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
