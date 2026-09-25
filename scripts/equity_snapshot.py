#!/usr/bin/env python3
"""equity_snapshot.py

Append-only equity time-series: base perp + all 10 HIP-3 dex perps + spot USDC
+ HIP-4 outcome tokens, priced from allMids. One JSONL line per invocation.

Enforces MEMORY.md invariant "PnL must include EVERYTHING on HL" — reuses
audit_pnl.build_snapshot() so the definition of "everything" stays in one place.

Read-only against HL /info. No signing, no orders. Systemd timer fires every 30m.

Output: state/equity_snapshot.jsonl (append)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from audit_pnl import DEFAULT_ENV, STATE_DIR, build_snapshot, load_address


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=str(DEFAULT_ENV))
    ap.add_argument("--out", default=str(STATE_DIR / "equity_snapshot.jsonl"))
    args = ap.parse_args()

    address = load_address(Path(args.env))
    snap = build_snapshot(address)
    t = snap["totals"]
    line = {
        "ts": snap["timestamp_utc"],
        "verified": snap["verified"],
        "grand_total_usd": t["grand_total_usd"],
        "base_perp_equity_usd": t["base_perp_equity_usd"],
        "hip3_perp_equity_sum_usd": t["hip3_perp_equity_sum_usd"],
        "spot_usdc_usd": t["spot_usdc_usd"],
        "hip4_verified_mv_usd": t["hip4_outcome_verified_mv_usd"],
        "hip4_estimated_mv_usd": t["hip4_outcome_estimated_mv_usd"],
        "hip4_unpriced_count": t["hip4_outcome_unpriced_count"],
        "hip4_unpriced_entry_ntl_usd": t["hip4_outcome_unpriced_entry_ntl_usd"],
        "issue_count": len(snap.get("issues", [])),
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a") as fh:
        fh.write(json.dumps(line) + "\n")

    print(json.dumps(line))
    return 0 if snap["verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
