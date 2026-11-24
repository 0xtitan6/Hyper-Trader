#!/usr/bin/env python3
"""Autonomous HL topup via WaaP agent wallet.

Flow:
1. Check HL account free margin
2. If below THRESHOLD_USD, request a topup
3. WaaP CLI signs an ERC20 USDC transfer on Arbitrum to the HL account owner
4. Journal the tx, caps + allowlist enforced in code

Safety rails:
- DESTINATION hardcoded (= HL account owner addr 0xE503186067b1B0Fb973c063054B14c4625434A1a)
- MAX_SINGLE_TOPUP_USD = $100 (daily cap of $200 handled server-side by WaaP policy)
- Dry-run flag required for first use
- Journal every tx to state/topup.jsonl

Call: `python topup.py --dry-run` first, then `python topup.py --live`
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/ec2-user/.openclaw/workspace/hyper-trader")
# Add venv site-packages so hyperliquid imports resolve
import glob
for sp in glob.glob("/home/ec2-user/.openclaw/workspace/hyper-trader/.venv/lib/python*/site-packages"):
    sys.path.insert(0, sp)

# === HARD-CODED RAILS ===
HL_ACCOUNT_OWNER = "0xE503186067b1B0Fb973c063054B14c4625434A1a"  # Neil's main HL trading addr
WAAP_WALLET = "0x50101b0c2ba2b53cb8d133a4842b4de15c68e888"
ARBITRUM_CHAIN = "evm:42161"
USDC_ARB = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"  # Circle USDC on Arbitrum
MAX_SINGLE_TOPUP_USD = 100
THRESHOLD_USD = 50  # trigger topup if free margin < this

# ERC20 transfer(address,uint256) selector + encoded args
# selector = 0xa9059cbb
# USDC is 6 decimals

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
JOURNAL = STATE_DIR / "topup.jsonl"
WAAP_SESSION_DIR = "/home/ec2-user/.config/waap-cli"


def hl_free_margin() -> float | None:
    """Pull free margin from Neil's HL account via existing engine code."""
    try:
        from src.config import load_config
        from hyperliquid.info import Info
        cfg = load_config()
        info = Info(cfg.hyperliquid_api_url, skip_ws=True)
        state = info.post("/info", {"type": "clearinghouseState", "user": cfg.account_address})
        if not state:
            return None
        margin = state.get("marginSummary") or {}
        acct_value = float(margin.get("accountValue", 0))
        margin_used = float(margin.get("totalMarginUsed", 0))
        return acct_value - margin_used
    except Exception as e:
        print(f"hl_free_margin err: {e}", file=sys.stderr)
        return None


def encode_erc20_transfer(to_addr: str, amount_usdc: float) -> str:
    """Hand-encode ERC20 transfer(address,uint256). Returns 0x-prefixed hex."""
    to_hex = to_addr.lower().replace("0x", "").rjust(64, "0")
    # USDC = 6 decimals
    amount_wei = int(amount_usdc * 10**6)
    amount_hex = f"{amount_wei:064x}"
    return "0xa9059cbb" + to_hex + amount_hex


def waap_wallet_balance() -> dict:
    """Pull current balance from WaaP wallet on Arbitrum."""
    env = {**os.environ, "WAAP_CLI_SESSION_DIR": WAAP_SESSION_DIR}
    try:
        r = subprocess.run(
            ["waap-cli", "wallet-balance", "--chain", ARBITRUM_CHAIN, "--json"],
            capture_output=True, text=True, env=env, timeout=30,
        )
        return json.loads(r.stdout) if r.returncode == 0 else {"error": r.stderr}
    except Exception as e:
        return {"error": str(e)}


def send_topup(amount_usdc: float, dry_run: bool) -> dict:
    """Rail-protected USDC send to HL account owner addr."""
    # Rail 1: destination allowlist (hardcoded)
    dest = HL_ACCOUNT_OWNER
    # Rail 2: single-tx cap
    if amount_usdc > MAX_SINGLE_TOPUP_USD:
        return {"error": f"amount {amount_usdc} > MAX_SINGLE_TOPUP_USD {MAX_SINGLE_TOPUP_USD}"}
    if amount_usdc < 1:
        return {"error": f"amount {amount_usdc} < $1 min"}

    data = encode_erc20_transfer(dest, amount_usdc)

    cmd = [
        "waap-cli", "send-tx",
        "--to", USDC_ARB,     # contract = USDC
        "--value", "0",       # no ETH value
        "--data", data,       # encoded transfer call
        "--chain", ARBITRUM_CHAIN,
        "--json",
    ]
    if dry_run:
        return {"dry_run": True, "cmd": " ".join(cmd), "would_send": amount_usdc, "dest": dest}

    env = {**os.environ, "WAAP_CLI_SESSION_DIR": WAAP_SESSION_DIR}
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
        out = json.loads(r.stdout) if r.stdout else {}
        if r.returncode != 0:
            out["error"] = r.stderr
        return out
    except Exception as e:
        return {"error": str(e)}


def journal(event: dict) -> None:
    event["ts"] = int(time.time())
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(JOURNAL, "a") as f:
        f.write(json.dumps(event) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--amount", type=float, help="Amount USDC to send (overrides auto-size)")
    ap.add_argument("--dry-run", action="store_true", help="Compute but don't broadcast")
    ap.add_argument("--live", action="store_true", help="Explicitly confirm live run")
    ap.add_argument("--force", action="store_true", help="Skip margin threshold check")
    args = ap.parse_args()

    if not (args.dry_run or args.live):
        print("Specify --dry-run or --live", file=sys.stderr); return 2

    # Margin check
    free = hl_free_margin()
    print(f"HL free margin: ${free}", file=sys.stderr)
    if free is None:
        journal({"event": "margin_check_failed"})
        print("Can't read HL margin — aborting", file=sys.stderr); return 3

    if not args.force and free > THRESHOLD_USD:
        print(f"Margin ${free:.2f} > threshold ${THRESHOLD_USD}, no topup needed", file=sys.stderr)
        return 0

    # Size the topup
    amount = args.amount if args.amount else min(MAX_SINGLE_TOPUP_USD, 50.0)

    # Check WaaP balance
    bal = waap_wallet_balance()
    print(f"WaaP wallet native balance: {bal}", file=sys.stderr)

    result = send_topup(amount, dry_run=args.dry_run)
    journal({"event": "topup", "amount": amount, "dest": HL_ACCOUNT_OWNER,
             "dry_run": args.dry_run, "result": result})
    print(json.dumps(result, indent=2))
    return 0 if "error" not in result else 4


if __name__ == "__main__":
    sys.exit(main())
