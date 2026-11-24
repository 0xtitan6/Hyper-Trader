#!/usr/bin/env python3
"""In-game BAL/CLE monitor + auto-flat on bad score.

Firecrawl + Alexandria polls the live game every 60s during the kickoff window.
If BAL leads by >10 at Q2+ → flat CLE YES to limit loss.
If CLE leads by >14 anytime → flat CLE YES to lock gain.
If game ends → flat remaining position via market order.

Journal every decision to state/balcle_monitor.jsonl.
"""
from __future__ import annotations

import json, os, subprocess, sys, time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, "/home/ec2-user/.openclaw/workspace/hyper-trader")
import glob
for sp in glob.glob("/home/ec2-user/.openclaw/workspace/hyper-trader/.venv/lib/python*/site-packages"):
    sys.path.insert(0, sp)

import urllib.request

FIRECRAWL_KEY = Path("/home/ec2-user/.config/hyper-trader/firecrawl.env").read_text().split("=", 1)[1].strip()
STATE = Path(__file__).resolve().parent.parent / "state"
JOURNAL = STATE / "balcle_monitor.jsonl"
LAST_SCORE = STATE / "balcle_last_score.json"

# Our position
CLE_YES = "#118051"
BAL_YES = "#118050"

# Rules
FLAT_IF_BAL_UP = 10    # flat our CLE YES if BAL leads by >10 in Q2+
TAKE_PROFIT_IF_CLE_UP = 14  # lock profit if CLE leads by >14
POLL_INTERVAL_S = 180

def journal(event: dict) -> None:
    event["ts"] = int(time.time())
    with JOURNAL.open("a") as f:
        f.write(json.dumps(event) + "\n")

def alex_game(game_id: str) -> dict | None:
    body = json.dumps({
        "alexandria": {"provider": "nfl-com", "capability": "sports-league-data/game",
                       "options": {"game_id": game_id}},
    }).encode()
    req = urllib.request.Request("https://api.firecrawl.dev/v2/scrape", data=body,
        headers={"Authorization": f"Bearer {FIRECRAWL_KEY}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read())
        rows = d.get("data", {}).get("alexandria", [])
        return rows[0].get("data") if rows and not rows[0].get("error") else None
    except Exception as e:
        print(f"alex err: {e}", file=sys.stderr)
        return None

def fetch_bal_cle_game_id() -> str | None:
    """Pull Week 6 schedule, find BAL vs CLE."""
    body = json.dumps({
        "alexandria": {"provider": "nfl-com", "capability": "sports-league-data/schedule",
                       "options": {"season": 2026, "week": 6}},
    }).encode()
    req = urllib.request.Request("https://api.firecrawl.dev/v2/scrape", data=body,
        headers={"Authorization": f"Bearer {FIRECRAWL_KEY}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read())
        rows = d.get("data", {}).get("alexandria", [])
        if not rows: return None
        games = rows[0].get("data", {}).get("games", []) or []
        for g in games:
            h = (g.get("home_team") or {}).get("abbreviation", "")
            a = (g.get("away_team") or {}).get("abbreviation", "")
            if {h, a} == {"BAL", "CLE"}:
                return g.get("id")
    except Exception as e:
        print(f"schedule err: {e}", file=sys.stderr)
    return None

def flat_position(coin: str, reason: str, dry_run: bool = False) -> dict:
    """Market-sell our full position in coin."""
    try:
        from src.config import load_config
        from hyperliquid.exchange import Exchange
        from hyperliquid.info import Info
        from eth_account import Account
        from src.hl_outcome import register_outcome_assets
        cfg = load_config()
        wallet = Account.from_key(cfg.private_key)
        info = Info(cfg.hyperliquid_api_url, skip_ws=True)
        register_outcome_assets(info)
        # Get current spot balance of this coin
        state = info.post("/info", {"type": "spotClearinghouseState", "user": cfg.account_address})
        sz = 0.0
        # HL spot balance uses `+NNNNN` identifier, L2 book uses `#NNNNN`.
        token_num = coin.lstrip("#").split("-")[0]
        spot_id = f"+{token_num}"
        for b in (state or {}).get("balances", []):
            if b.get("coin") == spot_id:
                sz = float(b.get("total", 0)); break
        if sz < 1:
            return {"status": "nothing_to_flat", "sz": sz}
        # Market sell
        book = info.post("/info", {"type": "l2Book", "coin": coin})
        bid = float(book["levels"][0][0]["px"])
        px = round(bid * 0.98, 5)  # 200bp below for sure-fill IOC
        if dry_run:
            return {"status": "dry_run", "would_sell": sz, "px": px}
        exchange = Exchange(wallet, cfg.hyperliquid_api_url, account_address=cfg.account_address)
        register_outcome_assets(exchange.info)
        r = exchange.order(coin, False, sz, px,
            order_type={"limit": {"tif": "Ioc"}}, reduce_only=False)
        return {"status": "ok", "reason": reason, "sz": sz, "result": r}
    except Exception as e:
        return {"status": "error", "err": str(e)[:200]}

def main() -> int:
    gid = fetch_bal_cle_game_id()
    if not gid:
        print("could not find BAL vs CLE game id", file=sys.stderr); return 1
    print(f"watching game_id={gid}", file=sys.stderr)
    journal({"event": "monitor_start", "game_id": gid})

    while True:
        now = datetime.now(UTC)
        # Only active during Sunday Oct 18 15:00Z - 23:30Z
        if not (now.year == 2026 and now.month == 10 and now.day == 18
                and 15 <= now.hour < 24):
            time.sleep(1800); continue

        data = alex_game(gid)
        if not data:
            time.sleep(POLL_INTERVAL_S); continue

        home = data.get("home_team", {}) or {}
        away = data.get("away_team", {}) or {}
        h_abbr = home.get("abbreviation", "")
        a_abbr = away.get("abbreviation", "")
        h_score = int(data.get("home_score") or 0)
        a_score = int(data.get("away_score") or 0)
        status = data.get("status") or data.get("game_status") or "?"
        # Feed returns quarter as a string ("Q2"); a bare `quarter >= 2` below
        # raised TypeError and killed this process the moment a flat threshold
        # was first met. Same bug as nfl_games_live_monitor.py. (2026-10-18)
        _q = str(data.get("quarter") or 0).upper().strip().lstrip("Q").strip()
        if _q.isdigit():
            quarter = int(_q)
        elif "OT" in _q:
            quarter = 5
        elif _q.startswith("H"):
            quarter = 2
        else:
            quarter = 0

        # Map scores to teams
        bal_score = h_score if h_abbr == "BAL" else a_score
        cle_score = h_score if h_abbr == "CLE" else a_score
        margin = cle_score - bal_score  # positive = CLE leading

        snapshot = {"BAL": bal_score, "CLE": cle_score, "margin": margin,
                    "quarter": quarter, "status": status}
        LAST_SCORE.write_text(json.dumps(snapshot))
        print(f"BAL {bal_score} - CLE {cle_score} (Q{quarter}) status={status}", file=sys.stderr)

        # Decision logic
        decision = None
        if status in ("FINAL", "FINISHED", "COMPLETE"):
            decision = "settle" if margin > 0 else "took_loss"
            journal({"event": "final", **snapshot, "decision": decision})
            break
        elif margin >= TAKE_PROFIT_IF_CLE_UP and quarter >= 2:
            # CLE leading big — lock profit before volatility reverses
            r = flat_position(CLE_YES, f"take_profit CLE+{margin} Q{quarter}")
            journal({"event": "take_profit", **snapshot, "flatten": r})
            break
        elif margin <= -FLAT_IF_BAL_UP and quarter >= 2:
            # BAL running away — cut loss
            r = flat_position(CLE_YES, f"cut_loss BAL+{-margin} Q{quarter}")
            journal({"event": "cut_loss", **snapshot, "flatten": r})
            break

        time.sleep(POLL_INTERVAL_S)

    print("monitor exiting", file=sys.stderr)
    return 0

if __name__ == "__main__":
    sys.exit(main())
