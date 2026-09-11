"""Trade-tape collector — captures taker-side flow (VPIN + volume-imbalance),
the signal both prediction-market papers converge on.

v2 (red-team-hardened): (1) DEDUP by trade id — HL re-sends a recent-trades
snapshot on every (re)subscribe, so without dedup the tape double-counts and
corrupts the dataset. (2) PERIODIC WS REFRESH — the SDK WS can die silently and
not reconnect; we recreate the Info/WS connection every ~10 min (dedup makes the
snapshot overlap harmless). Read-only. Detached, self-expires ~1 week.

Output: research/trade_flow.jsonl  (ts, coin, px, sz, side, time, tid)
"""
import json
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone

REPO = "/home/ec2-user/.openclaw/workspace/hyper-trader"
sys.path.insert(0, REPO)
from dotenv import load_dotenv
load_dotenv(f"{REPO}/.env")
from hyperliquid.info import Info
from hyperliquid.utils import constants
from src.hl_outcome import encode_outcome_coin_name, register_outcome_assets

OUT = f"{REPO}/research/trade_flow.jsonl"
WEEK_END = datetime(2026, 7, 14, 1, 0, tzinfo=timezone.utc)
REFRESH_S = 600  # recreate the WS connection every 10 min (silent-death insurance)

_lock = threading.Lock()
_seen = set()                 # trade ids already written
_seen_order = deque(maxlen=200000)  # bound the dedup memory


def _mark_seen(tid):
    if tid in _seen:
        return False
    _seen.add(tid)
    _seen_order.append(tid)
    if len(_seen_order) == _seen_order.maxlen:
        # deque auto-drops the oldest; keep _seen roughly in sync
        while len(_seen) > _seen_order.maxlen:
            _seen.discard(_seen_order.popleft())
    return True


def makeable(info, top=10):
    resp = info.post("/info", {"type": "outcomeMeta"}) or {}
    out = []
    for o in resp.get("outcomes", []):
        oid = o.get("outcome")
        if not isinstance(oid, int):
            continue
        for side in range(2):
            coin = encode_outcome_coin_name(oid, side)
            try:
                bk = info.post("/info", {"type": "l2Book", "coin": coin}) or {}
                lv = bk.get("levels") or [[], []]
                b, a = lv[0], lv[1]
                if not b or not a:
                    continue
                bb, ba = float(b[0]["px"]), float(a[0]["px"])
                mid = (bb + ba) / 2
                if not (0.05 <= mid <= 0.95):
                    continue
                dep = sum(float(x["sz"]) for x in b[:5]) + sum(float(x["sz"]) for x in a[:5])
                sp = (ba - bb) / mid * 10000
                if dep > 30:
                    out.append((sp * (dep ** 0.5), coin))
            except Exception:
                pass
    out.sort(reverse=True)
    return [c for _, c in out[:top]]


def _handler(coin):
    def h(msg):
        try:
            data = msg.get("data") if isinstance(msg, dict) else None
            trades = data if isinstance(data, list) else (msg if isinstance(msg, list) else [])
            if not isinstance(trades, list):
                return
            ts = datetime.now(timezone.utc).isoformat()
            rows = []
            with _lock:
                for tr in trades:
                    if not isinstance(tr, dict):
                        continue
                    tid = tr.get("tid") or f"{tr.get('coin')}-{tr.get('time')}-{tr.get('px')}-{tr.get('sz')}-{tr.get('side')}"
                    if not _mark_seen(tid):
                        continue  # duplicate (snapshot replay) — skip
                    rows.append({"ts": ts, "coin": tr.get("coin", coin), "px": tr.get("px"),
                                 "sz": tr.get("sz"), "side": tr.get("side"),
                                 "time": tr.get("time"), "tid": tid})
                if rows:
                    with open(OUT, "a") as f:
                        for r in rows:
                            f.write(json.dumps(r) + "\n")
        except Exception:
            pass
    return h


def main():
    while datetime.now(timezone.utc) <= WEEK_END:
        info = None
        try:
            info = Info(constants.MAINNET_API_URL, skip_ws=False)
            register_outcome_assets(info)
            for coin in makeable(info):
                info.subscribe({"type": "trades", "coin": coin}, _handler(coin))
        except Exception:
            time.sleep(30)
            continue
        # run this connection for REFRESH_S, then rebuild a fresh WS (dedup makes the
        # snapshot overlap harmless) — insures against silent WS death.
        deadline = time.time() + REFRESH_S
        while time.time() < deadline and datetime.now(timezone.utc) <= WEEK_END:
            time.sleep(20)
        try:
            if info is not None and getattr(info, "ws_manager", None):
                info.ws_manager.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
