#!/usr/bin/env python3
"""Verify the Outcome builder-fee approval landed, and that we can attach the code.

The Outcome liquidity-rewards program scores ONLY orders carrying its builder
code, and the code is only honoured if the master wallet has approved the
builder address. That approval is a user-signed action: an agent/API wallet
CANNOT perform it (HL attributes the action to the signer, which then fails with
"Must deposit before performing actions"). So this is a read-only checker —
a human signs, this confirms.

    ./scripts/check_builder_approval.py
"""
from __future__ import annotations

import sys
import time

import requests

INFO = "https://api.hyperliquid.xyz/info"
MASTER = "0xE503186067b1B0Fb973c063054B14c4625434A1a"
BUILDER = "0xab5dbc057628bc18523c4cdfc0e1e2ebdbecb704"


def post(body: dict, tries: int = 6):
    """POST /info with backoff — our own research agents can saturate the API."""
    for k in range(tries):
        r = requests.post(INFO, json=body, timeout=25)
        if r.status_code == 200:
            return r.json()
        time.sleep(1.5 * (k + 1))
    return None


def main() -> int:
    fee = post({"type": "maxBuilderFee", "user": MASTER, "builder": BUILDER})
    print(f"master  : {MASTER}")
    print(f"builder : {BUILDER}")
    print(f"maxBuilderFee -> {fee!r}")

    approved = fee not in (None, 0, "0")
    if approved:
        print("\nAPPROVED — orders carrying this builder code will be scored.")
        print("Next: set risk.outcome_builder_address in config.yaml and start the maker in shadow mode.")
        return 0
    print("\nNOT APPROVED yet (0 = no approval on record).")
    print("A human must sign approveBuilderFee from the MASTER wallet:")
    print("  1. open outcome.xyz (or app.hyperliquid.xyz/outcomes) with the master wallet")
    print("  2. approve builder", BUILDER)
    print("  3. any small nonzero max fee rate is fine — the program itself charges 0")
    return 1


if __name__ == "__main__":
    sys.exit(main())
