"""Micro-price calibration v0 (pure numpy; no pandas/scipy).

Fits Stoikov's micro-price adjustment G(imb_l1) per HL HIP-4 outcome coin from
state/book_snapshots/h*.jsonl. Compares three predictors of mid @ t+5s:
    - naive_mid  = mid_t                              (baseline)
    - weighted   = bid + imb_l1 * (ask - bid)         (G = identity)
    - micro      = bid + G_fit(imb_l1) * (ask - bid)  (G fit per coin + universal)

Writes:
    models/microprice_v0.json
    analysis/microprice_v0.md

Read-only w.r.t. live state. numpy-only (venv has no pandas/scipy).
"""
from __future__ import annotations
import json, glob, os, math, sys, datetime as dt
from collections import defaultdict
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SNAP_DIR = os.path.join(ROOT, "state", "book_snapshots")
MODEL_OUT = os.path.join(ROOT, "models", "microprice_v0.json")
REPORT_OUT = os.path.join(ROOT, "analysis", "microprice_v0.md")

FWD_TARGET = 5.0     # seconds
FWD_TOL = 2.0        # seconds tolerance (5 +/- 2)
N_BUCKETS = 10
UNDERFIT_N = 200
GLOBAL_MIN_N = 1000

# --------------- data loading --------------------------------------------

def load_book_snaps():
    """Return dict[coin] -> np.ndarray of shape (n, 6) columns: ts,bid,ask,mid,imb_l1,imb_l5.
    Sorted by ts, deduped on ts (files h*40 and h*41 mirror each other)."""
    rows_by_coin = defaultdict(list)
    for f in sorted(glob.glob(os.path.join(SNAP_DIR, "h*.jsonl"))):
        for line in open(f):
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("event") != "book":
                continue
            try:
                rows_by_coin[d["coin"]].append((
                    float(d["ts"]),
                    float(d["bid"]),
                    float(d["ask"]),
                    float(d["mid"]),
                    float(d["imb_l1"]),
                    float(d.get("imb_l5", d["imb_l1"])),
                ))
            except (KeyError, TypeError, ValueError):
                continue
    out = {}
    for coin, rows in rows_by_coin.items():
        arr = np.array(rows, dtype=float)
        # sort by ts, dedupe
        order = np.argsort(arr[:, 0])
        arr = arr[order]
        _, uniq_idx = np.unique(arr[:, 0], return_index=True)
        arr = arr[np.sort(uniq_idx)]
        out[coin] = arr
    return out

# --------------- forward pairs -------------------------------------------

def build_pairs(arr: np.ndarray) -> np.ndarray:
    """Return (m, 7) array: ts, bid, ask, mid, imb_l1, spread, mid_next.
    Only rows with a forward match in [FWD_TARGET-FWD_TOL, FWD_TARGET+FWD_TOL]
    and with positive spread."""
    if len(arr) < 2:
        return np.zeros((0, 7))
    ts = arr[:, 0]
    n = len(arr)
    lo, hi = FWD_TARGET - FWD_TOL, FWD_TARGET + FWD_TOL
    rows = []
    j = 1
    for i in range(n):
        target = ts[i] + FWD_TARGET
        if j <= i:
            j = i + 1
        while j < n and ts[j] < ts[i] + lo:
            j += 1
        best = -1
        best_err = 1e18
        k = j
        while k < n and ts[k] <= ts[i] + hi:
            err = abs(ts[k] - target)
            if err < best_err:
                best_err = err
                best = k
            k += 1
        if best < 0:
            continue
        bid = arr[i, 1]; ask = arr[i, 2]
        if ask <= bid:
            continue
        rows.append((
            ts[i], bid, ask, arr[i, 3], arr[i, 4], ask - bid, arr[best, 3],
        ))
    if not rows:
        return np.zeros((0, 7))
    return np.array(rows, dtype=float)

# --------------- fit primitives ------------------------------------------

def logistic(x, k):
    return 1.0 / (1.0 + np.exp(-k * (x - 0.5)))

def mse_logistic(k, imb, target_g):
    pred = logistic(imb, k)
    e = pred - target_g
    return float(np.mean(e * e))

def golden_section_min(f, a, b, tol=1e-4, maxit=200):
    """Golden-section search for minimum of scalar f on [a,b]."""
    phi = (math.sqrt(5) - 1) / 2  # ~0.618
    c = b - phi * (b - a)
    d = a + phi * (b - a)
    fc = f(c); fd = f(d)
    for _ in range(maxit):
        if abs(b - a) < tol:
            break
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - phi * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + phi * (b - a)
            fd = f(d)
    xmin = 0.5 * (a + b)
    return xmin, f(xmin)

def fit_logistic_k(imb: np.ndarray, target_g: np.ndarray):
    """Fit k in G(x) = 1/(1+exp(-k(x-0.5))) minimizing MSE vs target_g in [0,1]-ish."""
    if len(imb) < 20:
        return None
    # bracket over a wide range; k~0 means flat 0.5, k large means step
    def f(k): return mse_logistic(k, imb, target_g)
    # coarse scan first
    grid = np.linspace(0.0, 20.0, 41)
    vals = [f(k) for k in grid]
    i = int(np.argmin(vals))
    lo = grid[max(0, i - 1)]; hi = grid[min(len(grid) - 1, i + 1)]
    k_star, _ = golden_section_min(f, max(0.0, lo), hi)
    return float(k_star)

def bucket_G(pairs: np.ndarray, n_buckets=N_BUCKETS):
    """Non-parametric G: bucket imb_l1, mean of (mid_next - bid)/(ask - bid)."""
    if len(pairs) == 0:
        return {"edges": [], "centers": [], "means": [], "counts": []}
    imb = pairs[:, 4]
    y = (pairs[:, 6] - pairs[:, 1]) / pairs[:, 5]
    y = np.clip(y, -0.5, 1.5)
    edges = np.linspace(0.0, 1.0, n_buckets + 1)
    centers = 0.5 * (edges[:-1] + edges[1:])
    means = [None] * n_buckets
    counts = [0] * n_buckets
    for b in range(n_buckets):
        lo, hi = edges[b], edges[b + 1]
        if b == n_buckets - 1:
            mask = (imb >= lo) & (imb <= hi)
        else:
            mask = (imb >= lo) & (imb < hi)
        counts[b] = int(mask.sum())
        if counts[b] > 0:
            means[b] = float(y[mask].mean())
    return {
        "edges": edges.tolist(),
        "centers": centers.tolist(),
        "means": means,
        "counts": counts,
    }

def eval_predictors(pairs: np.ndarray, k_fit, bucket_lut: dict):
    bid = pairs[:, 1]; ask = pairs[:, 2]; mid = pairs[:, 3]
    imb = pairs[:, 4]; spread = pairs[:, 5]; mid_next = pairs[:, 6]

    def rmse(pred):
        e = pred - mid_next
        return float(np.sqrt(np.mean(e * e)))

    out = {
        "n": int(len(pairs)),
        "rmse_naive": rmse(mid),
        "rmse_weighted": rmse(bid + imb * spread),
    }
    if k_fit is not None:
        out["rmse_micro_logistic"] = rmse(bid + logistic(imb, k_fit) * spread)
    edges = np.array(bucket_lut["edges"])
    means = bucket_lut["means"]
    idx = np.clip(np.digitize(imb, edges) - 1, 0, N_BUCKETS - 1)
    g_bucket = np.array([
        means[i] if (i < len(means) and means[i] is not None) else imb[k]
        for k, i in enumerate(idx)
    ])
    out["rmse_micro_bucket"] = rmse(bid + g_bucket * spread)
    return out

# --------------- driver --------------------------------------------------

def main():
    snaps = load_book_snaps()
    coins = sorted(snaps.keys())
    print(f"[microprice_v0] loaded {len(coins)} coins", file=sys.stderr)

    per_coin_pairs = {}
    total_pairs = 0
    for coin in coins:
        pairs = build_pairs(snaps[coin])
        per_coin_pairs[coin] = pairs
        total_pairs += len(pairs)
        print(f"  {coin}: {len(pairs)} fwd pairs", file=sys.stderr)

    result = {
        "version": "v0",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "fwd_target_sec": FWD_TARGET,
        "fwd_tol_sec": FWD_TOL,
        "n_buckets": N_BUCKETS,
        "n_coins": len(coins),
        "n_pairs_total": total_pairs,
        "per_coin": {},
        "universal": None,
        "notes": [],
    }

    if total_pairs < GLOBAL_MIN_N:
        result["notes"].append(
            f"UNDERPOWERED: only {total_pairs} pairs total across all coins "
            f"(threshold {GLOBAL_MIN_N}); skipping per-coin fits per spec."
        )
        all_pairs = np.vstack([p for p in per_coin_pairs.values() if len(p)])
        if len(all_pairs):
            g_target = np.clip(
                (all_pairs[:, 6] - all_pairs[:, 1]) / all_pairs[:, 5], -0.5, 1.5
            )
            k_uni = fit_logistic_k(all_pairs[:, 4], g_target)
            bucket = bucket_G(all_pairs)
            metrics = eval_predictors(all_pairs, k_uni, bucket)
            result["universal"] = {
                "k_logistic": k_uni,
                "bucket": bucket,
                "metrics": metrics,
                "rmse_reduction_pct_vs_naive": (
                    100 * (metrics["rmse_naive"] - min(
                        metrics.get("rmse_micro_logistic", metrics["rmse_naive"]),
                        metrics["rmse_micro_bucket"],
                    )) / metrics["rmse_naive"]
                ) if metrics["rmse_naive"] > 0 else 0.0,
            }
        _dump(result)
        write_report(result)
        return result

    # per-coin fits
    for coin, pairs in per_coin_pairs.items():
        if len(pairs) == 0:
            result["per_coin"][coin] = {"n": 0, "note": "no forward pairs"}
            continue
        g_target = np.clip((pairs[:, 6] - pairs[:, 1]) / pairs[:, 5], -0.5, 1.5)
        k = fit_logistic_k(pairs[:, 4], g_target)
        bucket = bucket_G(pairs)
        metrics = eval_predictors(pairs, k, bucket)
        entry = {
            "n": int(len(pairs)),
            "k_logistic": k,
            "bucket": bucket,
            "metrics": metrics,
            "underfit": bool(len(pairs) < UNDERFIT_N),
        }
        if metrics["rmse_naive"] > 0:
            entry["rmse_reduction_pct_vs_naive"] = 100 * (
                metrics["rmse_naive"] - min(
                    metrics.get("rmse_micro_logistic", metrics["rmse_naive"]),
                    metrics["rmse_micro_bucket"],
                )
            ) / metrics["rmse_naive"]
        result["per_coin"][coin] = entry

    # universal fit over pooled data
    all_pairs = np.vstack([p for p in per_coin_pairs.values() if len(p)])
    g_target = np.clip((all_pairs[:, 6] - all_pairs[:, 1]) / all_pairs[:, 5], -0.5, 1.5)
    k_uni = fit_logistic_k(all_pairs[:, 4], g_target)
    bucket_uni = bucket_G(all_pairs)
    metrics_uni = eval_predictors(all_pairs, k_uni, bucket_uni)
    result["universal"] = {
        "k_logistic": k_uni,
        "bucket": bucket_uni,
        "metrics": metrics_uni,
        "rmse_reduction_pct_vs_naive": (
            100 * (metrics_uni["rmse_naive"] - min(
                metrics_uni.get("rmse_micro_logistic", metrics_uni["rmse_naive"]),
                metrics_uni["rmse_micro_bucket"],
            )) / metrics_uni["rmse_naive"]
        ) if metrics_uni["rmse_naive"] > 0 else 0.0,
    }
    _dump(result)
    write_report(result)
    return result

def _dump(result):
    with open(MODEL_OUT, "w") as f:
        json.dump(result, f, indent=2)

def write_report(result: dict):
    lines = []
    lines.append("# Micro-price calibration v0")
    lines.append("")
    lines.append(f"- generated_at_utc: {result['generated_at_utc']}")
    lines.append(f"- fwd horizon: {result['fwd_target_sec']}s (+/- {result['fwd_tol_sec']}s)")
    lines.append(f"- n_buckets: {result['n_buckets']}")
    lines.append(f"- n coins: {result['n_coins']}")
    lines.append(f"- n forward pairs total: {result['n_pairs_total']}")
    for note in result.get("notes", []):
        lines.append(f"- NOTE: {note}")
    lines.append("")
    uni = result.get("universal")
    if uni:
        m = uni["metrics"]
        lines.append("## Universal fit (all coins pooled)")
        lines.append("")
        lines.append(f"- n: {m['n']}")
        k_uni = uni.get("k_logistic")
        lines.append(f"- k_logistic: {k_uni:.4f}" if k_uni is not None else "- k_logistic: (fit failed)")
        lines.append(f"- RMSE naive mid : {m['rmse_naive']:.6g}")
        lines.append(f"- RMSE weighted  : {m['rmse_weighted']:.6g}   (G = identity)")
        if "rmse_micro_logistic" in m:
            lines.append(f"- RMSE micro-log : {m['rmse_micro_logistic']:.6g}   (G = logistic(k))")
        lines.append(f"- RMSE micro-bkt : {m['rmse_micro_bucket']:.6g}   (G = 10-bucket LUT)")
        red = uni.get("rmse_reduction_pct_vs_naive", 0.0)
        lines.append(f"- best RMSE reduction vs naive: **{red:.3f}%**")
        lines.append("")
        lines.append("### Bucket LUT (universal)")
        lines.append("| bucket (imb_l1 center) | n | mean G |")
        lines.append("|---:|---:|---:|")
        for c, n, mval in zip(uni["bucket"]["centers"], uni["bucket"]["counts"], uni["bucket"]["means"]):
            mstr = f"{mval:.4f}" if mval is not None else "-"
            lines.append(f"| {c:.2f} | {n} | {mstr} |")
        lines.append("")
    if result["per_coin"]:
        lines.append("## Per-coin summary")
        lines.append("")
        lines.append("| coin | n | underfit | k_logistic | RMSE naive | RMSE weighted | RMSE micro-bkt | reduction% |")
        lines.append("|---|---:|:---:|---:|---:|---:|---:|---:|")
        for coin, e in sorted(result["per_coin"].items()):
            if e.get("n", 0) == 0:
                lines.append(f"| {coin} | 0 | - | - | - | - | - | - |")
                continue
            m = e["metrics"]
            k = e.get("k_logistic")
            kstr = f"{k:.3f}" if k is not None else "-"
            uf = "YES" if e.get("underfit") else "no"
            red = e.get("rmse_reduction_pct_vs_naive", 0.0)
            lines.append(
                f"| {coin} | {e['n']} | {uf} | {kstr} | {m['rmse_naive']:.5g} | "
                f"{m['rmse_weighted']:.5g} | {m['rmse_micro_bucket']:.5g} | {red:.3f} |"
            )
        lines.append("")

    # Verdict
    lines.append("## Verdict")
    lines.append("")
    n = result["n_pairs_total"]
    uni_red = (result.get("universal") or {}).get("rmse_reduction_pct_vs_naive", 0.0)
    uf_coins = sum(1 for e in result["per_coin"].values() if e.get("underfit"))
    if n < GLOBAL_MIN_N:
        verdict = "Not enough data"
        reason = (
            f"Only {n} forward pairs total (need >= {GLOBAL_MIN_N} for per-coin fits). "
            f"Snapshot cadence ~5s per coin, so ~12/min/coin; wait ~24h to hit ~17k pairs."
        )
    elif uni_red < 1.0:
        verdict = "Killed"
        reason = (
            f"Universal micro-price beats naive mid by only {uni_red:.3f}% RMSE. "
            "Weighted mid is essentially tied. imb_l1 at 5s horizon carries no exploitable signal in this window."
        )
    elif uni_red < 5.0:
        verdict = "Ship v0, retrain in N days"
        reason = (
            f"Universal reduction {uni_red:.3f}% is real but small. "
            f"{uf_coins}/{result['n_coins']} coins are underfit (n<{UNDERFIT_N}); "
            "use universal k for those and per-coin LUT for the well-sampled ones. Retrain weekly."
        )
    else:
        verdict = "Ship it"
        reason = (
            f"Universal reduction {uni_red:.3f}% RMSE vs naive is meaningful. "
            f"Per-coin k varies; prefer per-coin LUT where n>={UNDERFIT_N}, universal elsewhere."
        )
    lines.append(f"**{verdict}** -- {reason}")
    lines.append("")
    lines.append("## Interface (for consumers)")
    lines.append("")
    lines.append("```")
    lines.append("input:  bid, ask, imb_l1  (imb_l1 = bid_l1/(bid_l1+ask_l1), in [0,1])")
    lines.append("output: micro_px = bid + G(imb_l1) * (ask - bid)")
    lines.append("        where G is per-coin logistic k (fallback universal),")
    lines.append("        or 10-bucket LUT (piecewise-constant) for robustness.")
    lines.append("failure: if imb_l1 missing or spread<=0 -> return mid_t.")
    lines.append("kill-switch: config flag mm.use_microprice: false -> use mid_t.")
    lines.append("```")
    lines.append("")
    with open(REPORT_OUT, "w") as f:
        f.write("\n".join(lines))

if __name__ == "__main__":
    r = main()
    n = r["n_pairs_total"]
    uni = r.get("universal") or {}
    red = uni.get("rmse_reduction_pct_vs_naive", 0.0)
    m = uni.get("metrics") or {}
    print(f"n_pairs_total={n}", file=sys.stderr)
    print(
        f"universal RMSE naive={m.get('rmse_naive')} "
        f"bucket={m.get('rmse_micro_bucket')} log={m.get('rmse_micro_logistic')}",
        file=sys.stderr,
    )
    print(f"universal reduction_vs_naive={red:.4f}%", file=sys.stderr)
