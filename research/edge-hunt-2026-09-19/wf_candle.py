import json, os, math
import numpy as np

D = "/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
uni = [u[0] for u in json.load(open(D + "/universe.json"))]
HOR = [1, 2, 5, 10, 30]
LOOK = 1440  # trailing window (1 day of 1m bars) for percentile -> no look-ahead


def load(c):
    fp = f"{D}/{c}_1m.json"
    if not os.path.exists(fp):
        return None
    a = np.array(json.load(open(fp)), dtype=float)
    return a  # t,o,h,l,c,v,n


def stats(x, label, n_extra=""):
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 5:
        return f"{label:28s} n={n} (too few)"
    m = x.mean(); s = x.std(ddof=1)
    t = m / (s / math.sqrt(n))
    return f"{label:28s} n={n:6d}  mean={m:+8.2f}bp  sd={s:7.1f}  t={t:+6.2f}  med={np.median(x):+7.2f} {n_extra}"


def run(metric, pct, tag):
    res = {h: [] for h in HOR}
    percoin = {}
    nev = 0
    for c in uni:
        a = load(c)
        if a is None or len(a) < LOOK + 100:
            continue
        t, o, hi, lo, cl, v, ntr = a[:, 0], a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5], a[:, 6]
        ntl = v * cl
        if metric == "vol":
            m = ntl
        elif metric == "avgfill":
            m = np.where(ntr > 0, ntl / np.maximum(ntr, 1), 0.0)
        elif metric == "ntrades":
            m = ntr.astype(float)
        ev = []
        for i in range(LOOK, len(a) - max(HOR) - 1):
            # gap check: bars contiguous?
            if t[i + 1] - t[i] != 60000:
                continue
            thr = np.percentile(m[i - LOOK:i], pct)   # strictly past data
            if m[i] <= thr:
                continue
            d = cl[i] - o[i]
            if d == 0:
                continue
            sgn = 1.0 if d > 0 else -1.0
            entry = o[i + 1]                          # first observable, post-signal
            if entry <= 0:
                continue
            ev.append(i)
            for h in HOR:
                j = i + h
                if t[j] - t[i + 1] != (h - 1) * 60000:
                    continue
                r = sgn * (cl[j] - entry) / entry * 1e4
                res[h].append(r)
                percoin.setdefault(c, {}).setdefault(h, []).append(r)
        nev += len(ev)
    print(f"\n=== {tag}  (metric={metric}, top {100-pct:g}%, sign=candle direction, entry=next bar open) ===")
    print(f"events={nev}")
    for h in HOR:
        print("  +%2dm  %s" % (h, stats(res[h], "")))
    return res, percoin


if __name__ == "__main__":
    run("vol", 99.0, "VOLUME SPIKE momentum")
    run("avgfill", 99.0, "LARGE-AVG-FILL spike momentum")
    run("avgfill", 99.9, "LARGE-AVG-FILL top0.1% momentum")
    run("vol", 99.9, "VOLUME top0.1% momentum")
