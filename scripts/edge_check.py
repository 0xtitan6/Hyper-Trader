#!/usr/bin/env python3
"""Pre-bet edge checker — compare HL vs Kalshi for the game.

Usage:
    python edge_check.py <team_abbr>
Example:
    python edge_check.py NE

Reports:
  HL moneyline mid (perp spot both sides)
  Kalshi moneyline mid (both sides, with depth)
  Edge (Kalshi - HL)
  Injury flags from state/nfl_news.jsonl for both teams
  Pre-bet verdict: BET YES / BET NO / PASS

Call this BEFORE any new NFL bet. Rule: only ship when |edge| > 5pp AND
Kalshi $-depth > $500k AND no star injury against our side.
"""
from __future__ import annotations
import json, sys, re, time
from pathlib import Path
import urllib.request

STATE = Path(__file__).resolve().parent.parent / "state"
KALSHI_DIR = STATE / "kalshi"
NFL_NEWS = STATE / "nfl_news.jsonl"

STAR_WATCH = {
    'Josh Allen','Patrick Mahomes','Jalen Hurts','Lamar Jackson','Dak Prescott',
    'Joe Burrow','Justin Herbert','Saquon Barkley','Christian McCaffrey',
    "Ja'Marr Chase",'Tyreek Hill','CeeDee Lamb','Travis Kelce','Nick Chubb',
    'Jalen Carter','Myles Garrett','Micah Parsons','Aaron Donald',
    'Trevon Diggs','Jalen Ramsey','Minkah Fitzpatrick',
}

def most_recent_kalshi_mid(team: str) -> list[dict]:
    files = sorted(KALSHI_DIR.glob("markets_*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not files: return []
    last = files[-1]
    out = []
    for line in last.read_text().splitlines():
        try:
            d = json.loads(line)
        except Exception: continue
        tkr = d.get("market_ticker","")
        title = d.get("market_title","")
        if team.upper() in tkr.split("-")[-1] or team in title:
            out.append(d)
    return out

def hl_mids_for_team(team: str, mids: dict, meta: dict) -> list[dict]:
    found = []
    for o in meta.get('outcomes', []):
        if 'sportsContestWinner' not in o.get('name',''): continue
        d = str(o.get('description',''))
        if 'NFL' not in d: continue
        tm = re.search(r'participantA:([^|]+).*?participantB:([^|]+)', d)
        if not tm: continue
        pa, pb = tm.group(1).strip(), tm.group(2).strip()
        team_full = {
            'NE':'New England Patriots','KC':'Kansas City Chiefs','CLE':'Cleveland Browns',
            'BAL':'Baltimore Ravens','NYG':'New York Giants','NO':'New Orleans Saints',
            'DAL':'Dallas Cowboys','PHI':'Philadelphia Eagles','PIT':'Pittsburgh Steelers',
            'TB':'Tampa Bay Buccaneers','HOU':'Houston Texans','JAX':'Jacksonville Jaguars',
            'BUF':'Buffalo Bills','LV':'Las Vegas Raiders','CHI':'Chicago Bears',
            'ATL':'Atlanta Falcons','NYJ':'New York Jets','TEN':'Tennessee Titans',
            'IND':'Indianapolis Colts','CAR':'Carolina Panthers','SEA':'Seattle Seahawks',
            'DEN':'Denver Broncos','AZ':'Arizona Cardinals','LAR':'Los Angeles Rams',
            'LAC':'Los Angeles Chargers','SF':'San Francisco 49ers','WAS':'Washington Commanders',
            'GB':'Green Bay Packers','MIA':'Miami Dolphins','DET':'Detroit Lions',
            'MIN':'Minnesota Vikings','CIN':'Cincinnati Bengals',
        }.get(team)
        if team_full and (pa == team_full or pb == team_full):
            yes_key = f"#{o['outcome']}0"
            if yes_key in mids:
                found.append({
                    'oid': o['outcome'],
                    'pa': pa, 'pb': pb,
                    'our_side': 'YES' if pa == team_full else 'NO',
                    'yes_px': float(mids[yes_key]),
                    'desc': d[:100],
                })
    return found

def recent_injuries(team: str) -> list[dict]:
    if not NFL_NEWS.exists(): return []
    cutoff = int(time.time()) - 86400 * 3
    out = []
    for line in NFL_NEWS.read_text().splitlines():
        try: r = json.loads(line)
        except: continue
        if r.get("ts", 0) < cutoff: continue
        tm = r.get("team","")
        if team.upper() in tm.upper() or team in tm:
            if r.get("is_star") or r.get("player","") in STAR_WATCH:
                out.append(r)
    return out[-5:]

def main() -> int:
    if len(sys.argv) < 2:
        sys.exit("usage: edge_check.py <team_abbr>")
    team = sys.argv[1].upper()
    print(f"=== EDGE CHECK: {team} ===\n")

    # HL
    mids = json.loads(urllib.request.urlopen(urllib.request.Request('https://api.hyperliquid.xyz/info',
        method='POST', data=json.dumps({'type':'allMids'}).encode(),
        headers={'Content-Type':'application/json'}), timeout=10).read())
    meta = json.loads(urllib.request.urlopen(urllib.request.Request('https://api.hyperliquid.xyz/info',
        method='POST', data=json.dumps({'type':'outcomeMeta'}).encode(),
        headers={'Content-Type':'application/json'}), timeout=10).read())
    hl = hl_mids_for_team(team, mids, meta)
    print(f"HL markets: {len(hl)}")
    for h in hl:
        px_for_team = h['yes_px'] if h['our_side'] == 'YES' else 1 - h['yes_px']
        print(f"  #{h['oid']} ({h['our_side']}): {team} price = {px_for_team:.4f}  ({h['pa'][:15]} vs {h['pb'][:15]})")

    # Kalshi
    ks = most_recent_kalshi_mid(team)
    print(f"\nKalshi markets: {len(ks)}")
    for k in ks:
        print(f"  {k['market_ticker']}: mid={k['mid']:.4f} bid={k['yes_bid']} ask={k['yes_ask']} depth=${k.get('yes_bid_depth_usd',0):,.0f}/{k.get('yes_ask_depth_usd',0):,.0f}")

    # Compute edge
    if hl and ks:
        hl_price = hl[0]['yes_px'] if hl[0]['our_side'] == 'YES' else 1 - hl[0]['yes_px']
        # Find matching Kalshi market where team is the "YES" (winning side)
        k_price = None
        for k in ks:
            if team.upper() in k['market_ticker'].split("-")[-1]:
                k_price = k['mid']
                depth = min(k.get('yes_bid_depth_usd',0), k.get('yes_ask_depth_usd',0))
                break
        if k_price is not None:
            edge = (k_price - hl_price) * 100
            print(f"\n=== EDGE: {edge:+.2f}pp ({'BUY HL' if edge > 0 else 'SELL HL / BUY NO on HL'}) ===")
            print(f"  HL price: {hl_price:.4f}  Kalshi price: {k_price:.4f}  Kalshi depth: ${depth:,.0f}")
            # Verdict
            injuries = recent_injuries(team)
            print(f"\nStar injuries for {team} last 3d: {len(injuries)}")
            for i in injuries:
                print(f"  {i.get('player')} ({i.get('status')}): {i.get('comment','')[:80]}")
            if abs(edge) < 5:
                verdict = "PASS — edge too small"
            elif depth < 500000:
                verdict = "PASS — Kalshi depth too thin, mid unreliable"
            elif injuries and edge > 0:
                verdict = f"PASS — star injury flagged against our side"
            else:
                verdict = f"BET: {'YES' if edge > 0 else 'NO'} on HL at ${75} (edge {edge:+.1f}pp)"
            print(f"\n*** VERDICT: {verdict} ***")

if __name__ == "__main__":
    sys.exit(main() or 0)
