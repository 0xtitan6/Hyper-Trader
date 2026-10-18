#!/usr/bin/env python3
"""Gatekept bet shipper — REFUSES to send any HL sports outcome order without
first running edge_check and seeing verdict == BET.

Usage:
    python ship_bet.py <coin> <side> <usd> <team_abbr>
Example:
    python ship_bet.py "#114590" YES 50 KC

Flow:
    1. Resolve team from coin + outcomeMeta
    2. Run edge_check.py <team> → verdict line
    3. If verdict contains "BET:" → place IOC buy at ask+2%, size = usd/ask
       If verdict contains "PASS" → abort, journal why
    4. Journal every call (bet or abort) to state/firecrawl_attribution.jsonl

Only path to ship a sports bet. If you bypass this and go direct to
exchange.order(), you're going back to the pattern that cost us $180 on 10-18.
"""
from __future__ import annotations
import json, os, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, "/home/ec2-user/.openclaw/workspace/hyper-trader")
import glob
for sp in glob.glob("/home/ec2-user/.openclaw/workspace/hyper-trader/.venv/lib/python*/site-packages"):
    sys.path.insert(0, sp)

from src.config import load_config
from src.hl_outcome import register_outcome_assets
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from eth_account import Account

ATTRIBUTION = Path(__file__).resolve().parent.parent / "state" / "firecrawl_attribution.jsonl"
MAX_STAKE_USD = 75  # hard cap until monitor backtest proves auto-flat net positive

def journal(record: dict) -> None:
    record.setdefault("ts", int(time.time()))
    with ATTRIBUTION.open("a") as f:
        f.write(json.dumps(record) + "\n")

def run_edge_check(team: str) -> tuple[str, str]:
    """Returns (verdict, full_output)."""
    r = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "edge_check.py"), team],
        capture_output=True, text=True, timeout=60,
    )
    out = (r.stdout or "") + (r.stderr or "")
    verdict = "UNKNOWN"
    for line in out.splitlines():
        if "VERDICT:" in line:
            verdict = line.split("VERDICT:")[1].strip().rstrip("*").strip()
            break
    return verdict, out

def main() -> int:
    if len(sys.argv) < 5:
        sys.exit("usage: ship_bet.py <coin:#NNNNN0> <side:YES|NO> <usd> <team_abbr>")
    coin = sys.argv[1]
    side = sys.argv[2].upper()
    usd = float(sys.argv[3])
    team = sys.argv[4].upper()

    if usd > MAX_STAKE_USD:
        print(f"REJECT: stake ${usd} > hard cap ${MAX_STAKE_USD}", file=sys.stderr)
        journal({"decision": "rejected", "reason": "over_stake_cap", "coin": coin,
                 "team": team, "stake_usd": usd, "cap": MAX_STAKE_USD})
        return 2

    print(f"=== ship_bet: {coin} {side} ${usd} ({team}) ===", file=sys.stderr)
    print(f"Running edge_check {team}...", file=sys.stderr)
    verdict, output = run_edge_check(team)
    print(f"Verdict: {verdict}", file=sys.stderr)

    if "BET:" not in verdict:
        print(f"REJECTED by edge_check — not shipping.", file=sys.stderr)
        journal({"decision": "rejected_by_edge_check", "coin": coin, "side": side,
                 "team": team, "stake_usd": usd, "verdict": verdict})
        print("--- edge_check output (last 20 lines) ---", file=sys.stderr)
        for line in output.splitlines()[-20:]:
            print(line, file=sys.stderr)
        return 3

    # Verdict allows it — ship
    cfg = load_config()
    wallet = Account.from_key(cfg.private_key)
    info = Info(cfg.hyperliquid_api_url, skip_ws=True)
    register_outcome_assets(info)
    exchange = Exchange(wallet, cfg.hyperliquid_api_url, account_address=cfg.account_address)
    register_outcome_assets(exchange.info)

    book = info.post("/info", {"type": "l2Book", "coin": coin})
    if not book or not book.get("levels"):
        print(f"REJECT: empty book on {coin}", file=sys.stderr)
        journal({"decision": "rejected", "reason": "empty_book", "coin": coin,
                 "team": team, "stake_usd": usd, "verdict": verdict})
        return 4

    is_buy = (side == "YES")
    px_lvl = book["levels"][1 if is_buy else 0]
    if not px_lvl:
        print(f"REJECT: empty {('ask' if is_buy else 'bid')} on {coin}", file=sys.stderr)
        journal({"decision": "rejected", "reason": "empty_level", "coin": coin,
                 "team": team, "stake_usd": usd})
        return 4
    px = float(px_lvl[0]["px"])
    sz = round(usd / px)
    if sz < 1:
        print(f"REJECT: size {sz} < 1 on {coin}", file=sys.stderr)
        journal({"decision": "rejected", "reason": "size_rounds_zero", "coin": coin,
                 "team": team, "stake_usd": usd, "px": px})
        return 4

    ioc_px = round(px * (1.02 if is_buy else 0.98), 5)
    print(f"SHIPPING: {'BUY' if is_buy else 'SELL'} {sz}@{ioc_px} ({coin})", file=sys.stderr)
    r = exchange.order(coin, is_buy, sz, ioc_px,
        order_type={"limit": {"tif": "Ioc"}}, reduce_only=False)
    print(f"result: {r}", file=sys.stderr)

    journal({
        "decision": "shipped", "coin": coin, "side": side, "team": team,
        "stake_usd": usd, "entry_px": px, "ioc_px": ioc_px, "sz": sz,
        "verdict": verdict, "source": "firecrawl/kalshi/edge_check",
        "result": r,
    })
    return 0

if __name__ == "__main__":
    sys.exit(main())
