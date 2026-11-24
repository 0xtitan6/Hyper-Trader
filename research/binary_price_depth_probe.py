"""binaryPrice HIP-4 flow + depth probe.

Follow-up (1) from research/barrier-depth-2026-09-29.md:
priceTouch confirmed dead — capacity single-digit $ / barrier / day.
Question: does template:binaryPrice (n=99) look materially different?

Method:
  1. Enumerate all binaryPrice outcomes with future expiry.
  2. Pull 24h 1h candles per coin -> sum trades (n) and USD volume (v*close).
  3. For top-20 by trade count, snap l2Book x 3 (spread, best-bid $, top-5 $).
  4. Rank by realised flow. Never trust depth without flow.

Read-only. Sleep 0.3s between HL info calls. No orders.
"""
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("research/binary_price_depth_samples.jsonl")
INFO = "https://api.hyperliquid.xyz/info"
SNAP_COUNT = 3
SNAP_INTERVAL_S = 20
TOP_N = 20


def post(body):
    req = urllib.request.Request(
        INFO,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def parse_expiry(s):
    try:
        return datetime.strptime(s, "%Y%m%d-%H%M").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def enumerate_markets():
    meta = post({"type": "outcomeMeta"})
    now = datetime.now(timezone.utc)
    out = []
    for o in meta["outcomes"]:
        if o.get("name") != "template:binaryPrice":
            continue
        parts = dict(
            p.split(":", 1) for p in o.get("description", "").split("|") if ":" in p
        )
        exp = parse_expiry(parts.get("time", ""))
        if not exp or exp < now:
            continue
        out.append(
            {
                "coin": f"#{10 * o['outcome']}",
                "outcome": o["outcome"],
                "perp": parts.get("perp"),
                "threshold": float(parts.get("threshold", "nan")),
                "seconds": int(parts.get("seconds", "0") or 0),
                "expiry": parts.get("time"),
                "expiry_ts": exp.timestamp(),
            }
        )
    return out


def hourly_flow(coin, hours=24):
    now_ms = int(time.time() * 1000)
    start = now_ms - hours * 3600_000
    try:
        cs = post(
            {
                "type": "candleSnapshot",
                "req": {
                    "coin": coin,
                    "interval": "1h",
                    "startTime": start,
                    "endTime": now_ms,
                },
            }
        )
    except Exception as e:
        return {"error": str(e), "trades": 0, "usd_vol": 0.0, "n_bars": 0}
    trades = sum(int(c.get("n", 0)) for c in cs)
    usd_vol = sum(float(c.get("v", 0)) * float(c.get("c", 0)) for c in cs)
    return {"trades": trades, "usd_vol": usd_vol, "n_bars": len(cs)}


def book_snap(coin):
    b = post({"type": "l2Book", "coin": coin})
    bids, asks = b["levels"]

    def top5(l):
        return sum(float(x["sz"]) * float(x["px"]) for x in l[:5])

    bb_px = float(bids[0]["px"]) if bids else None
    bb_sz = float(bids[0]["sz"]) if bids else None
    ba_px = float(asks[0]["px"]) if asks else None
    ba_sz = float(asks[0]["sz"]) if asks else None
    return {
        "ts": b["time"],
        "best_bid": bb_px,
        "best_bid_usd": (bb_px or 0) * (bb_sz or 0),
        "best_ask": ba_px,
        "best_ask_usd": (ba_px or 0) * (ba_sz or 0),
        "spread": (ba_px - bb_px) if (bb_px and ba_px) else None,
        "bid_top5_usd": top5(bids),
        "ask_top5_usd": top5(asks),
        "bid_n": len(bids),
        "ask_n": len(asks),
    }


def main():
    mkts = enumerate_markets()
    print(f"active binaryPrice markets: {len(mkts)}", file=sys.stderr)

    # Stage 1 — flow per market
    flows = []
    for i, m in enumerate(mkts):
        f = hourly_flow(m["coin"])
        row = {**m, **f}
        flows.append(row)
        time.sleep(0.3)
        if (i + 1) % 20 == 0:
            print(f"  flow {i+1}/{len(mkts)}", file=sys.stderr)

    flows.sort(key=lambda r: (r["trades"], r["usd_vol"]), reverse=True)

    # Stage 2 — top-N depth snaps
    top = flows[:TOP_N]
    print(f"top {TOP_N} by trade count:", file=sys.stderr)
    for r in top:
        print(
            f"  {r['perp']:12s} thr={r['threshold']:>10.4g} exp={r['expiry']} "
            f"trades={r['trades']:5d} usd_vol=${r['usd_vol']:>10,.0f} {r['coin']}",
            file=sys.stderr,
        )

    with OUT.open("w") as fh:
        for r in flows:
            fh.write(json.dumps({"kind": "flow", **r}) + "\n")

        for round_i in range(SNAP_COUNT):
            for r in top:
                try:
                    s = book_snap(r["coin"])
                    s.update(
                        {
                            "kind": "book",
                            "round": round_i,
                            "coin": r["coin"],
                            "perp": r["perp"],
                            "threshold": r["threshold"],
                            "trades_24h": r["trades"],
                        }
                    )
                    fh.write(json.dumps(s) + "\n")
                except Exception as e:
                    fh.write(
                        json.dumps({"kind": "book_err", "coin": r["coin"], "err": str(e)})
                        + "\n"
                    )
                time.sleep(0.3)
            fh.flush()
            if round_i < SNAP_COUNT - 1:
                time.sleep(SNAP_INTERVAL_S)

    print(f"wrote {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
