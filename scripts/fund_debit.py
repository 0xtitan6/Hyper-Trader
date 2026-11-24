#!/usr/bin/env python3
"""Convert USDC → USD on Coinbase when USD balance drops below floor.

Debit card spends against USD balance. When it runs low, this converts USDC
(easier to top up from on-chain) into USD so the debit card keeps working.

Safety rails:
- Only converts USDC → USD, never the reverse (no accidental USD→USDC drain)
- Hard max per conversion: $100
- Hard daily max: $100 (checked against local journal)
- Floor-triggered: only runs when USD balance < USD_FLOOR
- Dry-run flag required for first use
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, "/home/ec2-user/.openclaw/workspace/hyper-trader")
import glob
for sp in glob.glob("/home/ec2-user/.openclaw/workspace/hyper-trader/.venv/lib/python*/site-packages"):
    sys.path.insert(0, sp)

from coinbase.rest import RESTClient

ENV_FILE = Path("/home/ec2-user/.config/hyper-trader/coinbase.env")
JOURNAL = Path(__file__).resolve().parent.parent / "state" / "fund_debit.jsonl"
JOURNAL.parent.mkdir(parents=True, exist_ok=True)

# Rails
USD_FLOOR = 25.0           # convert when USD < this
TARGET_USD = 50.0          # top up to this
MAX_PER_CONVERSION = 100.0
MAX_PER_DAY = 100.0


def load_env() -> tuple[str, str]:
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith("COINBASE_CDP_API_KEY_NAME="):
            k = line.split("=", 1)[1].strip()
        elif line.startswith("COINBASE_CDP_API_KEY_SECRET="):
            s = line.split("=", 1)[1].strip()
    return k, s


def balance_of(client: RESTClient, currency: str) -> float:
    for a in client.get_accounts().accounts:
        if a.currency == currency:
            bal = a.available_balance
            return float(bal.get("value", 0) if isinstance(bal, dict) else bal.value)
    return 0.0


def spent_today_usd() -> float:
    if not JOURNAL.exists():
        return 0.0
    cutoff = (datetime.now(UTC) - timedelta(hours=24)).timestamp()
    total = 0.0
    for line in JOURNAL.read_text().splitlines():
        try:
            r = json.loads(line)
            if r.get("ts", 0) >= cutoff and r.get("status") == "ok":
                total += float(r.get("amount_usd", 0))
        except Exception:
            pass
    return total


def journal(event: dict) -> None:
    event["ts"] = int(time.time())
    with JOURNAL.open("a") as f:
        f.write(json.dumps(event) + "\n")


def convert_usdc_to_usd(client: RESTClient, amount_usd: float, dry_run: bool) -> dict:
    if amount_usd > MAX_PER_CONVERSION:
        return {"status": "error", "reason": f"amount {amount_usd} > max {MAX_PER_CONVERSION}"}

    spent = spent_today_usd()
    if spent + amount_usd > MAX_PER_DAY:
        return {"status": "error", "reason": f"daily cap: {spent}+{amount_usd} > {MAX_PER_DAY}"}

    if dry_run:
        return {"status": "dry_run", "would_convert_usd": amount_usd}

    # Coinbase convert API: USDC → USD
    try:
        quote = client.create_convert_quote(
            from_account="USDC",
            to_account="USD",
            amount=str(amount_usd),
        )
        trade_id = quote.trade.id if hasattr(quote, "trade") else quote["trade"]["id"]
        commit = client.commit_convert_trade(trade_id=trade_id, from_account="USDC", to_account="USD")
        return {"status": "ok", "trade_id": trade_id, "amount_usd": amount_usd}
    except Exception as e:
        return {"status": "error", "reason": str(e)[:200]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--force", action="store_true", help="Skip floor check")
    args = ap.parse_args()

    if not (args.dry_run or args.live):
        print("Pass --dry-run or --live", file=sys.stderr); return 2

    k, s = load_env()
    client = RESTClient(api_key=k, api_secret=s)

    usd = balance_of(client, "USD")
    usdc = balance_of(client, "USDC")
    print(f"USD balance: ${usd:.2f}, USDC: ${usdc:.2f}", file=sys.stderr)

    if not args.force and usd >= USD_FLOOR:
        print(f"USD ${usd:.2f} >= floor ${USD_FLOOR}, no action", file=sys.stderr)
        journal({"status": "skip", "usd": usd, "usdc": usdc})
        return 0

    need = TARGET_USD - usd
    convert_amt = min(need, usdc, MAX_PER_CONVERSION)
    if convert_amt < 1:
        print(f"insufficient USDC ({usdc:.2f}) for meaningful conversion", file=sys.stderr)
        return 3

    result = convert_usdc_to_usd(client, convert_amt, dry_run=args.dry_run)
    result["usd_before"] = usd
    result["usdc_before"] = usdc
    journal(result)
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") in ("ok", "dry_run") else 4


if __name__ == "__main__":
    sys.exit(main())
