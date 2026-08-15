"""New-market monitor — alerts Neil the moment a fresh, makeable outcome market
lists on HL (the prime pre-game making window before liquidity floods in).

Baselines the currently-listed markets on first run (no alert spam), then every
~3 min diffs outcomeMeta for NEW outcome ids. For each genuinely new market it
pulls the book and, if it's a real makeable window (interior price 0.1-0.9,
two-sided book, spread >= 30bps), sends a Telegram alert via the bot's own
ALERT_WEBHOOK_URL + TELEGRAM_CHAT_ID (same channel as the mirror watchdog).

Read-only. Detached, runs indefinitely (no self-expiry — it's an ongoing watch).
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

REPO = "/home/ec2-user/.openclaw/workspace/hyper-trader"
sys.path.insert(0, REPO)
from dotenv import load_dotenv
load_dotenv(f"{REPO}/.env")
from hyperliquid.info import Info
from hyperliquid.utils import constants
from src.hl_outcome import encode_outcome_coin_name, register_outcome_assets

KNOWN = f"{REPO}/research/known_markets.json"
LOG = f"{REPO}/research/new_markets.jsonl"
WEBHOOK = os.environ.get("ALERT_WEBHOOK_URL", "")
CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
INTERVAL = 30


def tg(text):
    if not WEBHOOK or not CHAT:
        return
    try:
        body = urllib.parse.urlencode({"chat_id": CHAT, "text": text}).encode()
        urllib.request.urlopen(urllib.request.Request(
            WEBHOOK, data=body, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"}), timeout=10)
    except Exception:
        pass


def load_known():
    try:
        return set(json.load(open(KNOWN)))
    except Exception:
        return None


def save_known(s):
    json.dump(sorted(s), open(KNOWN, "w"))


def book(info, coin):
    try:
        bk = info.post("/info", {"type": "l2Book", "coin": coin}) or {}
        lv = bk.get("levels") or [[], []]
        b, a = lv[0], lv[1]
        if not b or not a:
            return None
        bb, ba = float(b[0]["px"]), float(a[0]["px"])
        mid = (bb + ba) / 2
        dep = sum(float(x["sz"]) for x in b[:5]) + sum(float(x["sz"]) for x in a[:5])
        return bb, ba, mid, (ba - bb) / mid * 10000 if mid else 0, dep
    except Exception:
        return None


def main():
    info = Info(constants.MAINNET_API_URL, skip_ws=True)
    register_outcome_assets(info)
    known = load_known()
    first_run = known is None
    if first_run:
        known = set()
    while True:
        try:
            resp = info.post("/info", {"type": "outcomeMeta"}) or {}
            current = {}
            for o in resp.get("outcomes", []):
                oid = o.get("outcome")
                if isinstance(oid, int):
                    current[oid] = o.get("name") or f"#{oid}"
            new_ids = [oid for oid in current if oid not in known]
            if first_run:
                # baseline only — record everything, alert nothing
                known = set(current)
                save_known(known)
                first_run = False
                tg(f"🆕 new-market monitor armed — baselined {len(known)} markets, watching for fresh listings.")
            else:
                for oid in new_ids:
                    name = current[oid]
                    # check both sides for a makeable window
                    best = None
                    for side in range(2):
                        r = book(info, encode_outcome_coin_name(oid, side))
                        if r and 0.1 <= r[2] <= 0.9 and r[3] >= 30 and r[4] > 20:
                            if best is None or r[3] > best[3]:
                                best = r
                    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                           "outcome": oid, "name": name, "makeable": best is not None}
                    with open(LOG, "a") as f:
                        f.write(json.dumps(rec) + "\n")
                    if best:
                        bb, ba, mid, sp, dep = best
                        tg(f"🎯 NEW makeable market: {name}\n  mid {mid:.3f} | spread {sp:.0f}bps | depth ~{dep:.0f} sh\n  (fresh listing — prime pre-game making window)")
                known |= set(new_ids)
                if new_ids:
                    save_known(known)
        except Exception:
            pass
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
