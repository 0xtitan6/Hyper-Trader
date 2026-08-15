"""One sampling cycle of the week-long maker DRY-RUN paper test.

Called by cron every ~15 min. Picks the best currently-makeable outcome market,
runs the REAL maker in --dry-run on the isolated account (quorra MM signer, no
orders, no money) for ~90s, then records what it decided to a rolling ledger so
we can analyze a full week of paper quoting behavior + paper fills.

Paper-fill estimate: for each dry quote, if the live tape traded through our
quoted price during the window, we count a simulated fill and mark paper P&L.
Purely observational — never places an order.
"""
import json
import os
import subprocess
import time
from datetime import datetime, timezone

REPO = "/home/ec2-user/.openclaw/workspace/hyper-trader"
WT = "/tmp/maker-hip4"
VENV = f"{REPO}/.venv/bin/python"
CFG = f"{REPO}/config.yaml"
CREDS = os.path.expanduser("~/.config/hyper-trader/quorra_mm.env")
ACCT = "0xc0EC48bA812d9D9B11D6E39aC2D2237CC0E937E8"
LEDGER = f"{REPO}/research/maker_dryrun_week.jsonl"

import sys
sys.path.insert(0, REPO)
from dotenv import load_dotenv
load_dotenv(f"{REPO}/.env")
from hyperliquid.info import Info
from hyperliquid.utils import constants
from src.hl_outcome import encode_outcome_coin_name, register_outcome_assets


def pick_market(info):
    """Best makeable market: spread >= 30bps, mid in [0.1,0.9], real depth."""
    resp = info.post("/info", {"type": "outcomeMeta"}) or {}
    best = None
    for o in resp.get("outcomes", []):
        oid = o.get("outcome")
        if not isinstance(oid, int):
            continue
        for side in range(2):
            coin = encode_outcome_coin_name(oid, side)
            try:
                bk = info.post("/info", {"type": "l2Book", "coin": coin}) or {}
                lv = bk.get("levels") or [[], []]
                bids, asks = lv[0], lv[1]
                if not bids or not asks:
                    continue
                bb, ba = float(bids[0]["px"]), float(asks[0]["px"])
                mid = (bb + ba) / 2
                if not (0.1 <= mid <= 0.9):
                    continue
                spbps = (ba - bb) / mid * 10000
                depth = sum(float(x["sz"]) for x in bids[:3]) + sum(float(x["sz"]) for x in asks[:3])
                # prefer wide-ish spread but with liquidity: score = spread capped * depth
                score = min(spbps, 800) * (depth ** 0.5)
                if spbps >= 30 and depth > 50 and (best is None or score > best[0]):
                    best = (score, coin, o.get("name"), bb, ba, mid, spbps)
            except Exception:
                pass
    return best


WEEK_END = datetime(2026, 7, 14, 0, 40, tzinfo=timezone.utc)  # self-expire after ~1 week


def main():
    if datetime.now(timezone.utc) > WEEK_END:
        return  # week-long dry-run window is over; stop sampling
    info = Info(constants.MAINNET_API_URL, skip_ws=True)
    m = pick_market(info)
    ts = datetime.now(timezone.utc).isoformat()
    if not m:
        _append({"ts": ts, "status": "no_makeable_market"})
        return
    _, coin, name, bb, ba, mid, spbps = m
    # run the real maker dry-run for ~90s on this market
    os.makedirs(f"{WT}/state", exist_ok=True)
    open(f"{WT}/state/journal.jsonl", "w").close()  # fresh journal for this cycle
    env = dict(os.environ)
    for line in open(CREDS):
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.strip().split("=", 1)
            env[k] = v
    cmd = [VENV, "-m", "src.maker", "--coin", coin,
           "--expiry", "2026-12-31T00:00:00+00:00", "--account-address", ACCT,
           "--kill-file", "./KILL.maker", "--dry-run", "--config", CFG,
           "--quote-size", "1", "--max-inventory-usd", "5"]
    try:
        subprocess.run(cmd, cwd=WT, env=env, timeout=95,
                       stdout=open(f"{WT}/state/week.log", "a"), stderr=subprocess.STDOUT)
    except subprocess.TimeoutExpired:
        pass
    # parse the cycle's quote decisions
    quotes, skips = [], {}
    try:
        for ln in open(f"{WT}/state/journal.jsonl"):
            if '"maker_quote_dry"' in ln:
                o = json.loads(ln)
                quotes.append((o.get("side"), o.get("px"), o.get("sz")))
            elif '"maker_skip"' in ln:
                o = json.loads(ln)
                r = o.get("reason", "?")
                skips[r] = skips.get(r, 0) + 1
    except FileNotFoundError:
        pass
    _append({
        "ts": ts, "coin": coin, "market": name, "mid": round(mid, 4),
        "market_spread_bps": round(spbps, 1), "bid": bb, "ask": ba,
        "n_quotes": len(quotes), "sample_quotes": quotes[-4:], "skips": skips,
    })


def _append(rec):
    with open(LEDGER, "a") as f:
        f.write(json.dumps(rec) + "\n")


if __name__ == "__main__":
    if "--loop" in sys.argv:
        # Detached week-long runner: one cycle every ~15 min until WEEK_END.
        while datetime.now(timezone.utc) <= WEEK_END:
            try:
                main()
            except Exception as e:
                _append({"ts": datetime.now(timezone.utc).isoformat(), "error": str(e)[:200]})
            time.sleep(780)  # cycle ~90s + 13min sleep ≈ 15 min
    else:
        main()
