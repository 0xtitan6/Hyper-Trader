#!/usr/bin/env python3
"""One-leg passive round-trip maker for HIP-4 outcome markets.

THE TRADE, AND WHY IT IS DIFFERENT FROM WHAT WE RAN
---------------------------------------------------
Measured 2026-09-21 across 42,251 public fills, YES and NO are ONE book: every
trade prints on both legs at prices summing to exactly 1.000000 (n=807 matched
prints, min = max = mean), and `askNO == 1 - bidYES` on 142/142 live legs.

So "resting bids on both legs" was never a paired trade — a NO bid at bidN+tick
IS an offer on YES at askY-tick. We were market making one instrument while
modelling it as basket assembly, and it cost us three ways:

  1. "Hedging" a one-sided fill is not a hedge, it is crossing to flatten, and
     it costs one tick BY CONSTRUCTION:
         (bidY+tick) + askN - 1 = (bidY+tick) + (1-bidY) - 1 = tick
     verified on 142/142 legs with zero dispersion.
  2. Holding to settlement is the EXPENSIVE exit at 13.27 bps of face. Selling
     the leg back as a maker costs 7.83 bps of notional = ~3.9 bps of face at
     px 0.50 — 3.4x cheaper.
  3. Entry is free. Buys are billed 0.00 bps whether maker or taker; only sells
     and settlement are charged. Our -0.80% on Giants/Croatia was NOT fees, it
     was 6 minutes of drift between the fill and the hedge (105.6 and 21.2 bps).

Eight peer wallets running our old policy lost -5.31 bps of notional over
17,057 fills; 1 of 8 was profitable, and their entire loss is the fee on the
taking half.

WHAT THIS DOES INSTEAD
----------------------
Quote ONE leg at the front of the book. When it fills, immediately post the
SAME leg back at ask-tick. Never cross. Never settle. Both sides are maker, so
the round trip earns the spread and pays only the sell-side fee.

    both-sides-passive, settle     +19.5 - 13.27 = +6.2 bps
    cross to complete, settle      -18.3 bps          <- what we ran
    passive round-trip, never settle  +15.6 bps best / +3.8 realistic

Breakeven passive share for the old config was 74.7%. We ran ~50%. That is why
it lost, and maker share is the number this script exists to move.

INVENTORY IS A REAL POSITION. While we hold a leg we are directionally exposed
— there is no complement protecting us. Bounded by MAX_INVENTORY_USD per
surface, and everything is flattened before kickoff, because an unsold leg at
the whistle becomes the -$47 Tottenham trade.

    ./scripts/run_roundtrip_maker.py                 # dry run
    ./scripts/run_roundtrip_maker.py --execute
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
from hyperliquid.utils import constants

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.gamestate import KICKOFF_BUFFER_H, GameState  # noqa: E402
from src.hl_outcome import register_outcome_assets  # noqa: E402

BUILDER = "0xab5dbc057628bc18523c4cdfc0e1e2ebdbecb704"
MASTER = "0xE503186067b1B0Fb973c063054B14c4625434A1a"
ENV = "/home/ec2-user/.config/hyper-trader/copytrader.env"
INFO = "https://api.hyperliquid.xyz/info"
KILL = ROOT / "KILL"
LOCK = Path("/tmp/hip4-roundtrip.lock")
LEDGER = ROOT / "state" / "roundtrip.jsonl"

TICK = 0.0005
# A leg priced near 0 or 1 has almost no spread in face terms and settles
# asymmetrically; stay in the middle where the spread is real.
MIN_PX, MAX_PX = 0.05, 0.95

log = logging.getLogger("roundtrip")


def post(body: dict, tries: int = 6):
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
    now = int(time.time() * 1000)
    vol, n = 0.0, 0
    for side in (0, 1):
        c = post({"type": "candleSnapshot",
                  "req": {"coin": f"#{10 * oid + side}", "interval": "1h",
                          "startTime": now - 24 * 3600 * 1000, "endTime": now}})
        time.sleep(0.05)
        if isinstance(c, list):
            vol += sum(float(x["v"]) for x in c)
            n += sum(int(x["n"]) for x in c)
    return vol, n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--usd-per-leg", type=float, default=25.0)
    ap.add_argument("--max-surfaces", type=int, default=4)
    ap.add_argument("--max-inventory-usd", type=float, default=60.0,
                    help="per surface; inventory is a DIRECTIONAL position")
    ap.add_argument("--min-vol", type=float, default=2000.0)
    ap.add_argument("--min-trades", type=int, default=50)
    ap.add_argument("--min-spread-bps", type=float, default=20.0,
                    help="skip books too tight to round-trip after the sell fee")
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

    if KILL.exists():
        print("KILL present — refusing to quote")
        return 3
    lock_fd = open(LOCK, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another roundtrip run holds the lock — refusing")
        return 4

    gs = GameState()
    if not gs.refresh():
        print("score feed unreachable — refusing to quote (fail safe)")
        return 2

    sp = post({"type": "spotClearinghouseState", "user": MASTER}) or {}
    held = {b["coin"]: float(b["total"]) for b in sp.get("balances", [])
            if b["coin"].startswith("+") and float(b["total"]) > 0}
    usdc = next((b for b in sp.get("balances", []) if b["coin"] == "USDC"), None)
    free = (float(usdc["total"]) - float(usdc["hold"])) if usdc else 0.0

    orders = post({"type": "openOrders", "user": MASTER}) or []
    resting = {}
    for o in orders:
        if o["coin"].startswith("#"):
            resting.setdefault(o["coin"], []).append(o)

    meta = post({"type": "outcomeMeta"}) or {}
    plan = []
    for o in meta.get("outcomes", []):
        if len(plan) >= args.max_surfaces:
            break
        d = o.get("description", "")
        safe, reason = gs.is_safe_to_quote(d)
        if not safe:
            continue
        if any(t in d for t in ("perp:", "priceBinary", "priceDescription")):
            continue
        oid = o["outcome"]
        b = post({"type": "l2Book", "coin": f"#{10 * oid}"})
        time.sleep(0.08)
        lv = (b or {}).get("levels") or []
        if len(lv) < 2 or not lv[0] or not lv[1]:
            continue
        bid, ask = float(lv[0][0]["px"]), float(lv[1][0]["px"])
        if not (MIN_PX <= bid <= MAX_PX):
            continue
        spread_bps = (ask - bid) * 10_000          # bps of FACE ($1), not notional
        if spread_bps < args.min_spread_bps:
            continue
        vol, n = traded_24h(oid)
        if vol < args.min_vol or n < args.min_trades:
            continue
        plan.append({"oid": oid, "desc": d, "bid": bid, "ask": ask,
                     "spread_bps": spread_bps, "vol": vol, "n": n, "reason": reason})

    print(f"surfaces: {len(plan)}  (spread >= {args.min_spread_bps:.0f}bps of face, "
          f"vol >= ${args.min_vol:.0f}, {args.min_trades}+ trades)")
    for s in plan:
        nm = (s["desc"].split("participant:")[1].split("|")[0]
              if "participant:" in s["desc"] else str(s["oid"]))
        inv = held.get(f"+{s['oid']}0", 0.0)
        print(f"  #{s['oid']*10:<7} {nm:<14} bid {s['bid']:.5f} ask {s['ask']:.5f} "
              f"spread {s['spread_bps']:5.1f}bps  vol ${s['vol']:,.0f}/{s['n']}t  "
              f"inventory {inv:.0f}")
    if not args.execute:
        print("\nDRY RUN — nothing submitted.")
        return 0

    key = open(ENV).read().split("HL_PRIVATE_KEY=")[1].split("\n")[0].strip()
    ex = Exchange(eth_account.Account.from_key(key), constants.MAINNET_API_URL,
                  meta=post({"type": "meta"}), spot_meta=post({"type": "spotMeta"}),
                  account_address=MASTER)
    register_outcome_assets(ex.info)

    placed = 0
    for s in plan:
        coin = f"#{s['oid']*10}"
        inv_sz = held.get(f"+{s['oid']}0", 0.0)
        inv_usd = inv_sz * s["bid"]
        have = resting.get(coin, [])
        has_buy = any(o["side"] == "B" for o in have)
        has_sell = any(o["side"] == "A" for o in have)

        # SELL SIDE FIRST — an unsold leg is a directional position, and the
        # whole thesis is that exiting as a maker (3.9 bps of face) beats
        # settling (13.27). Offer everything we hold, one tick inside the ask.
        if inv_sz >= 1 and not has_sell:
            px = round(s["ask"] - TICK, 5)
            if px > s["bid"]:
                r = ex.order(coin, False, float(int(inv_sz)), px,
                             order_type={"limit": {"tif": "Alo"}}, reduce_only=False,
                             builder={"b": BUILDER, "f": 0})
                st = (r.get("response", {}).get("data", {}).get("statuses") or [{}])[0]
                if "error" in st:
                    log.error("SELL rejected %s %s @ %s: %s", coin, int(inv_sz), px, st["error"])
                else:
                    placed += 1
                    log.info("OFFER %s %d @ %.5f (bought near %.5f)", coin, int(inv_sz), px, s["bid"])
                time.sleep(0.4)

        # BUY SIDE — only if inventory has room and cash allows.
        if inv_usd < args.max_inventory_usd and not has_buy:
            px = round(s["bid"] + TICK, 5)
            if px >= s["ask"]:
                px = round(s["bid"], 5)
            sz = int(args.usd_per_leg / px)
            if sz >= 1 and free >= sz * px:
                r = ex.order(coin, True, float(sz), px,
                             order_type={"limit": {"tif": "Alo"}}, reduce_only=False,
                             builder={"b": BUILDER, "f": 0})
                st = (r.get("response", {}).get("data", {}).get("statuses") or [{}])[0]
                if "error" in st:
                    log.error("BID rejected %s %s @ %s: %s", coin, sz, px, st["error"])
                else:
                    placed += 1
                    free -= sz * px
                    log.info("BID %s %d @ %.5f", coin, sz, px)
                time.sleep(0.4)

    print(f"\nplaced {placed} orders across {len(plan)} surfaces; free ${free:.2f}")
    print("maker share of fills is the number to watch — target >=90%, we ran 50%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
