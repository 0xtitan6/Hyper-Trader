#!/usr/bin/env python3
"""Pre-match pair maker for HIP-4 outcome surfaces.

THE TRADE
---------
Outcome legs are spot-like: you can only BID, never short. So classic two-sided
quoting on one leg is impossible. What IS possible is resting bids on BOTH legs
of a surface. If both fill you own a basket that settles to exactly $1.00, for
less than $1.00. The difference is the edge, it is risk-free once complete, and
HIP-4 charges zero fees (measured on 7 fills including a settlement).

WHY THIS IS NOT THE THING THAT LOST $47
---------------------------------------
Two changes, both measured rather than assumed.

1. NEVER IN PLAY. Measured 2026-09-20 across live surfaces:
        in-play  median paired edge 6.68%  (n=3)
        not live median paired edge 0.17%  (n=6)
   A 39x gap. That 6.68% is not opportunity, it is the market pricing the fact
   that someone watching the match knows the score before the book does. On
   2026-09-19 we rested a bid on Tottenham YES during a live match, Villa scored,
   the leg settled at 0.00: -$47. src/gamestate.py refuses those surfaces.

2. HEDGE ON FILL. A one-sided fill is a directional bet we did not choose. The
   maker crosses immediately for the complementary leg, completing the basket at
   the moment of the fill. Hedging later is EV-neutral — all the value is in the
   immediacy.

We are NOT chasing the LP reward programme. It was measured paying $0 to this
account for a full qualifying epoch on 2026-09-19. Builder code is still attached
(costs nothing, may pay later) but no part of this assumes it.

Realistic expectation, stated honestly: the safe edge is ~0.17% per completed
pair against ~$2,657 of total book depth across all tradeable surfaces. This is
a few dollars, not a rescue. It is run to find out whether the paired-fill rate
is high enough to matter, having measured 0 paired fills in 6 attempts so far.

    ./scripts/run_pair_maker.py --dry-run
    ./scripts/run_pair_maker.py --execute --usd-per-leg 25 --max-pairs 4
"""
from __future__ import annotations

import argparse
import fcntl
import logging
import sys
import time
from pathlib import Path

import eth_account
import requests
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.gamestate import GameState  # noqa: E402
from src.hl_outcome import register_outcome_assets  # noqa: E402

BUILDER = "0xab5dbc057628bc18523c4cdfc0e1e2ebdbecb704"
MASTER = "0xE503186067b1B0Fb973c063054B14c4625434A1a"
ENV = "/home/ec2-user/.config/hyper-trader/copytrader.env"
INFO = "https://api.hyperliquid.xyz/info"
KILL = Path(__file__).resolve().parent.parent / "KILL"
# Only one maker may hold capital-reservation state at a time. The reservation
# is computed from a balance read at start-up, so two concurrent runs each
# believe they can afford a pair and both place a first leg. Measured
# 2026-09-21: a manual run and the 20-minute cron fired at 22:31:23 on the same
# surface; the cron placed its YES leg and then had no capital for the NO,
# leaving 116 shares of YES against 27 of NO. A 4:1 directional bet on England
# that nobody chose — the one-sided shape that cost -$47 on 2026-09-19.
LOCK = Path("/tmp/hip4-pair-requote.lock")
# HIP-4 outcome legs price to 5dp.
#
# WE IMPROVE THE TOUCH BY ONE TICK — we do not sit behind it.
# Sitting one tick BEHIND the best bid was why we took zero fills in five hours
# of quoting on books doing ~340 trades/day. Measured 2026-09-21: our bids sat
# with $384-$795 of other orders ahead of them, including the incumbent maker's
# 1000-share block, so nothing could reach us until that entire queue cleared.
# On one leg we were four levels deep (0.73332 against a 0.73912 touch).
#
# The old comment claimed sitting behind stopped a post-only from crossing.
# That is wrong: a post-only (Alo) order only crosses if it reaches the ASK.
# Resting AT or one tick ABOVE the best bid never crosses and puts us first in
# line, which is the entire point of quoting.
TICK = 0.0005

log = logging.getLogger("pairmaker")


def post(body: dict, tries: int = 8):
    for k in range(tries):
        try:
            r = requests.post(INFO, json=body, timeout=25)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(1.5 * (k + 1))
    return None


def traded_24h(oid: int) -> tuple[float, int]:
    """(USD volume, trade count) across both legs in the last 24h."""
    now = int(time.time() * 1000)
    vol = 0.0
    n = 0
    for side in (0, 1):
        c = post({"type": "candleSnapshot",
                  "req": {"coin": f"#{10 * oid + side}", "interval": "1h",
                          "startTime": now - 24 * 3600 * 1000, "endTime": now}})
        time.sleep(0.05)
        if isinstance(c, list):
            vol += sum(float(x["v"]) for x in c)
            n += sum(int(x["n"]) for x in c)
    return vol, n


def scan(gs: GameState, min_edge: float, min_depth: float,
         min_vol: float, min_trades: int) -> list[dict]:
    """Surfaces worth quoting: two-sided, not in play, buyable below par by at
    least `min_edge` — AND actually traded.

    DEPTH IS NOT FLOW. Measured 2026-09-20: Kosovo, Greece, Serbia and Ireland
    each showed $330-358 of resting depth at a clean 1.15% spread and had
    NEVER TRADED — $0 volume, 0 fills, in 24h and in 7d. A bid resting in one
    of those books earns nothing for as long as it sits there. That deep quote
    is a single market maker posting 1000 shares a side at a fixed 1.15c on
    every market from creation; it is not evidence that anyone wants to trade.

    This is the same mistake three times now (empty books 09-19, frozen index
    binaries 09-20, these 09-20). Ranking on depth finds books nobody uses.
    Requiring flow is what makes a resting bid a trade rather than decoration.
    """
    meta = post({"type": "outcomeMeta"}) or {}
    out = []
    for o in meta.get("outcomes", []):
        desc = o.get("description", "")
        safe, reason = gs.is_safe_to_quote(desc, o.get("name",""))
        if not safe:
            continue
        # Weekend-frozen underlyings. Measured 2026-09-20 (a Sunday): xyz:SP500,
        # xyz:GOLD and xyz:XYZ100 all quoted a UNIFORM 9.80% paired spread across
        # every strike, on underlyings that moved 0.10-0.23% in 12h because US
        # equities and gold were closed. That is a market maker pricing Monday's
        # opening gap, not an inefficiency. Quoting into it is the Tottenham
        # trade with a scheduled catalyst.
        if any(t in desc for t in ("perp:xyz:", "priceBinary", "priceDescription")):
            continue
        oid = o["outcome"]
        legs = {}
        for side in (0, 1):
            b = post({"type": "l2Book", "coin": f"#{10 * oid + side}"})
            time.sleep(0.28)
            lv = (b or {}).get("levels") or []
            if len(lv) < 2 or not lv[0] or not lv[1]:
                legs = None
                break
            bid, ask = float(lv[0][0]["px"]), float(lv[1][0]["px"])
            legs[side] = {"bid": bid, "ask": ask,
                          "depth": float(lv[0][0]["sz"]) * bid}
        if not legs:
            continue
        # Both legs need a real price. A leg at ~0 is a decided outcome; the pair
        # is then just "buy the winner at 1.00", which has no spread to capture.
        if min(legs[0]["bid"], legs[1]["bid"]) < 0.02:
            continue
        edge = 1.0 - (legs[0]["bid"] + legs[1]["bid"])
        depth = min(legs[0]["depth"], legs[1]["depth"])
        if edge < min_edge or depth < min_depth:
            continue
        # A wide pair is only capturable if BOTH bids fill. Bids far below mid
        # essentially never both fill (measured: 91-95% end up one-sided), so a
        # huge "edge" here is a wide illiquid book, not an opportunity.
        mid_sum = ((legs[0]["bid"] + legs[0]["ask"]) / 2
                   + (legs[1]["bid"] + legs[1]["ask"]) / 2)
        if edge > 0.06 or abs(mid_sum - 1.0) > 0.06:
            log.info("skip oid=%s — wide/incoherent book (edge %.1f%%, mids sum %.3f)",
                     oid, edge * 100, mid_sum)
            continue
        vol, ntrades = traded_24h(oid)
        if vol < min_vol or ntrades < min_trades:
            log.info("skip oid=%s — no flow ($%.0f / %d trades in 24h)", oid, vol, ntrades)
            continue
        out.append({"oid": oid, "desc": desc, "edge": edge, "depth": depth,
                    "vol24": vol, "trades24": ntrades,
                    "legs": legs, "reason": reason})
    out.sort(key=lambda s: -s["edge"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--usd-per-leg", type=float, default=25.0,
                    help="ruin-safe band is <=$25/leg (3,000-path sim, 2026-09-19)")
    ap.add_argument("--max-pairs", type=int, default=4,
                    help="<=5 concurrent pairs keeps P(ruin) under 0.4%%")
    ap.add_argument("--min-edge", type=float, default=0.004,
                    help="minimum 1-(bidYes+bidNo); safe books median ~0.0017")
    ap.add_argument("--min-depth", type=float, default=25.0)
    ap.add_argument("--min-vol", type=float, default=500.0,
                    help="minimum 24h traded USD across both legs; depth is NOT flow")
    ap.add_argument("--min-trades", type=int, default=10,
                    help="minimum 24h fill count across both legs")
    ap.add_argument("--execute", action="store_true", help="default is dry-run")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

    if KILL.exists():
        print("KILL present — refusing to quote")
        return 3

    # Held for the life of the process; released when it exits for any reason.
    lock_fd = open(LOCK, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another pair-maker run holds the lock — refusing to quote "
              "(concurrent runs half-enter pairs)")
        return 4

    gs = GameState()
    if not gs.refresh():
        print("score feed unreachable — refusing to quote (fail safe)")
        return 2

    surfaces = scan(gs, args.min_edge, args.min_depth, args.min_vol, args.min_trades)
    print(f"tradeable surfaces (not in play, edge >= {args.min_edge*100:.2f}%, "
          f"depth >= ${args.min_depth:.0f}): {len(surfaces)}")
    for s in surfaces[:10]:
        y, n = s["legs"][0], s["legs"][1]
        print(f"  edge {s['edge']*100:5.2f}%  bids {y['bid']:.4f}+{n['bid']:.4f}"
              f"={y['bid']+n['bid']:.4f}  depth ${s['depth']:5.0f}  vol24 ${s['vol24']:7.0f}"
              f"/{s['trades24']:>3}t  {s['desc'][:34]}")
    if not surfaces:
        print("nothing qualifies right now")
        return 2
    if not args.execute:
        print("\nDRY RUN — nothing submitted. Re-run with --execute.")
        return 0

    meta = post({"type": "meta"})
    spot = post({"type": "spotMeta"})
    key = open(ENV).read().split("HL_PRIVATE_KEY=")[1].split("\n")[0].strip()
    ex = Exchange(eth_account.Account.from_key(key), constants.MAINNET_API_URL,
                  meta=meta, spot_meta=spot, account_address=MASTER)
    info = Info(constants.MAINNET_API_URL, skip_ws=True, meta=meta, spot_meta=spot)
    for t in (info, ex.info):
        register_outcome_assets(t)

    sp = post({"type": "spotClearinghouseState", "user": MASTER}) or {}
    usdc = next((b for b in sp.get("balances", []) if b["coin"] == "USDC"), None)
    free_usdc = [float(usdc["total"]) - float(usdc["hold"]) if usdc else 0.0]
    print(f"free USDC: ${free_usdc[0]:.2f}")

    placed = []
    for s in surfaces[:args.max_pairs]:
        # Re-read the book at SUBMIT time. Measured 2026-09-20: all 8 orders
        # placed from scan-time prices came back oid=None. They were post-only
        # (Alo) sitting AT the best bid, the book moved in the seconds between
        # scan and submit, and HL kills a post-only that would cross rather than
        # filling it. Safe failure, but it placed nothing.
        fresh = {}
        for side in (0, 1):
            b = post({"type": "l2Book", "coin": f"#{10 * s['oid'] + side}"})
            lv = (b or {}).get("levels") or []
            if len(lv) < 2 or not lv[0] or not lv[1]:
                fresh = None
                break
            fresh[side] = {"bid": float(lv[0][0]["px"]), "ask": float(lv[1][0]["px"])}
            time.sleep(0.2)
        if not fresh:
            log.warning("skip oid=%s — book went one-sided between scan and submit", s["oid"])
            continue
        # Re-check the edge survived the move, then join the queue one tick
        # BEHIND the touch so a post-only can never cross.
        edge_now = 1.0 - (fresh[0]["bid"] + fresh[1]["bid"])
        if edge_now < args.min_edge:
            log.info("skip oid=%s — edge decayed %.2f%% -> %.2f%%",
                     s["oid"], s["edge"] * 100, edge_now * 100)
            continue

        # SIZE BY SHARES, NOT BY DOLLARS. A basket redeems $1.00 per matched
        # PAIR of shares, so the hedge is N shares of YES against N shares of
        # NO. Equal dollars per leg buys unequal shares — it always overweights
        # the cheap leg, because cheap means unlikely. Measured 2026-09-21: at
        # $15/leg on a 0.7367/0.2503 book this placed 20 YES against 59 NO. Only
        # 20 shares were hedged; the other 39 were a naked directional bet we
        # did not choose. At 60/40 with $20 a side the same error loses $7 if
        # YES wins and makes $10 if NO wins — a coin flip wearing a hedge's
        # clothes.
        # Price BOTH legs first, then check the edge on what we will really
        # pay. Improving the touch costs one tick a leg; if that eats the edge
        # the surface is not worth quoting and we skip it rather than quietly
        # booking a worse trade than we measured.
        quote = {}
        for side in (0, 1):
            q = round(fresh[side]["bid"] + TICK, 5)
            if q >= fresh[side]["ask"]:
                q = round(fresh[side]["bid"], 5)
            quote[side] = q
        pair_px = quote[0] + quote[1]
        edge_quoted = 1.0 - pair_px
        if edge_quoted < args.min_edge:
            log.info("skip oid=%s — edge %.2f%% after improving the touch (was %.2f%%)",
                     s["oid"], edge_quoted * 100, edge_now * 100)
            continue
        if pair_px <= 0:
            continue
        shares = int(args.usd_per_leg * 2 / pair_px)   # ONE count for both legs
        if shares < 1:
            log.info("skip oid=%s — $%.2f buys less than one full pair at %.4f",
                     s["oid"], args.usd_per_leg * 2, pair_px)
            continue

        # Reserve capital for BOTH legs before placing EITHER. Running out
        # mid-surface leaves a lone resting bid, which is a directional bet we
        # did not choose — the exact shape that cost $47 on 2026-09-19. Better to
        # skip a surface entirely than to half-enter it.
        need = shares * pair_px
        if free_usdc[0] < need:
            log.info("skip oid=%s — $%.2f free, need $%.2f for %d-share pair",
                     s["oid"], free_usdc[0], need, shares)
            continue
        free_usdc[0] -= need

        for side in (0, 1):
            coin = f"#{10 * s['oid'] + side}"
            # Improve the touch to take price priority. Never reach the ask —
            # Alo would reject it, and we would be paying the spread rather
            # than earning it.
            px = quote[side]
            if px <= 0:
                continue
            # HIP-4 outcome legs trade in WHOLE shares. A fractional size is
            # rejected with {"error": "Order has invalid size."} — measured
            # 2026-09-20 after 8 orders silently failed because the code only
            # read statuses[0].resting and never looked at .error.
            sz = float(shares)   # SAME share count on both legs — see above
            try:
                r = ex.order(coin, True, sz, px,
                             order_type={"limit": {"tif": "Alo"}},   # post-only: never take
                             reduce_only=False,
                             builder={"b": BUILDER, "f": 0})
                st = (r.get("response", {}).get("data", {}).get("statuses") or [{}])[0]
                if "error" in st:
                    log.error("REJECTED %s sz=%s px=%s: %s", coin, sz, px, st["error"])
                    continue
                oid_ = (st.get("resting") or {}).get("oid")
                if oid_ is None:
                    log.error("NOT RESTING %s: %s", coin, str(st)[:160])
                    continue
                placed.append((coin, px, sz, oid_))
                log.info("rested %s %.0f @ %.5f oid=%s", coin, sz, px, oid_)
            except Exception as e:  # noqa: BLE001
                log.error("order failed %s: %s", coin, e)
            time.sleep(0.4)

    print(f"\nrested {len(placed)} legs across {min(len(surfaces), args.max_pairs)} surfaces")
    print("NOTE: fills are NOT auto-hedged by this script — MakerConfig.hedge_on_fill")
    print("covers that path in the long-running maker. Check paired-fill rate before scaling.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
