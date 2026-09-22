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

# PASSIVE HEDGING.
#
# Crossing the spread the instant a leg fills is correct for a live event and
# wrong for a book days from kickoff. Measured 2026-09-21, our first two real
# fills: the minder crossed within 6 minutes and both baskets completed ABOVE
# par (1.01056 and 1.00212), turning a quoted +1.25% edge into a realised
# -0.80%. The fill you get is the leg the market is moving away from, so by the
# time you cross, the other side has repriced past your edge.
#
# With days to run there is no reason to pay that spread. Rest a bid at the
# price that still clears a profit and let it come to you; escalate to crossing
# only when the clock forces it.
HEDGE_TARGET_TOTAL = 0.995   # basket cost to aim for => +0.5% locked
PASSIVE_MAX_H = 24.0         # give a passive hedge this long before crossing
CROSS_DEADLINE_H = 4.0       # inside this to kickoff, complete at market
MIN_HEDGE_PX = 0.002         # below this a bid is noise, not a quote


def hedge_decision(paid: float, bid: float, ask: float,
                   hours_to_event: float | None, position_age_h: float,
                   resting_px: float | None) -> dict:
    """Decide how to complete a one-sided basket. Pure function, so it can be
    tested against the cases that actually cost money.

    Returns {"action": CROSS|REST|KEEP|HOLD, "px": float|None, "reason": str}.

      CROSS  take the ask now — either it is already profitable, or the clock
             has run out and locking a small loss beats holding a coin flip
      REST   post a bid at the price that still clears HEDGE_TARGET_TOTAL
      KEEP   a correct passive hedge is already resting; leave it alone
      HOLD   completing would cost more than MAX_PAIR_COST; a naked leg is bad
             but locking a >2% loss to fix it is worse
    """
    target_px = round(HEDGE_TARGET_TOTAL - paid, 5)
    cross_cost = paid + ask

    # 1. The ask is already cheap enough to clear our target. Free — take it.
    if ask <= target_px:
        return {"action": "CROSS", "px": ask,
                "reason": f"ask {ask:.5f} already clears target "
                          f"(basket {cross_cost:.5f} <= {HEDGE_TARGET_TOTAL})"}

    # 2. Clock forcing. Inside the deadline, or the position has sat too long.
    #    A resting bid that never fills leaves us naked into the event, which is
    #    the exposure this whole script exists to prevent.
    forced = (hours_to_event is not None and hours_to_event < CROSS_DEADLINE_H)
    aged = position_age_h > PASSIVE_MAX_H
    if forced or aged:
        why = (f"kickoff in {hours_to_event:.1f}h" if forced
               else f"position {position_age_h:.1f}h old")
        if cross_cost > MAX_PAIR_COST:
            return {"action": "HOLD", "px": None,
                    "reason": f"{why} but crossing costs {cross_cost:.5f} > "
                              f"{MAX_PAIR_COST} — locking that beats nothing"}
        return {"action": "CROSS", "px": ask,
                "reason": f"{why} — completing at {cross_cost:.5f} "
                          f"({(1.0 - cross_cost) * 100:+.2f}%)"}

    # 3. No room left: we already paid more than the whole target basket.
    if target_px < MIN_HEDGE_PX:
        return {"action": "HOLD", "px": None,
                "reason": f"paid {paid:.5f} leaves only {target_px:.5f} for the "
                          f"hedge — no passive price exists"}

    # 4. Already resting at (or better than) the right price — do not churn.
    if resting_px is not None and resting_px <= target_px + 1e-9:
        return {"action": "KEEP", "px": resting_px,
                "reason": f"passive hedge already resting at {resting_px:.5f}"}

    # 5. Rest a bid that still clears a profit. Never above the ask (that would
    #    cross and become the very taker fill we are avoiding).
    px = min(target_px, round(ask - 0.0005, 5))
    return {"action": "REST", "px": px,
            "reason": f"resting at {px:.5f} for basket {paid + px:.5f} "
                      f"({(1.0 - paid - px) * 100:+.2f}%); ask {ask:.5f} too dear"}
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


def hours_to_event(gs: GameState, description: str) -> float | None:
    """Hours until the contest starts, or None if we cannot tell.

    Returns None rather than guessing — the caller treats unknown as "no clock
    pressure", and the separate kickoff-cancel pass still pulls quotes."""
    st = gs.scheduled_start(description)
    if st is None:
        return None
    return (st - datetime.now(tz=timezone.utc)).total_seconds() / 3600.0


def opened_times() -> dict[str, float]:
    """Epoch seconds of the FIRST fill on each outcome leg we hold, so a passive
    hedge can be aged out rather than resting forever."""
    fills = post({"type": "userFills", "user": MASTER}) or []
    first: dict[str, float] = {}
    for f in fills:
        c = f.get("coin", "")
        if not c.startswith("#") or f.get("dir") == "Settlement":
            continue
        key = "+" + c.lstrip("#")
        t = f["time"] / 1000.0
        first[key] = min(first.get(key, t), t)
    return first


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
    opened_at = opened_times()

    actions: list[str] = []

    # Surfaces owned by the ROUND-TRIP maker. Single-leg inventory there is the
    # strategy, not an accident: it buys a leg as maker and offers the SAME leg
    # back as maker, never crossing and never settling (+3.8 to +15.6 bps).
    #
    # Measured 2026-09-21: within 5h of the round-trip maker going live, this
    # minder had "hedged" 8 of its surfaces by buying the complement — silently
    # converting every round trip into the cross-and-settle basket that costs
    # -18.3 bps by construction, which is the trade we had just stopped running.
    # Two strategies, opposite intentions, same inventory.
    owned: set[int] = set()
    try:
        owned = set(json.loads((ROOT / "state" / "roundtrip_owned.json").read_text())
                    .get("outcomes", []))
    except (OSError, ValueError):
        pass

    # --- 1. one-sided holdings -> hedge -------------------------------------
    one_sided = []
    for coin, sz in held.items():
        leg = coin.lstrip("+")
        oid, side = int(leg[:-1]), int(leg[-1])
        comp = f"+{oid}{1 - side}"
        if comp in held:
            continue          # already a complete basket
        if oid in owned:
            continue          # round-trip inventory — leave it alone
        one_sided.append((coin, sz, oid, side, comp))

    # Resting orders keyed by coin, so we can see an existing passive hedge.
    resting_by_coin: dict[str, list] = {}
    for o in orders:
        resting_by_coin.setdefault(o["coin"], []).append(o)

    decisions = []
    for coin, sz, oid, side, comp in one_sided:
        hedge_coin = f"#{oid}{1 - side}"
        book = post({"type": "l2Book", "coin": hedge_coin})
        lv = (book or {}).get("levels") or []
        if len(lv) < 2 or not lv[0] or not lv[1]:
            actions.append(f"ESCALATE {coin}: one-sided, no book on {hedge_coin} to hedge into")
            record("hedge_no_book", coin=coin, hedge=hedge_coin, sz=sz)
            continue
        bid, ask = float(lv[0][0]["px"]), float(lv[1][0]["px"])
        paid = basis.get(coin)
        if paid is None:
            actions.append(f"ESCALATE {coin}: holding it but no fill found — cannot price a hedge")
            record("hedge_no_basis", coin=coin, sz=sz)
            continue

        hrs = hours_to_event(gs, desc.get(oid, "")) if feed_ok else None
        age_h = (time.time() - opened_at.get(coin, time.time())) / 3600.0
        rp = resting_by_coin.get(hedge_coin)
        resting_px = min(float(o["limitPx"]) for o in rp) if rp else None

        d = hedge_decision(paid=paid, bid=bid, ask=ask, hours_to_event=hrs,
                           position_age_h=age_h, resting_px=resting_px)
        d.update(coin=coin, sz=sz, hedge_coin=hedge_coin, paid=paid,
                 ask=ask, existing=rp or [])
        decisions.append(d)
        actions.append(f"{d['action']} {coin} sz={sz:.0f} paid={paid:.5f} -> "
                       f"{hedge_coin}: {d['reason']}")
        record("hedge_decision", coin=coin, hedge=hedge_coin, sz=sz,
               action=d["action"], px=d["px"], paid=paid, ask=ask,
               hours_to_event=hrs, age_h=round(age_h, 2), reason=d["reason"])

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
        safe, reason = gs.is_safe_to_quote(d, o.get("name",""))
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
        for d in decisions:
            hedge_coin, sz = d["hedge_coin"], d["sz"]
            if d["action"] in ("HOLD", "KEEP"):
                continue

            # Cancel our own resting order on the leg we are about to act on.
            #
            # The one-sided position usually arose because a PAIR was quoted and
            # only one leg filled, so our bid on the other leg is still resting.
            # Completing the basket while it stays alive means that if it later
            # fills we hold TWICE the hedge leg and are naked by the excess.
            # Measured 2026-09-21: after two baskets completed, 202 shares were
            # still resting on Giants YES against an 80/80 basket, and 151 on
            # Croatia YES against 151/151.
            for o in d["existing"]:
                try:
                    ex.cancel(hedge_coin, o["oid"])
                    log.info("cancelled own resting %s %s @ %s", hedge_coin, o["sz"], o["limitPx"])
                    record("cancel_before_hedge", coin=hedge_coin, sz=o["sz"], px=o["limitPx"])
                except Exception as e:  # noqa: BLE001
                    log.error("could not cancel %s: %s", hedge_coin, e)
                time.sleep(0.2)

            try:
                if d["action"] == "CROSS":
                    # Immediacy is the point: pay up to the ask, IOC.
                    r = ex.order(hedge_coin, True, float(int(sz)),
                                 round(d["px"] * 1.01, 5),
                                 order_type={"limit": {"tif": "Ioc"}}, reduce_only=False,
                                 builder={"b": BUILDER, "f": 0})
                else:  # REST — post-only, never cross, let it come to us
                    r = ex.order(hedge_coin, True, float(int(sz)), d["px"],
                                 order_type={"limit": {"tif": "Alo"}}, reduce_only=False,
                                 builder={"b": BUILDER, "f": 0})
                st = (r.get("response", {}).get("data", {}).get("statuses") or [{}])[0]
                if "error" in st:
                    log.error("%s %s REJECTED: %s", d["action"], hedge_coin, st["error"])
                    record("hedge_rejected", coin=hedge_coin, action=d["action"],
                           px=d["px"], error=st["error"])
                else:
                    log.info("%s %s sz=%s @ %s -> %s", d["action"], hedge_coin,
                             int(sz), d["px"], str(st)[:100])
                    record("hedged", coin=d["coin"], hedge=hedge_coin, sz=sz,
                           action=d["action"], px=d["px"], basket=d["paid"] + d["px"])
            except Exception as e:  # noqa: BLE001
                log.error("hedge failed %s: %s", hedge_coin, e)
            time.sleep(0.4)

    return 1


if __name__ == "__main__":
    sys.exit(main())
