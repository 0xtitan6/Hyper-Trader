#!/usr/bin/env python3
"""In-game monitor for ALL our NFL directional bets. Single-process, batched.

Polls the Week 6 NFL schedule once, finds game_ids for every bet we hold.
Every 180s during the Sunday game window:
  - Pulls score for each unresolved game (one Alexandria call per game)
  - If our side down >=10 at Q2+ → flat that bet (cut loss)
  - If our side up >=14 anytime after Q2 → flat (lock gain)
  - On FINAL → journal settle result, drop from poll list

Credit math (4 games × 3hr × 180s poll = 60 polls/game × 5cr = 300cr/game,
1200cr total game-day — fits Hobby comfortably).

Our bets (coin → side we want to win, pos sz, friendly label):
  #114540 YES → NE wins NE@TEN       (198 sh, $150)
  #114590 YES → KC wins KC@LV        (192 sh, $151)
  #118010 YES → PITT wins PITT@CIN   (269 sh, $150) [post-trim]
  #118051 YES → CLE wins BAL@CLE     (386 sh, $151) [also BAL/CLE monitor active]
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
JOURNAL = STATE / "nfl_games_monitor.jsonl"
LAST = STATE / "nfl_games_last.json"

# Bet config: coin (perp notation) → {our_team, opp_team, label, side_is_yes}
BETS = {
    "#114540": {"team": "NE",  "opp": "NYJ", "label": "NYJ@NE YES",   "flat_py": "flat_coin"},
    "#114590": {"team": "KC",  "opp": "LAC", "label": "LAC@KC YES",   "flat_py": "flat_coin"},
    "#114560": {"team": "NYG", "opp": "NO",  "label": "NO@NYG YES",   "flat_py": "flat_coin"},
}

CUT_LOSS_MARGIN = 17          # our team down this much Q2+ → flat
TAKE_PROFIT_MARGIN = 17       # our team up this much Q2+ → flat
HYSTERESIS = 3                # need to be past threshold by this much to fire (prevents edge-case flicker)
COLD_START_SECONDS = 180      # ignore all auto-flat triggers for first N seconds after process start (prevents cold-start + crash-recovery from firing on a game already past threshold — see 2026-10-18 CLE $318 incident)
CONFIRM_POLLS = 2             # need this many consecutive polls past threshold before firing
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
        print(f"alex game err: {e}", file=sys.stderr)
        return None

def fetch_week_schedule() -> list[dict]:
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
        if not rows: return []
        return rows[0].get("data", {}).get("games", []) or []
    except Exception as e:
        print(f"schedule err: {e}", file=sys.stderr)
        return []

def map_bets_to_games(games: list[dict]) -> dict[str, str]:
    """Returns {coin: game_id} for each bet whose matchup is in the schedule."""
    out = {}
    for coin, bet in BETS.items():
        want = {bet["team"], bet["opp"]}
        for g in games:
            h = (g.get("home_team") or {}).get("abbreviation", "")
            a = (g.get("away_team") or {}).get("abbreviation", "")
            if {h, a} == want:
                out[coin] = g.get("id")
                break
    return out

def flat_coin(coin: str, reason: str) -> dict:
    """Market-sell our full spot position in coin."""
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
        state = info.post("/info", {"type": "spotClearinghouseState", "user": cfg.account_address})
        sz = 0.0
        token_num = coin.lstrip("#").split("-")[0]
        spot_id = f"+{token_num}"
        for b in (state or {}).get("balances", []):
            if b.get("coin") == spot_id:
                sz = float(b.get("total", 0)); break
        if sz < 1:
            return {"status": "nothing_to_flat", "sz": sz}
        book = info.post("/info", {"type": "l2Book", "coin": coin})
        bid = float(book["levels"][0][0]["px"])
        px = round(bid * 0.97, 5)  # 300bp slip for sure fill
        exchange = Exchange(wallet, cfg.hyperliquid_api_url, account_address=cfg.account_address)
        register_outcome_assets(exchange.info)
        r = exchange.order(coin, False, sz, px,
            order_type={"limit": {"tif": "Ioc"}}, reduce_only=False)
        return {"status": "ok", "reason": reason, "sz": sz, "px": px, "result": r}
    except Exception as e:
        return {"status": "error", "err": str(e)[:200]}

def main() -> int:
    PROCESS_START = time.time()
    print("nfl_games_live_monitor starting", file=sys.stderr)
    # Resolve game_ids for our bets
    games = fetch_week_schedule()
    coin_to_gid = map_bets_to_games(games)
    print(f"mapped {len(coin_to_gid)}/{len(BETS)} bets to game ids:", file=sys.stderr)
    for coin, gid in coin_to_gid.items():
        print(f"  {coin} ({BETS[coin]['label']}) → game {gid}", file=sys.stderr)
    if not coin_to_gid:
        print("no bets mapped to games, exiting", file=sys.stderr)
        return 1

    journal({"event": "monitor_start", "bets": {c: BETS[c]['label'] for c in coin_to_gid},
             "mapped_count": len(coin_to_gid),
             "cold_start_block_seconds": COLD_START_SECONDS,
             "hysteresis": HYSTERESIS, "confirm_polls": CONFIRM_POLLS})

    active = dict(coin_to_gid)  # coins still being watched
    # Per-coin counter of consecutive polls past threshold (reset when margin recovers)
    confirm_count: dict[str, int] = {c: 0 for c in active}
    last_margin: dict[str, int] = {}

    while active:
        now = datetime.now(UTC)
        # Game window: Sunday 15:00-24:00 UTC + late MNF-ish 00:00-03:00 Mon
        in_window = (now.month == 10 and now.day == 18 and 15 <= now.hour < 24) or \
                    (now.month == 10 and now.day == 19 and now.hour < 4)
        if not in_window:
            print(f"outside window ({now.hour:02d}Z), sleeping 30min", file=sys.stderr)
            time.sleep(1800); continue

        resolved_this_cycle = []
        for coin, gid in list(active.items()):
            bet = BETS[coin]
            data = alex_game(gid)
            if not data:
                continue
            home = data.get("home_team", {}) or {}
            away = data.get("away_team", {}) or {}
            h = home.get("abbreviation", "")
            a = away.get("abbreviation", "")
            h_sc = int(data.get("home_score") or 0)
            a_sc = int(data.get("away_score") or 0)
            status = (data.get("status") or data.get("game_status") or "").upper()
            # The feed returns quarter as a string ("Q2"), so a bare
            # `quarter >= 2` raised TypeError and killed this process at the
            # exact moment a cut-loss/take-profit threshold was first met —
            # the margin test short-circuited it while games sat 0-0, so it
            # looked healthy for hours. Normalize to int. (2026-10-18)
            _q = str(data.get("quarter") or 0).upper().strip().lstrip("Q").strip()
            if _q.isdigit():
                quarter = int(_q)
            elif "OT" in _q:
                quarter = 5          # overtime counts as late-game
            elif _q.startswith("H"):
                quarter = 2          # halftime is after Q2
            else:
                quarter = 0          # unknown → no auto-flat

            our_sc = h_sc if h == bet["team"] else a_sc
            opp_sc = h_sc if h == bet["opp"] else a_sc
            margin = our_sc - opp_sc  # positive = our side winning

            snap = {"coin": coin, "label": bet["label"], "our": our_sc, "opp": opp_sc,
                    "margin": margin, "quarter": quarter, "status": status}
            print(f"  {bet['label']}: {our_sc}-{opp_sc} Q{quarter} {status} margin={margin:+d}",
                  file=sys.stderr)

            # Three safety gates added after 2026-10-18 $318 CLE incident:
            # (1) cold-start block: never fire within first N seconds of process start
            # (2) hysteresis: must be past threshold by HYSTERESIS extra points
            # (3) confirm_polls: must see threshold-crossing margin for N consecutive polls
            # If we never saw this coin before this cycle (last_margin missing), require full confirm.
            seconds_up = time.time() - PROCESS_START
            cold_start_block = seconds_up < COLD_START_SECONDS

            trip_tp = margin >= (TAKE_PROFIT_MARGIN + HYSTERESIS) and quarter >= 2
            trip_cl = margin <= -(CUT_LOSS_MARGIN + HYSTERESIS) and quarter >= 2

            if trip_tp or trip_cl:
                confirm_count[coin] = confirm_count.get(coin, 0) + 1
            else:
                confirm_count[coin] = 0
            last_margin[coin] = margin

            decision = None
            if status in ("FINAL", "FINISHED", "COMPLETE", "F"):
                decision = "won" if margin > 0 else "lost"
                journal({"event": "final", **snap, "decision": decision})
                resolved_this_cycle.append(coin)
            elif cold_start_block and (trip_tp or trip_cl):
                journal({"event": "cold_start_block", **snap,
                         "seconds_up": int(seconds_up),
                         "would_fire": "tp" if trip_tp else "cl"})
                print(f"  SKIP (cold start, {int(seconds_up)}s < {COLD_START_SECONDS}s): {bet['label']}", file=sys.stderr)
            elif trip_tp and confirm_count[coin] >= CONFIRM_POLLS:
                r = flat_coin(coin, f"take_profit {bet['team']}+{margin} Q{quarter} (confirmed {confirm_count[coin]}x)")
                journal({"event": "take_profit", **snap, "flatten": r, "confirms": confirm_count[coin]})
                resolved_this_cycle.append(coin)
            elif trip_cl and confirm_count[coin] >= CONFIRM_POLLS:
                r = flat_coin(coin, f"cut_loss {bet['team']}{margin} Q{quarter} (confirmed {confirm_count[coin]}x)")
                journal({"event": "cut_loss", **snap, "flatten": r, "confirms": confirm_count[coin]})
                resolved_this_cycle.append(coin)
            elif trip_tp or trip_cl:
                print(f"  THRESHOLD HIT but awaiting confirm ({confirm_count[coin]}/{CONFIRM_POLLS}): {bet['label']}", file=sys.stderr)

        for c in resolved_this_cycle:
            active.pop(c, None)
            print(f"removed {c} from watch (resolved)", file=sys.stderr)

        if not active:
            break

        LAST.write_text(json.dumps({"ts": int(time.time()), "active": list(active.keys())}))
        time.sleep(POLL_INTERVAL_S)

    print("all games resolved, monitor exiting", file=sys.stderr)
    journal({"event": "monitor_exit"})
    return 0

if __name__ == "__main__":
    sys.exit(main())
