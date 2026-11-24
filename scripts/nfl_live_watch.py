#!/usr/bin/env python3
"""Live-game watcher — polls nfl-com/sports-league-data/game via Alexandria
every 60s for games we have active HB makers on.

Writes score snapshots to state/nfl_live.jsonl and alerts on:
  - score flips (lead change)
  - big delta (>10 points in 2 polls)
  - game end (status != in_progress)

The HB fair-value integration reads nfl_live.jsonl to skew quotes toward
the team currently leading. Standalone script.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
if not API_KEY:
    env = Path.home() / ".config/hyper-trader/firecrawl.env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("FIRECRAWL_API_KEY="):
                API_KEY = line.split("=", 1)[1].strip()
if not API_KEY:
    sys.exit("FIRECRAWL_API_KEY missing")

STATE = Path(__file__).resolve().parent.parent / "state"
STATE.mkdir(parents=True, exist_ok=True)
JSONL = STATE / "nfl_live.jsonl"
LAST = STATE / "nfl_live_last.json"

# Our active HB games mapped to NFL abbreviations (home vs away is in schedule).
# Keep this short — if we add HB on a new game, add it here too.
ACTIVE_GAMES = {
    # Only games with real $ at risk — HB makers run blind on their own.
    "KC vs LAC":  ("KC", "LAC"),   # $150 directional on KC YES
    "NE vs NYJ":  ("NE", "NYJ"),   # $150 directional on NE YES
}


def alex(provider: str, capability: str, options: dict | None = None) -> tuple[dict | None, int]:
    body = json.dumps({"alexandria": {"provider": provider, "capability": capability, "options": options or {}}}).encode()
    req = urllib.request.Request(
        "https://api.firecrawl.dev/v2/scrape",
        data=body,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read())
    except Exception as e:
        print(f"alex {provider}/{capability} err: {e}", file=sys.stderr)
        return None, 0
    alx = d.get("data", {}).get("alexandria", [])
    if not alx:
        return None, 0
    first = alx[0]
    if first.get("error"):
        print(f"alex row err: {first['error']}", file=sys.stderr)
        return None, first.get("creditsCost", 0)
    return first.get("data"), first.get("creditsCost", 0)


def fetch_week_games() -> list[dict]:
    data, _ = alex("nfl-com", "sports-league-data/schedule", {"season": 2026, "week": 6})
    if not data:
        return []
    return data.get("games", []) or []


def find_game_ids(games: list[dict]) -> dict[str, str]:
    """Return {label: game_id} for ACTIVE_GAMES."""
    out = {}
    for label, (a, b) in ACTIVE_GAMES.items():
        for g in games:
            home = (g.get("home_team") or {}).get("abbreviation", "")
            away = (g.get("away_team") or {}).get("abbreviation", "")
            if {home, away} == {a, b}:
                out[label] = g.get("id")
                break
    return out


def poll_game(game_id: str) -> dict | None:
    data, cost = alex("nfl-com", "sports-league-data/game", {"game_id": game_id})
    if data:
        print(f"poll {game_id[:8]} cost={cost}cr", file=sys.stderr)
    return data


def alert(record: dict) -> None:
    record["ts"] = int(time.time())
    with open(JSONL, "a") as f:
        f.write(json.dumps(record) + "\n")
    print(f"ALERT: {record}", file=sys.stderr)


def main() -> int:
    print(f"nfl_live_watch starting, key={API_KEY[:8]}...", file=sys.stderr)
    # One-shot: get game IDs for this week
    games = fetch_week_games()
    gids = find_game_ids(games)
    if not gids:
        print(f"no matching games in schedule (checked {len(games)} games); exiting", file=sys.stderr)
        return 1
    print(f"watching {len(gids)} games: {list(gids.keys())}", file=sys.stderr)

    last_state: dict[str, dict] = {}
    if LAST.exists():
        try:
            last_state = json.loads(LAST.read_text())
        except Exception:
            pass

    while True:
        # Only poll during active game window: Sunday Oct 18 15:00Z - 23:30Z
        import datetime
        now = datetime.datetime.now(datetime.UTC)
        is_sunday_window = (
            now.year == 2026 and now.month == 10 and now.day == 18
            and 15 <= now.hour < 24
        )
        if not is_sunday_window:
            print(f"idle (not Sunday window): {now.isoformat()}", file=sys.stderr)
            time.sleep(1800)  # 30min idle sleep
            continue
        for label, gid in gids.items():
            data = poll_game(gid)
            if not data:
                continue
            away = data.get("away_team", {}) or {}
            home = data.get("home_team", {}) or {}
            snapshot = {
                "label": label,
                "away": away.get("abbreviation"),
                "home": home.get("abbreviation"),
                "away_score": data.get("away_score"),
                "home_score": data.get("home_score"),
                "status": data.get("status") or data.get("game_status"),
                "quarter": data.get("quarter"),
                "clock": data.get("clock"),
            }
            prev = last_state.get(label, {})
            # Alert on any score change
            if (snapshot["away_score"] != prev.get("away_score")
                or snapshot["home_score"] != prev.get("home_score")
                or snapshot["status"] != prev.get("status")):
                alert({**snapshot, "prev": prev})
            last_state[label] = snapshot

        LAST.write_text(json.dumps(last_state))
        time.sleep(300)


if __name__ == "__main__":
    sys.exit(main())
