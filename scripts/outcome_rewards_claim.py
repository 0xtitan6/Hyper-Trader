#!/usr/bin/env python3
"""Poll Outcome/Monarch LP rewards, record them, and alert when claimable.

Payout mechanics (discovered from the API 2026-09-19, NOT documented publicly):
  - Scoring runs in daily UTC epochs  (`included_epochs: ["20260918_0000:86400"]`)
  - A merkle root is published ~00:15 UTC for the PREVIOUS day
  - Rewards are CLAIM-based, not automatic, and the route expires ~7 days later
    (`route_expires_at`) — unclaimed rewards can therefore be LOST
  - Paid in USDC. Programme had distributed $153,679 as of 2026-09-19

Deliberately does NOT attempt the on-chain claim. The claim contract/ABI is not
in the frontend bundle, so the execution path is unknown until a real non-empty
payload shows its shape. Guessing at a signing flow for someone else's money is
how you lose it. This records the payload verbatim so the claim can be wired
correctly once there is one to inspect.

Doubles as the ATTRIBUTION TEST: if we quoted a full epoch with the builder code
and rewards is still empty, attribution is broken and the strategy is dead.

    ./scripts/outcome_rewards_claim.py           # poll + record
    ./scripts/outcome_rewards_claim.py --quiet   # cron mode, only alert on change
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

API = "https://api.monarch.fast"
MASTER = "0xE503186067b1B0Fb973c063054B14c4625434A1a"
LEDGER = Path("state/outcome_rewards.jsonl")
ENV = "/home/ec2-user/.config/hyper-trader/copytrader.env"


def get(path: str, tries: int = 6):
    for k in range(tries):
        try:
            r = requests.get(f"{API}{path}", headers={"Origin": "https://monarch.fast"}, timeout=25)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(1.5 * (k + 1))
    return None


def alert(text: str) -> None:
    """Telegram via the same webhook the engine uses. Never fatal."""
    try:
        env = dict(
            line.split("=", 1)
            for line in Path(ENV).read_text().splitlines()
            if "=" in line and not line.startswith("#")
        )
        url, chat = env.get("ALERT_WEBHOOK_URL"), env.get("TELEGRAM_CHAT_ID")
        if url and chat:
            requests.post(url, data={"chat_id": chat, "text": text}, timeout=15)
    except Exception:  # noqa: BLE001 — alerting must never break the job
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true", help="cron mode: alert only on change")
    args = ap.parse_args()

    rewards = get(f"/marina/claims/rewards?address={MASTER}")
    proofs = get(f"/marina/claims/proofs?address={MASTER}")
    if rewards is None:
        print("rewards endpoint unreachable")
        return 2

    rw = rewards.get("rewards") or []
    cl = (proofs or {}).get("claims") or []
    total = 0.0
    for r in rw:
        for k in ("amount_usdc", "amount", "claimable_usdc"):
            if k in r:
                try:
                    total += float(r[k])
                except (TypeError, ValueError):
                    pass
                break

    rec = {
        "ts": time.time(),
        "epochs": rewards.get("included_epochs"),
        "root_updated_at": rewards.get("root_updated_at"),
        "route_expires_at": rewards.get("route_expires_at"),
        "n_rewards": len(rw),
        "n_claims": len(cl),
        "total_usdc": total,
        "rewards_raw": rw,
        "claims_raw": cl,
    }
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as f:
        f.write(json.dumps(rec) + "\n")

    print(f"epochs        : {rec['epochs']}")
    print(f"root updated  : {rec['root_updated_at']}")
    print(f"route expires : {rec['route_expires_at']}")
    print(f"rewards       : {len(rw)} entries, ${total:.4f} USDC")
    print(f"claims        : {len(cl)} entries")

    if rw or cl:
        # Non-empty payload is the thing we have been waiting for: it both proves
        # attribution works AND reveals the claim structure.
        print("\nCLAIMABLE — payload recorded to", LEDGER)
        print(json.dumps(rec["claims_raw"] or rec["rewards_raw"], indent=1)[:1200])
        alert(
            f"Outcome LP rewards CLAIMABLE: ${total:.4f} USDC "
            f"({len(rw)} rewards / {len(cl)} claims). Route expires {rec['route_expires_at']}. "
            f"Claim path not yet automated — payload in {LEDGER}."
        )
        return 0

    # Empty. Distinguish "not scored yet" from "attribution broken".
    quoted = os.path.exists("state/journal.jsonl") and any(
        "maker_start" in line for line in open("state/journal.jsonl", errors="ignore")
    )
    msg = "no rewards yet"
    if quoted:
        msg += " — we HAVE quoted with the builder code; if this persists past a full UTC epoch, attribution is broken"
    print("\n" + msg)
    if not args.quiet and quoted:
        alert(f"Outcome LP rewards: still $0. {msg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
