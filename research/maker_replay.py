r"""Maker-replay backtest on REAL HL outcome tape — the direct profitability test.

The synthetic RL sim answers "is making profitable IF informed_rate=X". This answers
it on OUR actual flow. Glosten-Milgrom decomposition: a passive maker quoting at the
touch earns the half-spread on every fill but pays adverse selection when the taker who
hit it was informed (price then moves against the maker's new inventory).

Per real taker trade:
  maker_sign = +1 if taker SOLD (side A) -> maker BUYS at bid, ends up LONG
             = -1 if taker BOUGHT (side B) -> maker SELLS at ask, ends up SHORT
  per-unit maker PnL = half_spread  +  maker_sign * forward_mid_move
                       \_____________/   \_________________________/
                        spread captured    adverse selection (negative if flow is informed)

Uses book snapshots (mid, spread) nearest each trade, and the forward mid move from the
book series. Size-weighted with a per-fill cap (a real maker can't absorb unbounded size).
Honest: reports spread income vs adverse-selection cost separately, and per-market.
"""
import json
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime

REPO = "/home/ec2-user/.openclaw/workspace/hyper-trader"
BOOK = f"{REPO}/research/ml_market_snapshots.jsonl"
TAPE = f"{REPO}/research/trade_flow.jsonl"
FWD_S = 90            # horizon over which adverse selection is realized
MATCH_TOL_S = 60      # a trade must have a book snapshot within this to be usable
FILL_CAP = 20.0       # max size (contracts) the maker fills per trade
HALF_SPREAD_FLOOR = 0.002   # don't credit sub-tick spreads
# REALISTIC maker half-spread cap: you CANNOT harvest the full wide quote of an
# illiquid market risk-free (that width IS the illiquidity). A competitive maker
# quotes tight to win fills; cap what we credit ourselves at a realistic 1-tick edge.
HALF_SPREAD_CAP = 0.01
FILL_PROB = 0.35      # we win only a fraction of flow (queue competition)


def ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def load_books():
    books = defaultdict(list)  # coin -> [(t, mid, half_spread)]
    for l in open(BOOK, encoding="utf-8", errors="ignore"):
        try:
            o = json.loads(l)
        except Exception:
            continue
        t = ts(o.get("ts", "")); mid = o.get("mid")
        if t is None or mid is None:
            continue
        sp_bps = float(o.get("spread_bps", 0) or 0)
        half = max((sp_bps / 10000.0) * float(mid) / 2.0, 0.0)
        books[o["coin"]].append((t, float(mid), half))
    for c in books:
        books[c].sort()
    return books


def mid_at(series, times, t):
    """mid at the first snapshot >= t (None if past the end)."""
    i = bisect_left(times, t)
    return series[i][1] if i < len(series) else None


def nearest(series, times, t, tol):
    """(mid, half_spread) of the snapshot closest to t within tol, else None."""
    i = bisect_left(times, t)
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(series) and abs(series[j][0] - t) <= tol:
            if best is None or abs(series[j][0] - t) < abs(series[best][0] - t):
                best = j
    return (series[best][1], series[best][2]) if best is not None else None


def run(books, times, tape, fill_prob, half_cap):
    per = defaultdict(lambda: [0.0, 0.0, 0.0, 0])  # coin -> [spread_inc, adv_sel, net, n]
    used = skipped = 0
    for o in tape:
        coin = o.get("coin")
        if coin not in books:
            skipped += 1; continue
        t = ts(o.get("ts", ""))
        try:
            sz = min(float(o.get("sz")), FILL_CAP)
        except (TypeError, ValueError):
            continue
        if t is None:
            continue
        nb = nearest(books[coin], times[coin], t, MATCH_TOL_S)
        if nb is None:
            skipped += 1; continue
        mid_now, half = nb
        half = min(max(half, HALF_SPREAD_FLOOR), half_cap)   # realistic competitive quote
        mid_fwd = mid_at(books[coin], times[coin], t + FWD_S)
        if mid_fwd is None:
            skipped += 1; continue
        maker_sign = 1.0 if o.get("side") == "A" else -1.0   # A=taker sell -> maker long
        fwd_move = mid_fwd - mid_now
        eff_sz = sz * fill_prob
        spread_inc = half * eff_sz
        adv_sel = maker_sign * fwd_move * eff_sz
        rec = per[coin]
        rec[0] += spread_inc; rec[1] += adv_sel; rec[2] += spread_inc + adv_sel; rec[3] += 1
        used += 1
    return per, used, skipped


def main():
    books = load_books()
    times = {c: [r[0] for r in s] for c, s in books.items()}
    tape = []
    for l in open(TAPE, encoding="utf-8", errors="ignore"):
        try:
            tape.append(json.loads(l))
        except Exception:
            pass
    per, used, skipped = run(books, times, tape, FILL_PROB, HALF_SPREAD_CAP)
    tot_spread = sum(v[0] for v in per.values())
    tot_adv = sum(v[1] for v in per.values())
    tot_net = sum(v[2] for v in per.values())
    print(f"maker-replay on real HL tape: {used} fills simulated ({skipped} skipped for no book match)")
    print(f"  spread income:        ${tot_spread:+.3f}")
    print(f"  adverse selection:    ${tot_adv:+.3f}   (negative = informed flow hurt the maker)")
    print(f"  ---------------------------------------")
    print(f"  NET maker P&L:        ${tot_net:+.3f}   ({'PROFITABLE' if tot_net > 0 else 'LOSS'} on captured flow)")
    if used:
        print(f"  per-fill avg:         ${tot_net/used:+.5f}   spread ${tot_spread/used:.5f} / advsel ${tot_adv/used:+.5f}")
        print(f"  adv-sel as % of spread: {100*abs(tot_adv)/(tot_spread+1e-9):.1f}%  "
              f"({'spread survives adverse selection' if tot_net>0 else 'adverse selection eats the spread'})")
    print(f"\n  per-market (net, n):")
    for coin, v in sorted(per.items(), key=lambda z: z[1][2]):
        if v[3] >= 10:
            print(f"    {coin:14} net=${v[2]:+.3f}  spread=${v[0]:.3f} advsel=${v[1]:+.3f}  n={v[3]}")

    # ---- sensitivity: is the +net robust across assumptions, or fragile? ----
    print(f"\n=== sensitivity grid: NET maker P&L vs (fill_prob x half_spread_cap) ===")
    print(f"  {'fill_prob':>10} " + " ".join(f"cap={c:.3f}".rjust(11) for c in (0.005, 0.010, 0.020)))
    all_pos = True
    for fp in (0.20, 0.35, 0.50):
        cells = []
        for cap in (0.005, 0.010, 0.020):
            p, _, _ = run(books, times, tape, fp, cap)
            net = sum(v[2] for v in p.values())
            all_pos = all_pos and net > 0
            cells.append(f"${net:+.1f}".rjust(11))
        print(f"  {fp:>10.2f} " + " ".join(cells))
    print(f"  => {'ROBUST: profitable across ALL plausible assumptions' if all_pos else 'FRAGILE: flips negative somewhere — flag it'}")


if __name__ == "__main__":
    main()
