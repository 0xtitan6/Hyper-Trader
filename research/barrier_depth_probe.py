"""Poll l2Book for the 7 active priceTouch barriers.

Question: is the standing best bid/ask on BTC/HYPE barrier markets real
depth or a dust quote? Follow-up (3) from research/barrier-lag-2026-09-28.md.

Read-only. Sleeps >= 0.3s between requests. No orders placed.
"""
import json, urllib.request, time, sys
from pathlib import Path

OUT = Path("research/barrier_depth_samples.jsonl")
DURATION_S = 300
CADENCE_S = 3.0
INFO_URL = "https://api.hyperliquid.xyz/info"

def post(body):
    req = urllib.request.Request(
        INFO_URL,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=15).read())

def barriers():
    meta = post({"type": "outcomeMeta"})
    out = []
    for o in meta["outcomes"]:
        if o.get("name") != "template:priceTouch":
            continue
        desc = o.get("description", "")
        parts = dict(p.split(":", 1) for p in desc.split("|") if ":" in p)
        out.append({
            "coin": f"#{10 * o['outcome']}",
            "outcome": o["outcome"],
            "perp": parts.get("perp"),
            "target": float(parts.get("target", "nan")),
            "expiry": parts.get("time"),
        })
    return out

def snap(coin):
    b = post({"type": "l2Book", "coin": coin})
    bids, asks = b["levels"]
    def total(levels):
        return sum(float(l["sz"]) * float(l["px"]) for l in levels)
    def top5(levels):
        return sum(float(l["sz"]) * float(l["px"]) for l in levels[:5])
    best_bid_px = float(bids[0]["px"]) if bids else None
    best_bid_sz = float(bids[0]["sz"]) if bids else None
    best_ask_px = float(asks[0]["px"]) if asks else None
    best_ask_sz = float(asks[0]["sz"]) if asks else None
    return {
        "ts": b["time"],
        "coin": coin,
        "best_bid": best_bid_px,
        "best_bid_usd": (best_bid_px or 0) * (best_bid_sz or 0),
        "best_ask": best_ask_px,
        "best_ask_usd": (best_ask_px or 0) * (best_ask_sz or 0),
        "spread": (best_ask_px - best_bid_px) if (best_bid_px and best_ask_px) else None,
        "bid_top5_usd": top5(bids),
        "ask_top5_usd": top5(asks),
        "bid_total_usd": total(bids),
        "ask_total_usd": total(asks),
        "bid_n_lvls": len(bids),
        "ask_n_lvls": len(asks),
    }

def main():
    bs = barriers()
    print(f"barriers: {len(bs)} -- {[(b['perp'], int(b['target']), b['coin']) for b in bs]}",
          file=sys.stderr)
    end = time.time() + DURATION_S
    n = 0
    with OUT.open("w") as f:
        while time.time() < end:
            # Sample BTC perp mid for co-timing
            try:
                mids = post({"type": "allMids"})
                perp_mids = {k: mids.get(k) for k in ("BTC", "HYPE")}
            except Exception as e:
                perp_mids = {"error": str(e)}
            time.sleep(0.3)
            for b in bs:
                try:
                    s = snap(b["coin"])
                    s["perp"] = b["perp"]
                    s["target"] = b["target"]
                    s["perp_mid"] = perp_mids.get(b["perp"])
                    f.write(json.dumps(s) + "\n")
                    n += 1
                except Exception as e:
                    f.write(json.dumps({"error": str(e), "coin": b["coin"]}) + "\n")
                time.sleep(0.3)
            f.flush()
            time.sleep(max(0, CADENCE_S - 0.3 * (len(bs) + 1)))
    print(f"wrote {n} samples to {OUT}", file=sys.stderr)

if __name__ == "__main__":
    main()
