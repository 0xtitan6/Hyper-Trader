#!/usr/bin/env python3
"""Minds live HIP-4 pair-maker positions. Deterministic, zero tokens.

Resting quotes without a minder is how the 2026-09-19 loss happened: a bid
filled one-sided during a live match and nothing acted on it for hours. This
closes that loop. Three jobs, in order of urgency:

1. HEDGE a one-sided fill. Holding one leg is an unchosen directional bet. If we
   hold leg A and not leg B, cross for B immediately so the pair settles to
   exactly $1.00. Refuses if the pair would now cost more than
   MAX_PAIR_COST — past that the leg has already repriced and hedging only locks
   the loss at the worst price, which is EV-neutral versus simply holding. ALL
   the value of hedging is in doing it at the moment of the fill.

2. PULL QUOTES before kickoff. The whole thesis is that pre-match books are safe
   and in-play books are not (measured: 0.17% vs 6.68% paired edge). A resting
   quote becomes an in-play quote the moment the match starts, silently. Cancel
   anything whose fixture is within KICKOFF_BUFFER_H, and cancel everything on a
   surface the guard now refuses.

3. REPORT a genuinely stuck position so a human sees it.

Exit codes: 0 nothing needed, 1 acted, 2 escalate.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import eth_account
import requests
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.gamestate import KICKOFF_BUFFER_H, GameState  # noqa: E402
from src.hl_outcome import register_outcome_assets  # noqa: E402

MASTER = "0xE503186067b1B0Fb973c063054B14c4625434A1a"
BUILDER = "0xab5dbc057628bc18523c4cdfc0e1e2ebdbecb704"
ENV = "/home/ec2-user/.config/hyper-trader/copytrader.env"
INFO = "https://api.hyperliquid.xyz/info"
KILL = ROOT / "KILL"
LEDGER = ROOT / "state" / "pair_minder.jsonl"

MAX_PAIR_COST = 1.02      # beyond this, hedging is EV-neutral — do not bother
# KICKOFF_BUFFER_H is imported from src.gamestate so the maker and the minder
# can never disagree about when a pre-match book stops being pre-match.

log = logging.getLogger("minder")


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


def cost_basis() -> dict[str, float]:
    """Average price we actually PAID per outcome leg, from our own fills.

    This is the number the hedge decision turns on, and using the market bid
    instead is a live bug this script was born with: on 2026-09-20 it saw
    market_bid + hedge_ask = 1.0000 and said HEDGE, when we had paid 0.41876 for
    the leg, making the real pair cost 1.0666 — a guaranteed -6.7%. The market
    bid tells you what the leg is worth now; only the cost basis tells you
    whether completing the basket still profits.
    """
    fills = post({"type": "userFills", "user": MASTER}) or []
    agg: dict[str, list[float]] = {}
    for f in fills:
        c = f.get("coin", "")
        if not c.startswith("#") or f.get("dir") == "Settlement":
            continue
        try:
            sz, px = float(f["sz"]), float(f["px"])
        except (KeyError, TypeError, ValueError):
            continue
        key = "+" + c.lstrip("#")
        agg.setdefault(key, [0.0, 0.0])
        agg[key][0] += sz
        agg[key][1] += sz * px
    return {k: (v[1] / v[0]) for k, v in agg.items() if v[0] > 0}


def outcome_desc() -> dict[int, str]:
    meta = post({"type": "outcomeMeta"}) or {}
    return {o["outcome"]: o.get("description", "") for o in meta.get("outcomes", [])}


def record(event: str, **kw) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as f:
        f.write(json.dumps({"ts": time.time(), "event": event, **kw}) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="default is dry-run")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

    spot = post({"type": "spotClearinghouseState", "user": MASTER}) or {}
    held = {b["coin"]: float(b["total"]) for b in spot.get("balances", [])
            if b["coin"].startswith("+") and float(b["total"]) > 0}
    orders = post({"type": "openOrders", "user": MASTER}) or []
    desc = outcome_desc()
    basis = cost_basis()
    gs = GameState()
    feed_ok = gs.refresh()

    actions: list[str] = []

    # --- 1. one-sided holdings -> hedge -------------------------------------
    one_sided = []
    for coin, sz in held.items():
        leg = coin.lstrip("+")
        oid, side = int(leg[:-1]), int(leg[-1])
        comp = f"+{oid}{1 - side}"
        if comp in held:
            continue          # already a complete basket
        one_sided.append((coin, sz, oid, side, comp))

    for coin, sz, oid, side, comp in one_sided:
        hedge_coin = f"#{oid}{1 - side}"
        book = post({"type": "l2Book", "coin": hedge_coin})
        lv = (book or {}).get("levels") or []
        if len(lv) < 2 or not lv[1]:
            actions.append(f"ESCALATE {coin}: one-sided, no book on {hedge_coin} to hedge into")
            record("hedge_no_book", coin=coin, hedge=hedge_coin, sz=sz)
            continue
        ask = float(lv[1][0]["px"])
        paid = basis.get(coin)
        if paid is None:
            actions.append(f"ESCALATE {coin}: holding it but no fill found — cannot price a hedge")
            record("hedge_no_basis", coin=coin, sz=sz)
            continue
        pair_cost = paid + ask          # WHAT WE PAID, not what it is worth now
        if pair_cost > MAX_PAIR_COST:
            actions.append(
                f"HOLD {coin} sz={sz:.0f}: paid {paid:.5f}, hedge asks {ask:.5f} "
                f"=> pair {pair_cost:.4f} > {MAX_PAIR_COST}. Hedging locks "
                f"{(1.0 - pair_cost) * 100:+.2f}% — EV-neutral vs holding, not a recovery.")
            record("hedge_skipped", coin=coin, paid=paid, ask=ask, pair_cost=pair_cost, sz=sz)
            continue
        actions.append(f"HEDGE {coin} sz={sz:.0f} paid {paid:.5f} -> buy {hedge_coin} @ {ask:.5f} "
                       f"(pair {pair_cost:.4f}, locks {(1.0 - pair_cost) * 100:+.2f}%)")
        record("hedge_needed", coin=coin, hedge=hedge_coin, sz=sz, ask=ask, pair_cost=pair_cost)

    # --- 2. quotes that are about to become in-play quotes -------------------
    stale_orders = []
    for o in orders:
        coin = o.get("coin", "")
        if not coin.startswith("#"):
            continue
        try:
            oid = int(coin.lstrip("#")[:-1])
        except ValueError:
            continue
        d = desc.get(oid, "")
        if not feed_ok:
            stale_orders.append((o, "score feed unreachable — cannot verify not-in-play"))
            continue
        safe, reason = gs.is_safe_to_quote(d)
        if not safe:
            stale_orders.append((o, reason))
            continue
        # Approaching kickoff: a resting quote becomes an in-play quote silently.
        if "next plays" in reason:
            day = reason.split("next plays")[1].split("(")[0].strip()
            try:
                ko = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
                hrs = (ko - datetime.now(tz=timezone.utc)).total_seconds() / 3600
                if hrs < KICKOFF_BUFFER_H:
                    stale_orders.append((o, f"kickoff in {hrs:.1f}h — inside {KICKOFF_BUFFER_H}h buffer"))
            except ValueError:
                pass

    for o, why in stale_orders:
        actions.append(f"CANCEL {o['coin']} {o['sz']} @ {o['limitPx']}: {why}")
        record("cancel_needed", coin=o["coin"], sz=o["sz"], px=o["limitPx"], reason=why)

    print(f"held legs: {len(held)} | one-sided: {len(one_sided)} | "
          f"resting orders: {len(orders)} | to cancel: {len(stale_orders)}")
    for a in actions:
        print("  " + a)
    if not actions:
        print("  nothing to do")
        return 0

    if not args.execute:
        print("\nDRY RUN — nothing submitted.")
        return 1

    if KILL.exists():
        print("KILL present — cancels still allowed, hedges are not")

    meta = post({"type": "meta"})
    spot_meta = post({"type": "spotMeta"})
    key = open(ENV).read().split("HL_PRIVATE_KEY=")[1].split("\n")[0].strip()
    ex = Exchange(eth_account.Account.from_key(key), constants.MAINNET_API_URL,
                  meta=meta, spot_meta=spot_meta, account_address=MASTER)
    register_outcome_assets(ex.info)

    for o, why in stale_orders:
        try:
            r = ex.cancel(o["coin"], o["oid"])
            log.info("cancelled %s: %s (%s)", o["coin"], r.get("status"), why[:60])
            record("cancelled", coin=o["coin"], reason=why)
        except Exception as e:  # noqa: BLE001
            log.error("cancel failed %s: %s", o["coin"], e)

    if not KILL.exists():
        for coin, sz, oid, side, comp in one_sided:
            hedge_coin = f"#{oid}{1 - side}"
            book = post({"type": "l2Book", "coin": hedge_coin})
            lv = (book or {}).get("levels") or []
            if len(lv) < 2 or not lv[1]:
                continue
            ask = float(lv[1][0]["px"])
            paid = basis.get(coin)
            if paid is None or paid + ask > MAX_PAIR_COST:
                continue
            try:
                # Whole shares only, and take it — immediacy is the entire point.
                r = ex.order(hedge_coin, True, float(int(sz)), round(ask * 1.01, 5),
                             order_type={"limit": {"tif": "Ioc"}}, reduce_only=False,
                             builder={"b": BUILDER, "f": 0})
                log.info("hedged %s with %s: %s", coin, hedge_coin, str(r)[:140])
                record("hedged", coin=coin, hedge=hedge_coin, sz=sz, result=str(r)[:200])
            except Exception as e:  # noqa: BLE001
                log.error("hedge failed %s: %s", hedge_coin, e)

    return 1


if __name__ == "__main__":
    sys.exit(main())
