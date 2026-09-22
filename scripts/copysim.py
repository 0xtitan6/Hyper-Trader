#!/usr/bin/env python
"""Honest copy-trade simulator: real position book, our own taker fee, live caps.

Why this exists and src/backtest.py does not answer the question:
  * backtest.py has no position book -> it cannot know when a signal is
    rejected by an exposure cap (it says so itself at line 28).
  * at sizing.mode=fixed it charges the LEADER's fee scaled by size ratio,
    not our own taker fee on our own clip.
  Result: it reported +$65,279 of copy PnL on a $640 account.

Replays a leader's fills in time order. We mirror each fill with a fixed-USD
clip, subject to a notional cap. We pay OUR taker fee + assumed slippage on
every clip we actually place. PnL is realised on position reduction (FIFO-ish
via running average cost), which is how closedPnl works.
"""
import argparse, json, sys, time
from collections import defaultdict
import requests

API = "https://api.hyperliquid.xyz/info"


def post(payload, tries=6):
    """HL is rate-limited and the live engine is already hammering it."""
    delay = 1.0
    for i in range(tries):
        try:
            r = requests.post(API, json=payload, timeout=30)
            if r.status_code == 429:
                time.sleep(delay); delay = min(delay * 2, 30); continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if i == tries - 1:
                raise
            time.sleep(delay); delay = min(delay * 2, 30)
    return None


def fetch_fills(addr, start_ms, end_ms):
    """Page forward. HL caps a response at 2000 fills, so a busy leader needs
    many pages; we advance by last-fill time to avoid an infinite loop."""
    out, cursor, seen = [], start_ms, set()
    while cursor < end_ms:
        page = post({"type": "userFillsByTime", "user": addr,
                     "startTime": cursor, "endTime": end_ms})
        if not page:
            break
        fresh = [f for f in page if (f["tid"], f["time"]) not in seen]
        for f in fresh:
            seen.add((f["tid"], f["time"]))
        out.extend(fresh)
        if len(page) < 2000:
            break
        newest = max(f["time"] for f in page)
        if newest <= cursor:
            break
        cursor = newest
        time.sleep(0.35)
    out.sort(key=lambda f: f["time"])
    return out



def market_type(coin: str) -> str:
    """Mirror src/mirror.py:_is_allowed_market's classification exactly."""
    if coin.startswith("#") or coin.startswith("+"):
        return "outcome"
    if coin.startswith("@") or "/" in coin:
        return "spot"
    return "perp"


def simulate(fills, clip_usd, cap_usd, fee_bps, slip_bps, per_trade_max=120.0,
             per_trade_min=10.0):
    """Mirror each leader fill with our own clip. Returns (stats, per_coin, per_day)."""
    pos = defaultdict(float)        # coin -> our signed size
    avg = defaultdict(float)        # coin -> our average entry px
    realised = 0.0
    fees = 0.0
    taken = blocked_cap = blocked_min = 0
    opens = 0
    per_coin = defaultdict(float)
    per_day = defaultdict(float)
    cost_per_coin = defaultdict(float)

    for f in fills:
        coin, px = f["coin"], float(f["px"])
        sz = float(f["sz"])
        side = 1.0 if f["side"] == "B" else -1.0
        leader_sz = side * sz
        if leader_sz == 0 or px <= 0:
            continue
        day = time.strftime("%Y-%m-%d", time.gmtime(f["time"] / 1000))

        cur = pos[coin]
        reducing = cur != 0 and (cur > 0) != (leader_sz > 0)

        if reducing:
            # Close (up to) our whole position in this coin, proportionally.
            close_sz = min(abs(cur), abs(cur))  # leader flattens -> we flatten
            direction = 1.0 if cur > 0 else -1.0
            gross = (px - avg[coin]) * direction * close_sz
            notional = px * close_sz
            cost = notional * (fee_bps + slip_bps) / 1e4
            realised += gross - cost
            fees += cost
            per_coin[coin] += gross - cost
            per_day[day] += gross - cost
            cost_per_coin[coin] += cost
            pos[coin] = 0.0
            avg[coin] = 0.0
            taken += 1
            continue

        # An opening / adding signal.
        opens += 1
        gross_now = sum(abs(pos[c]) * px if c == coin else 0 for c in pos)
        # cap is on total gross notional across the book
        book_notional = 0.0
        for c, p in pos.items():
            if p:
                book_notional += abs(p) * (px if c == coin else avg[c] or px)
        want = min(max(clip_usd, per_trade_min), per_trade_max)
        if want < per_trade_min:
            blocked_min += 1
            continue
        if book_notional + want > cap_usd:
            blocked_cap += 1
            continue

        our_sz = (want / px) * (1.0 if leader_sz > 0 else -1.0)
        cost = want * (fee_bps + slip_bps) / 1e4
        realised -= cost
        fees += cost
        per_coin[coin] -= cost
        per_day[day] -= cost
        cost_per_coin[coin] += cost
        new = pos[coin] + our_sz
        if pos[coin] == 0:
            avg[coin] = px
        else:
            avg[coin] = (avg[coin] * abs(pos[coin]) + px * abs(our_sz)) / abs(new)
        pos[coin] = new
        taken += 1

    open_notional = sum(abs(p) * avg[c] for c, p in pos.items() if p)
    return ({"net": realised, "fees": fees, "gross": realised + fees,
             "taken": taken, "opens": opens, "blocked_cap": blocked_cap,
             "blocked_min": blocked_min, "open_notional": open_notional},
            dict(per_coin), dict(per_day))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("addrs", nargs="+")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--clip", type=float, default=30.0)
    ap.add_argument("--fee-bps", type=float, default=4.5, help="our taker fee per side")
    ap.add_argument("--caps", default="100,200,400,800")
    ap.add_argument("--slips", default="2,5,10,20")
    ap.add_argument("--cache", default="state/copysim_fills")
    ap.add_argument("--markets", default="",
                    help="comma list of market types to keep (perp,outcome,spot). "
                         "Empty = all. Set this to config.yaml's risk.allowed_market_types "
                         "to see what our engine can ACTUALLY reach.")
    args = ap.parse_args()

    now = int(time.time() * 1000)
    start = now - args.days * 86400_000

    for addr in args.addrs:
        import os
        os.makedirs(args.cache, exist_ok=True)
        cf = f"{args.cache}/{addr[:10]}_{args.days}d.json"
        if os.path.exists(cf) and (time.time() - os.path.getmtime(cf)) < 6 * 3600:
            fills = json.load(open(cf))
            src = "cache"
        else:
            fills = fetch_fills(addr, start, now)
            json.dump(fills, open(cf, "w"))
            src = "api"
        if not fills:
            print(f"{addr}: NO FILLS in {args.days}d"); continue

        if args.markets:
            keep = {m.strip() for m in args.markets.split(",") if m.strip()}
            before = len(fills)
            fills = [f for f in fills if market_type(f["coin"]) in keep]
            print(f"  [markets={sorted(keep)}] kept {len(fills)}/{before} fills")
            if not fills:
                print(f"{addr}: NO FILLS of type {sorted(keep)}"); continue

        days_active = len({time.strftime('%Y-%m-%d', time.gmtime(f['time']/1000)) for f in fills})
        taker = sum(1 for f in fills if f.get("crossed"))
        coins = defaultdict(int)
        for f in fills:
            coins[f["coin"]] += 1
        base_fills = sum(n for c, n in coins.items() if ":" not in c)

        print("=" * 78)
        print(f"{addr}  ({src})")
        print(f"  fills={len(fills)}  active_days={days_active}  "
              f"~{len(fills)/max(days_active,1):.0f}/day  taker={100*taker/len(fills):.0f}%")
        print(f"  base-dex fills={base_fills} ({100*base_fills/len(fills):.0f}%)  "
              f"top coins={sorted(coins.items(), key=lambda x:-x[1])[:5]}")

        print(f"\n  Net copy PnL, {args.days}d, ${args.clip:.0f} clips, our fee {args.fee_bps}bps/side")
        print(f"  {'cap':>8} | " + " | ".join(f"{'slip '+s+'bps':>12}" for s in args.slips.split(",")))
        for cap in [float(x) for x in args.caps.split(",")]:
            row = []
            for slip in [float(x) for x in args.slips.split(",")]:
                st, _, _ = simulate(fills, args.clip, cap, args.fee_bps, slip)
                row.append(f"{st['net']:+12.2f}")
            print(f"  {cap:>8.0f} | " + " | ".join(row))

        # detail at the middle setting
        mid_cap = float(args.caps.split(",")[-1])
        st, pc, pd = simulate(fills, args.clip, mid_cap, args.fee_bps, 5.0)
        print(f"\n  DETAIL @ cap ${mid_cap:.0f}, slip 5bps:")
        print(f"    gross {st['gross']:+.2f}  fees {st['fees']:.2f}  NET {st['net']:+.2f}"
              f"   fee drag = {100*st['fees']/abs(st['gross']) if st['gross'] else 0:.0f}% of gross")
        print(f"    open signals {st['opens']}, taken {st['taken']}, "
              f"blocked by cap {st['blocked_cap']} "
              f"({100*st['blocked_cap']/max(st['opens'],1):.1f}% of opens)")
        top = sorted(pc.items(), key=lambda x: -abs(x[1]))[:5]
        print(f"    by coin: {[(c, round(v,2)) for c,v in top]}")
        if pc:
            best_coin = max(pc.items(), key=lambda x: x[1])
            print(f"    ex-best-coin ({best_coin[0]} {best_coin[1]:+.2f}): "
                  f"{st['net']-best_coin[1]:+.2f}")
        if pd:
            best_day = max(pd.items(), key=lambda x: x[1])
            print(f"    ex-best-day  ({best_day[0]} {best_day[1]:+.2f}): "
                  f"{st['net']-best_day[1]:+.2f}")


if __name__ == "__main__":
    main()
