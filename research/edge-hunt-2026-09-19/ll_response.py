"""Impulse-response: when a leader jumps, how much of the alt's response is ALREADY
DONE by the time you could possibly act, and how much is left to capture?

This is the question 1m candles cannot answer. Bins of 250ms from BBO mids.
"""
import json, math, sys
import numpy as np

D = "/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/data"
FILE = sys.argv[1] if len(sys.argv) > 1 else "ll_bbo.jsonl"
BIN_MS = int(sys.argv[2]) if len(sys.argv) > 2 else 250
THR = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0
LEADERS = ["BTC", "ETH", "HYPE"]

rows = [json.loads(l) for l in open(D + "/" + FILE)]
coins = sorted({r[0] for r in rows})
t0 = min(r[1] for r in rows); t1 = max(r[1] for r in rows)
nb = int((t1 - t0) // BIN_MS) + 1
print(f"{FILE}: {len(rows)} updates, {(t1-t0)/60000:.1f} min, {len(coins)} coins, "
      f"bin={BIN_MS}ms, nbins={nb}")

spread = {}
mid = {}
for c in coins:
    arr = np.full(nb, np.nan)
    sp = []
    for r in rows:
        if r[0] != c:
            continue
        m = (r[2] + r[3]) / 2
        arr[int((r[1] - t0) // BIN_MS)] = m
        sp.append((r[3] - r[2]) / m * 1e4)
    spread[c] = float(np.median(sp))
    last = np.nan
    for i in range(nb):
        if np.isnan(arr[i]):
            arr[i] = last
        else:
            last = arr[i]
    mid[c] = arr
ok = ~np.isnan(np.vstack([mid[c] for c in coins])).any(axis=0)
first = int(np.argmax(ok))
G = {c: mid[c][first:] for c in coins}
n = len(G[coins[0]])
R = {c: np.diff(np.log(G[c])) * 1e4 for c in coins}
N = n - 1

HS = list(range(0, 41))          # bins after the signal bin
print(f"\n=== impulse response to leader 1-bin move >= {THR} bp "
      f"({BIN_MS}ms bins) ===")
print("cum[h] = signed alt move from the START of the leader's signal bin to h bins after it")
print("EXECUTABLE = cum[h] - cum[0]  (cum[0] is already gone when you see the signal)\n")
for L in LEADERS:
    if L not in R:
        continue
    rl = R[L]
    alts = [a for a in coins if a != L]
    idx = [i for i in range(1, N - max(HS) - 1) if abs(rl[i]) >= THR]
    if len(idx) < 10:
        print(f"{L}: only {len(idx)} events at thr={THR}, skip")
        continue
    # cum[h] per event, EW basket across alts
    cum = np.full((len(idx), len(HS)), np.nan)
    for ii, i in enumerate(idx):
        sgn = 1.0 if rl[i] > 0 else -1.0
        per_alt = np.full((len(alts), len(HS)), np.nan)
        for j, A in enumerate(alts):
            g = G[A]
            base = g[i]                       # price at START of signal bin
            if base <= 0:
                continue
            for hi, h in enumerate(HS):
                per_alt[j, hi] = sgn * (g[i + h] - base) / base * 1e4
        cum[ii] = np.nanmean(per_alt, axis=0)
    mean = np.nanmean(cum, axis=0)
    se = np.nanstd(cum, axis=0, ddof=1) / math.sqrt(len(idx))
    tot = mean[-1]
    print(f"--- leader {L}: {len(idx)} events, alts={len(alts)} ---")
    print(f"{'h bins':>7} {'h ms':>7} {'cum bp':>8} {'+/-se':>7} {'% of total':>11} "
          f"{'EXECUTABLE bp':>14} {'t':>6}")
    for hi, h in enumerate(HS):
        if h not in (0, 1, 2, 4, 8, 12, 20, 40):
            continue
        ex = mean[hi] - mean[1]
        exs = np.nanstd(cum[:, hi] - cum[:, 1], ddof=1) / math.sqrt(len(idx))
        print(f"{h:>7} {h*BIN_MS:>7} {mean[hi]:>+8.3f} {se[hi]:>7.3f} "
              f"{(mean[hi]/tot*100 if tot else float('nan')):>10.1f}% "
              f"{ex:>+14.3f} {(ex/exs if exs else float('nan')):>+6.2f}")
    med_alt_cost = 9.0 + np.median([spread[a] for a in alts])
    best_ex = max(mean[hi] - mean[1] for hi in range(len(HS)))
    print(f"    best executable over any horizon <= {max(HS)*BIN_MS}ms: "
          f"{best_ex:+.3f} bp")
    print(f"    median alt TRUE round-trip cost: {med_alt_cost:.2f} bp  -> "
          f"NET {best_ex - med_alt_cost:+.2f} bp")
    print(f"    alt co-move DURING the leader's own bin (already gone when you "
          f"see it): {mean[1]:+.3f} bp = "
          f"{(mean[1]/tot*100 if tot else float('nan')):.1f}% of total\n")
