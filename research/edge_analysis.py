"""Edge test: does book/flow imbalance predict forward mid-moves on HL outcome markets?

This is THE empirical question the collectors exist to answer (and the gate on whether
the maker/RL edge is real on our venue vs the mixed paper evidence). Aligns book
snapshots (mid, queue-imbalance) with the trade tape (taker flow), builds features at
time t and the forward mid-return label, and tests predictability out-of-sample.

Honest by construction: reports Spearman rank-corr AND an out-of-sample directional
hit-rate (train first half / test second half) vs the 50% coin-flip baseline. Thin
data early -> treat as preliminary; rerun as the tape grows.
"""
import json
import sys
from collections import defaultdict
from datetime import datetime

REPO = "/home/ec2-user/.openclaw/workspace/hyper-trader"
BOOK = f"{REPO}/research/ml_market_snapshots.jsonl"
TAPE = f"{REPO}/research/trade_flow.jsonl"
FWD_HORIZON_S = 90        # predict the mid move over the next ~90s
FLOW_WINDOW_S = 120       # trade-flow imbalance over the trailing 120s


def ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def load():
    books = defaultdict(list)   # coin -> [(t, mid, qi)]
    for l in open(BOOK, encoding="utf-8", errors="ignore"):
        try:
            o = json.loads(l)
        except Exception:
            continue
        t = ts(o.get("ts", ""))
        if t and o.get("mid") is not None:
            books[o["coin"]].append((t, float(o["mid"]), float(o.get("qi", 0))))
    trades = defaultdict(list)  # coin -> [(t, signed_sz)]  side B=buy(+), A=sell(-)
    for l in open(TAPE, encoding="utf-8", errors="ignore"):
        try:
            o = json.loads(l)
        except Exception:
            continue
        t = ts(o.get("ts", ""))
        try:
            sz = float(o.get("sz"))
        except (TypeError, ValueError):
            continue
        if t:
            sign = 1.0 if o.get("side") == "B" else -1.0
            trades[o["coin"]].append((t, sign * sz))
    for c in books:
        books[c].sort()
    for c in trades:
        trades[c].sort()
    return books, trades


def flow_imbalance(trs, t0, t1):
    b = s = 0.0
    for tt, ssz in trs:
        if tt < t0:
            continue
        if tt > t1:
            break
        if ssz > 0:
            b += ssz
        else:
            s += -ssz
    return (b - s) / (b + s) if (b + s) else 0.0


def spearman(xs, ys):
    n = len(xs)
    if n < 10:
        return 0.0
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0] * len(v)
        for pos, i in enumerate(order):
            r[i] = pos
        return r
    rx, ry = rank(xs), rank(ys)
    mx = sum(rx) / n; my = sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else 0.0


def main():
    books, trades = load()
    rows = []  # (qi, flow, momentum, fwd_ret)
    for coin, bk in books.items():
        trs = trades.get(coin, [])
        for i, (t, mid, qi) in enumerate(bk):
            # forward return: first snapshot >= t + FWD_HORIZON_S
            fwd = None
            for j in range(i + 1, len(bk)):
                if bk[j][0] >= t + FWD_HORIZON_S:
                    fwd = (bk[j][1] - mid)
                    break
            if fwd is None:
                continue
            flow = flow_imbalance(trs, t - FLOW_WINDOW_S, t)
            mom = mid - bk[i - 2][1] if i >= 2 else 0.0
            rows.append((qi, flow, mom, fwd))
    n = len(rows)
    print(f"aligned samples: {n} (from {len(books)} markets, {sum(len(v) for v in trades.values())} trades)")
    if n < 30:
        print("too few aligned samples — rerun once more data accrues.")
        return
    qi = [r[0] for r in rows]; flow = [r[1] for r in rows]; mom = [r[2] for r in rows]; fwd = [r[3] for r in rows]
    print("\n=== Spearman rank-corr vs forward mid-move ===")
    for name, x in (("book queue-imbalance (qi)", qi), ("trade flow-imbalance", flow), ("mid momentum", mom)):
        print(f"  {name:26} rho = {spearman(x, fwd):+.3f}")
    # out-of-sample directional test per feature (learn sign on train half, test on second)
    half = n // 2
    train, test = rows[:half], rows[half:]
    print(f"\n=== out-of-sample directional hit-rate (train {len(train)} / test {len(test)}) vs 50% ===")
    for idx, name in ((1, "trade flow-imbalance"), (0, "book queue-imbalance"), (2, "mid momentum")):
        agree = sum(1 for r in train if (r[idx] > 0) == (r[3] > 0) and r[3] != 0)
        tot_tr = sum(1 for r in train if r[3] != 0 and r[idx] != 0)
        direction = 1 if (tot_tr and agree >= tot_tr / 2) else -1
        hit = sum(1 for r in test if r[idx] != 0 and r[3] != 0 and ((r[idx] * direction > 0) == (r[3] > 0)))
        tot = sum(1 for r in test if r[idx] != 0 and r[3] != 0)
        edge = (hit / tot - 0.5) if tot else 0
        flag = ">>> EDGE" if abs(edge) > 0.03 and tot > 100 else "(no clear edge)"
        print(f"  {name:24} hit={100*hit/tot:.1f}% (n={tot}, dir={'+' if direction>0 else '-'})  {flag}")
    print("\n  NOTE: flow-imbalance is measured STRICTLY before t; forward move is after t -> genuinely predictive (no overlap).")

    # ---- robustness of the flow-imbalance signal (the only consistent one) ----
    print("\n=== flow-imbalance robustness ===")
    # (a) per-market rho: is it broad or driven by one market?
    per = []
    for coin, bk in books.items():
        trs = trades.get(coin, [])
        fx, fy = [], []
        for i, (t, mid, qi) in enumerate(bk):
            fwd = next((bk[j][1] - mid for j in range(i + 1, len(bk)) if bk[j][0] >= t + FWD_HORIZON_S), None)
            if fwd is None:
                continue
            fl = flow_imbalance(trs, t - FLOW_WINDOW_S, t)
            if fl != 0 and fwd != 0:
                fx.append(fl); fy.append(fwd)
        if len(fx) >= 20:
            per.append((coin, len(fx), spearman(fx, fy)))
    pos = sum(1 for _, _, r in per if r > 0.05)
    if per:
        wmean = sum(cnt * r for _, cnt, r in per) / sum(cnt for _, cnt, r in per)
        print(f"  >>> WITHIN-market weighted-mean rho = {wmean:+.3f}  (the honest pooled estimate; "
              f"{'~0 => pooled +0.338 was a cross-market artifact' if abs(wmean) < 0.1 else 'real within-market signal'})")
    print(f"  per-market (>=20 active samples): {len(per)} markets, {pos} show rho>+0.05")
    for coin, cnt, r in sorted(per, key=lambda z: -z[1])[:6]:
        print(f"    {coin:14} n={cnt:4}  rho={r:+.3f}")
    # (b) conditional edge magnitude: mean forward move when flow is strongly one-sided
    strong = [(r[1], r[3]) for r in rows if abs(r[1]) > 0.5 and r[3] != 0]
    if strong:
        follow = sum(1 for fl, fwd in strong if (fl > 0) == (fwd > 0)) / len(strong)
        mean_dir = sum((1 if fl > 0 else -1) * fwd for fl, fwd in strong) / len(strong)
        print(f"  strong flow (|imb|>0.5, n={len(strong)}): forward move follows flow {100*follow:.0f}% of the time,")
        print(f"    mean forward move in flow direction = {mean_dir:+.4f} (price units; >0 => flow is followed, tradeable)")
    # (c) binomial CI on the OOS 53%
    from math import sqrt
    nt = sum(1 for r in test if r[1] != 0 and r[3] != 0)
    ht = sum(1 for r in test if r[1] != 0 and r[3] != 0 and ((r[1] > 0) == (r[3] > 0)))
    if nt:
        p = ht / nt; se = sqrt(p * (1 - p) / nt)
        print(f"  OOS hit {100*p:.1f}% ± {100*1.96*se:.1f}% (95% CI, n={nt}) -> "
              f"{'excludes 50% (real)' if p - 1.96*se > 0.5 else 'CI still spans 50% — need more data'}")


if __name__ == "__main__":
    main()
