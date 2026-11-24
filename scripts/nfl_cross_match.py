"""Cross-match HL NFL outcome coins vs Kalshi NFL orderbook mids.

Reads HL meta + live allMids + latest Kalshi snapshot, prints a per-coin
divergence table. Read-only, safe to run anytime.

Fix over the notebook version: keys by (coin_id, yes_team) so duplicate HL
listings of the same game (two data sources register both #4655 and #4814
for Ravens vs Cowboys) don't collide via `sorted((A,B))`.

Run:
    .venv-ml/bin/python scripts/nfl_cross_match.py
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

HL_META = Path("analysis/hl_outcome_meta_full.json")
KALSHI_DIR = Path("state/kalshi")

# Kalshi 3-letter team code → HL long name
KALSHI_TEAM = {
    "ATL": "Atlanta Falcons", "GB": "Green Bay Packers",
    "WAS": "Washington Commanders", "SEA": "Seattle Seahawks",
    "CLE": "Cleveland Browns", "CAR": "Carolina Panthers",
    "NYG": "New York Giants", "TEN": "Tennessee Titans",
    "BUF": "Buffalo Bills", "LAC": "Los Angeles Chargers",
    "MIA": "Miami Dolphins", "KC": "Kansas City Chiefs",
    "DET": "Detroit Lions", "NYJ": "New York Jets",
    "PIT": "Pittsburgh Steelers", "CIN": "Cincinnati Bengals",
    "IND": "Indianapolis Colts", "HOU": "Houston Texans",
    "JAC": "Jacksonville Jaguars", "NE": "New England Patriots",
    "SF": "San Francisco 49ers", "ARI": "Arizona Cardinals",
    "TB": "Tampa Bay Buccaneers", "MIN": "Minnesota Vikings",
    "LV": "Las Vegas Raiders", "NO": "New Orleans Saints",
    "BAL": "Baltimore Ravens", "DAL": "Dallas Cowboys",
    "LAR": "Los Angeles Rams", "DEN": "Denver Broncos",
    "PHI": "Philadelphia Eagles", "CHI": "Chicago Bears",
}


def _get(url: str, body: dict | None = None) -> dict:
    if body is None:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    else:
        req = urllib.request.Request(
            url, data=json.dumps(body).encode(),
            headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def load_hl_nfl_coins() -> list[dict]:
    """Return list of {coin_id, hl_key, yes_team, opponent, matchup, scheduled_start, source}.

    NOTE: same game can appear under multiple outcome_ids from different data
    sources (ESPN vs NFL official). We list ALL of them — don't collapse.
    """
    meta = json.load(open(HL_META))
    out = []
    for e in meta.get("outcomes", []):
        d = e.get("description", "") or ""
        if e.get("name") != "template:sportsContestWinner":
            continue
        if "competition:NFL" not in d:
            continue
        parts = {kv.split(":", 1)[0]: kv.split(":", 1)[1]
                 for kv in d.split("|") if ":" in kv}
        A, B = parts.get("participantA"), parts.get("participantB")
        if not A or not B:
            continue
        sides = e.get("sideSpecs", [])
        yes_name = sides[0].get("name", "") if sides else ""
        if "shortNameA" in yes_name:
            yes_team, opp = A, B
        elif "shortNameB" in yes_name:
            yes_team, opp = B, A
        else:
            continue
        out.append({
            "coin_id": e.get("outcome"),
            "hl_key": f'#{e.get("outcome")}0',  # side 0 = YES
            "yes_team": yes_team,
            "opponent": opp,
            "matchup": tuple(sorted([A, B])),
            "scheduled_start": parts.get("scheduledStart", ""),
            "source": parts.get("officialSource", "?"),
        })
    return out


def load_kalshi_latest() -> dict:
    """Return {(matchup_tuple, team_name): kalshi_mid}."""
    paths = sorted(KALSHI_DIR.glob("markets_*.jsonl"))
    if not paths:
        return {}
    kg = {}
    for line in open(paths[-1]):
        r = json.loads(line)
        tk = r["market_ticker"].split("-")
        if len(tk) < 3:
            continue
        game, team = tk[1], tk[2]
        matchup_str = game[7:]
        if team not in matchup_str:
            continue
        other = matchup_str.replace(team, "", 1)
        tf, of = KALSHI_TEAM.get(team), KALSHI_TEAM.get(other)
        if not tf or not of:
            continue
        key = (tuple(sorted([tf, of])), tf)
        kg[key] = {
            "mid": r["mid"],
            "yes_bid": r["yes_bid"],
            "yes_ask": r["yes_ask"],
            "depth_usd": r["yes_bid_depth_usd"],
        }
    return kg


def main() -> int:
    hl_mids = _get("https://api.hyperliquid.xyz/info", {"type": "allMids"})
    hl_coins = load_hl_nfl_coins()
    kalshi = load_kalshi_latest()

    print(f"HL NFL coins: {len(hl_coins)}   Kalshi markets loaded: {len(kalshi)}\n")
    print(f'{"HL_coin":>8} {"YES side":24} {"HL":>7} {"K":>7} {"gap_bps":>8} {"K_depth":>10} {"src":>6}')
    print("-" * 100)
    edges = []
    for c in sorted(hl_coins, key=lambda x: x["matchup"]):
        k_key = (c["matchup"], c["yes_team"])
        k = kalshi.get(k_key)
        if not k:
            continue
        km = k["mid"]
        raw = hl_mids.get(c["hl_key"])
        try:
            hm = float(raw) if raw else None
        except (TypeError, ValueError):
            hm = None
        if hm is None or km is None:
            continue
        gap = (hm - km) * 10000
        src_tag = c["source"].split(" ")[0][:6]
        print(f'{c["coin_id"]:>8} {c["yes_team"][:24]:24} {hm:>7.4f} {km:>7.3f} {gap:>+8.0f} '
              f'{k["depth_usd"]:>10,.0f} {src_tag:>6}')
        if abs(gap) > 100:
            edges.append((c, hm, km, gap, k["depth_usd"]))

    print(f"\n=== edges (|gap| > 100 bps) ===")
    for c, hm, km, gap, depth in sorted(edges, key=lambda x: -abs(x[3])):
        print(f"  #{c['coin_id']} {c['yes_team']} ({c['scheduled_start']}, src={c['source'][:20]})")
        print(f"      HL={hm:.4f} K={km:.4f} gap={gap:+.0f}bps K_depth=${depth:,.0f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
