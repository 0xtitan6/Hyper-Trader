#!/usr/bin/env python3
"""Full-account equity snapshot. Appends to state/equity_snapshot.jsonl.

Writes one line per invocation summing: base perp equity, all HIP-3 dex perps,
base USDC, HIP-4 outcome spot token values. Per the standing invariant: every
PnL report must sum base perp + all 10 HIP-3 dex perps + base USDC + HIP-4
outcome tokens per dex, or say "partial".

Run via systemd timer every 30min. Idempotent — no state beyond the jsonl.
"""
from __future__ import annotations
import json, os, sys, time
from pathlib import Path

sys.path.insert(0, "/home/ec2-user/.openclaw/workspace/hyper-trader")
import glob
for sp in glob.glob("/home/ec2-user/.openclaw/workspace/hyper-trader/.venv/lib/python*/site-packages"):
    sys.path.insert(0, sp)

import urllib.request

ADDR = os.environ.get("HL_ACCOUNT_ADDRESS", "0xE503186067b1B0Fb973c063054B14c4625434A1a")
OUT = Path(__file__).resolve().parent.parent / "state" / "equity_snapshot.jsonl"
HL = "https://api.hyperliquid.xyz/info"

def post(body: dict) -> dict:
    req = urllib.request.Request(HL, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def main() -> int:
    try:
        # Base perp
        perp = post({"type": "clearinghouseState", "user": ADDR})
        base_perp_eq = float((perp or {}).get("marginSummary", {}).get("accountValue", 0))
        base_withdrawable = float((perp or {}).get("withdrawable", 0))

        # Spot (USDC + outcome tokens)
        spot = post({"type": "spotClearinghouseState", "user": ADDR})
        mids = post({"type": "allMids"})
        base_usdc = 0.0
        outcome_tokens_usd = 0.0
        token_count = 0
        for b in (spot or {}).get("balances", []):
            coin = b.get("coin", "")
            sz = float(b.get("total", 0))
            if coin == "USDC":
                base_usdc = sz
            elif coin.startswith("+") and sz > 0.5:
                px_key = "#" + coin[1:]
                px = float(mids.get(px_key, 0))
                outcome_tokens_usd += sz * px
                token_count += 1

        total = base_perp_eq + base_usdc + outcome_tokens_usd
        snap = {
            "ts": int(time.time()),
            "base_perp_eq": round(base_perp_eq, 2),
            "base_withdrawable": round(base_withdrawable, 2),
            "base_usdc": round(base_usdc, 2),
            "outcome_tokens_usd": round(outcome_tokens_usd, 2),
            "outcome_token_count": token_count,
            "total_usd": round(total, 2),
            "partial": True,          # HIP-3 dex perps not yet included
            "note": "base perp + spot + outcomes only; HIP-3 dex perps TBD",
        }
        with OUT.open("a") as f:
            f.write(json.dumps(snap) + "\n")
        print(f"snapshot: total=${total:.2f} (perp ${base_perp_eq:.2f}, usdc ${base_usdc:.2f}, outcomes ${outcome_tokens_usd:.2f})")
        return 0
    except Exception as e:
        print(f"snapshot err: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
