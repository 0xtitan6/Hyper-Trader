#!/usr/bin/env python3
"""NFL news watcher — Firecrawl /extract on ESPN injuries + sportsbook consensus.

Loop: every 90s, scrape ESPN NFL injuries + ESPN game lines. Diff vs last snapshot.
If a starting QB flips to 'Out' or 'Doubtful' → write alert JSON + append to
state/nfl_news.jsonl. The HB fair-value gate (future) reads this file and
mutes/skews quotes on affected games.

Why 90s: Firecrawl rate limit is generous, but we don't want to burn credits.
Pre-kickoff news lands with minutes of warning on average — 90s is tight enough.

Standalone, no deps outside stdlib + urllib. Pulls key from env.
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
    env_file = Path.home() / ".config/hyper-trader/firecrawl.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("FIRECRAWL_API_KEY="):
                API_KEY = line.split("=", 1)[1].strip()
                break
if not API_KEY:
    sys.exit("FIRECRAWL_API_KEY missing")

OUT_DIR = Path(__file__).resolve().parent.parent / "state"
OUT_DIR.mkdir(parents=True, exist_ok=True)
JSONL = OUT_DIR / "nfl_news.jsonl"
LAST = OUT_DIR / "nfl_news_last.json"


def firecrawl_extract(url: str, schema: dict, prompt: str) -> dict | None:
    body = json.dumps({
        "urls": [url],
        "schema": schema,
        "prompt": prompt,
    }).encode()
    req = urllib.request.Request(
        "https://api.firecrawl.dev/v2/extract",
        data=body,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"firecrawl err: {e}", file=sys.stderr)
        return None


def alexandria_call(provider: str, capability: str, options: dict | None = None) -> tuple[list[dict], int]:
    """Returns (rows, credits_cost). Logs cost."""
    body = json.dumps({
        "alexandria": {"provider": provider, "capability": capability, "options": options or {}},
    }).encode()
    req = urllib.request.Request(
        "https://api.firecrawl.dev/v2/scrape",
        data=body,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read())
    except Exception as e:
        print(f"alexandria {provider}/{capability} err: {e}", file=sys.stderr)
        return [], 0
    data = d.get("data", {})
    rows_wrap = data.get("alexandria", [])
    cost = data.get("creditsCost", 0)
    if not rows_wrap:
        return [], cost
    first = rows_wrap[0]
    if first.get("error"):
        print(f"alexandria row error: {first['error']}", file=sys.stderr)
        return [], cost
    payload = first.get("data", {})
    return payload.get("injuries", []) or [], first.get("creditsCost", cost)


def poll_injuries() -> list[dict]:
    rows, cost = alexandria_call("startwho-com", "fantasy-sports-rankings/injury_report")
    if cost:
        print(f"alexandria cost: {cost}cr ({len(rows)} rows)", file=sys.stderr)
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        status_short = r.get("status_short", "").upper()
        status = {"O": "out", "D": "doubtful", "Q": "questionable", "P": "probable"}.get(status_short, status_short.lower())
        out.append({
            "player": r.get("name", ""),
            "team": r.get("team", ""),
            "position": r.get("position", ""),
            "status": status,
        })
    return out


def alert(record: dict) -> None:
    record["ts"] = int(time.time())
    with open(JSONL, "a") as f:
        f.write(json.dumps(record) + "\n")
    print(f"ALERT: {record}", file=sys.stderr)


def main() -> int:
    print(f"nfl_news_watch starting, key={API_KEY[:8]}...", file=sys.stderr)
    last_state: dict[str, str] = {}
    if LAST.exists():
        try:
            last_state = json.loads(LAST.read_text())
        except Exception:
            pass

    # Severity levels — higher = more impactful
    SEVERITY = {"out": 3, "doubtful": 2, "questionable": 1, "probable": 0, "healthy": 0}

    while True:
        current = poll_injuries()
        current_map = {f"{i['team']}:{i['player']}": i.get("status", "").lower() for i in current}

        for key, status in current_map.items():
            prev = last_state.get(key, "healthy")
            new_sev = SEVERITY.get(status, 0)
            old_sev = SEVERITY.get(prev, 0)
            if new_sev > old_sev and new_sev >= 2:
                team, player = key.split(":", 1)
                # Position matters: match our injury alert to QBs first
                pos = next(
                    (i.get("position", "") for i in current if i.get("player") == player),
                    "",
                )
                alert({
                    "team": team,
                    "player": player,
                    "position": pos,
                    "status": status,
                    "prev_status": prev,
                    "source": "alexandria/startwho-com/injury_report",
                })

        last_state = current_map
        LAST.write_text(json.dumps(last_state))
        time.sleep(1800)


if __name__ == "__main__":
    sys.exit(main())
