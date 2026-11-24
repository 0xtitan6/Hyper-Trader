#!/usr/bin/env python3
"""NBA news watcher — Firecrawl /scrape ESPN NBA injuries page, parse markdown table.

Every 30min: scrape https://www.espn.com/nba/injuries, diff vs last snapshot.
If a star player flips to Out or Doubtful, append alert to state/nba_news.jsonl.

NBA is star-driven — load management + injuries move lines more than NFL.
Watch list: anyone averaging >20 PPG recent season or on a short list of impact
stars. Non-stars get logged but don't trigger alert.

Hobby plan budget: 1 scrape every 30min = 48 scrapes/day = ~240cr/day
(worst case). Fine for Hobby's ~167cr/day budget during NBA season when NFL
also running — may need Standard tier at $83/mo.
"""
from __future__ import annotations

import json
import os
import re
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
JSONL = OUT_DIR / "nba_news.jsonl"
LAST = OUT_DIR / "nba_news_last.json"

# Players we care about. Start permissive — any NBA star where injury flip
# moves game lines by >3% in model. Grow this list from backtests.
STARS = {
    "Luka Doncic", "Nikola Jokic", "Giannis Antetokounmpo", "Jayson Tatum",
    "Shai Gilgeous-Alexander", "LeBron James", "Stephen Curry", "Kevin Durant",
    "Anthony Davis", "Devin Booker", "Jaylen Brown", "Donovan Mitchell",
    "Damian Lillard", "Trae Young", "De'Aaron Fox", "Zion Williamson",
    "Joel Embiid", "Victor Wembanyama", "Anthony Edwards", "Tyrese Haliburton",
    "Paolo Banchero", "Scottie Barnes", "Jalen Brunson", "Darius Garland",
    "Pascal Siakam", "Lauri Markkanen", "Karl-Anthony Towns", "Jamal Murray",
    "Tyler Herro", "Bam Adebayo", "Ja Morant", "Kawhi Leonard", "Paul George",
    "Jimmy Butler", "DeMar DeRozan", "Zach LaVine", "Franz Wagner",
}

SEVERITY = {"out": 3, "doubtful": 2, "questionable": 1, "probable": 0,
            "day-to-day": 1, "available": 0, "healthy": 0}


def scrape_espn_injuries() -> tuple[str, int]:
    """Returns (markdown, credits_cost)."""
    body = json.dumps({
        "url": "https://www.espn.com/nba/injuries",
        "formats": ["markdown"],
    }).encode()
    req = urllib.request.Request(
        "https://api.firecrawl.dev/v2/scrape",
        data=body,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read())
    except Exception as e:
        print(f"firecrawl err: {e}", file=sys.stderr)
        return "", 0
    data = d.get("data", {})
    return data.get("markdown", ""), data.get("creditsCost", 0)


def parse_injury_table(md: str) -> list[dict]:
    """Parse the per-team injury tables. Returns list of {team, player, pos, status, comment}."""
    rows = []
    # Split on team headers (lines ending with team name after an image)
    # Pattern: team header is image markdown then team name on same line.
    sections = re.split(r"!\[\]\(<Base64-Image-Removed>\)([A-Z][a-zA-Z ']+?)(?=\n)", md)
    # sections = [preamble, team1, body1, team2, body2, ...]
    for i in range(1, len(sections) - 1, 2):
        team = sections[i].strip()
        body = sections[i + 1]
        # Each row: | [Player Name](url) | POS | DATE | STATUS | COMMENT |
        for m in re.finditer(
            r"\|\s*\[([^\]]+)\]\([^)]*\)\s*\|\s*([A-Z/]+)\s*\|\s*[^|]*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|",
            body,
        ):
            name, pos, status, comment = m.groups()
            rows.append({
                "team": team,
                "player": name.strip(),
                "position": pos.strip(),
                "status": status.strip().lower(),
                "comment": comment.strip()[:200],
            })
    return rows


def alert(record: dict) -> None:
    record["ts"] = int(time.time())
    with open(JSONL, "a") as f:
        f.write(json.dumps(record) + "\n")
    print(f"ALERT: {record}", file=sys.stderr)


def main() -> int:
    print(f"nba_news_watch starting, key={API_KEY[:8]}...", file=sys.stderr)
    last_state: dict[str, str] = {}
    if LAST.exists():
        try:
            last_state = json.loads(LAST.read_text())
        except Exception:
            pass

    total_cost = 0
    cycles = 0
    while True:
        md, cost = scrape_espn_injuries()
        if md:
            total_cost += cost
            cycles += 1
            current = parse_injury_table(md)
            print(f"scrape #{cycles}: {len(current)} injury rows, cost={cost}cr (total {total_cost})",
                  file=sys.stderr)

            current_map = {f"{r['team']}:{r['player']}": r["status"] for r in current}
            for key, status in current_map.items():
                prev = last_state.get(key, "healthy")
                new_sev = SEVERITY.get(status, 0)
                old_sev = SEVERITY.get(prev, 0)
                if new_sev > old_sev and new_sev >= 2:
                    team, player = key.split(":", 1)
                    is_star = player in STARS
                    row = next((r for r in current if r["player"] == player), {})
                    rec = {
                        "team": team,
                        "player": player,
                        "position": row.get("position", ""),
                        "status": status,
                        "prev_status": prev,
                        "comment": row.get("comment", ""),
                        "is_star": is_star,
                        "source": "firecrawl/espn/nba-injuries",
                    }
                    if is_star:
                        alert(rec)
                    else:
                        # Still log, but silent (no stderr spam)
                        rec["ts"] = int(time.time())
                        with open(JSONL, "a") as f:
                            f.write(json.dumps(rec) + "\n")

            last_state = current_map
            LAST.write_text(json.dumps(last_state))

        time.sleep(1800)  # 30 min


if __name__ == "__main__":
    sys.exit(main())
