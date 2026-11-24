# Micro-price calibration v0

- generated_at_utc: 2026-09-25T00:27:42.595145+00:00
- fwd horizon: 5.0s (+/- 2.0s)
- n_buckets: 10
- n coins: 20
- n forward pairs total: 2816

## Universal fit (all coins pooled)

- n: 2816
- k_logistic: 0.0280
- RMSE naive mid : 0.00200367
- RMSE weighted  : 0.00257297   (G = identity)
- RMSE micro-log : 0.00200304   (G = logistic(k))
- RMSE micro-bkt : 0.00200308   (G = 10-bucket LUT)
- best RMSE reduction vs naive: **0.031%**

### Bucket LUT (universal)
| bucket (imb_l1 center) | n | mean G |
|---:|---:|---:|
| 0.05 | 72 | 0.5000 |
| 0.15 | 266 | 0.5000 |
| 0.25 | 293 | 0.4929 |
| 0.35 | 636 | 0.5009 |
| 0.45 | 297 | 0.4979 |
| 0.55 | 326 | 0.5019 |
| 0.65 | 356 | 0.4998 |
| 0.75 | 212 | 0.5094 |
| 0.85 | 291 | 0.5004 |
| 0.95 | 67 | 0.5000 |

## Per-coin summary

| coin | n | underfit | k_logistic | RMSE naive | RMSE weighted | RMSE micro-bkt | reduction% |
|---|---:|:---:|---:|---:|---:|---:|---:|
| #14740 | 127 | YES | 0.000 | 0 | 3.4073e-06 | 0 | 0.000 |
| #14741 | 127 | YES | 0.000 | 0 | 3.4073e-06 | 0 | 0.000 |
| #43260 | 127 | YES | 0.000 | 0 | 5.634e-06 | 0 | 0.000 |
| #43261 | 127 | YES | 0.000 | 0 | 5.634e-06 | 0 | 0.000 |
| #43470 | 127 | YES | 0.133 | 6.5157e-05 | 0.00036384 | 6.8228e-05 | -2.502 |
| #43471 | 127 | YES | 0.133 | 6.5157e-05 | 0.00036384 | 6.8228e-05 | -2.502 |
| #44650 | 265 | no | 0.000 | 0 | 1.5041e-06 | 0 | 0.000 |
| #44710 | 127 | YES | 0.000 | 4.4368e-07 | 0.0020841 | 4.3669e-07 | 1.575 |
| #44711 | 127 | YES | 0.000 | 4.4368e-07 | 0.0020841 | 4.3669e-07 | 1.575 |
| #44730 | 127 | YES | 0.000 | 4.4368e-07 | 0.0032007 | 4.3646e-07 | 1.626 |
| #44750 | 127 | YES | 0.000 | 0 | 0.0007968 | 0 | 0.000 |
| #44751 | 127 | YES | 0.000 | 0 | 0.0007968 | 0 | 0.000 |
| #44850 | 127 | YES | 0.000 | 0 | 0.00072776 | 0 | 0.000 |
| #44851 | 127 | YES | 0.000 | 0 | 0.00072776 | 0 | 0.000 |
| #44950 | 127 | YES | 0.000 | 0.0001374 | 0.00073043 | 0.00013285 | 3.312 |
| #45130 | 127 | YES | 0.148 | 0.0066705 | 0.0071319 | 0.0066132 | 0.859 |
| #45131 | 127 | YES | 0.148 | 0.0066705 | 0.0071319 | 0.0064573 | 3.196 |
| #45160 | 265 | no | 0.000 | 0 | 1.0104e-06 | 0 | 0.000 |
| #45190 | 127 | YES | 0.000 | 0 | 9.318e-07 | 0 | 0.000 |
| #46620 | 127 | YES | 0.000 | 0 | 0.004796 | 0 | 0.000 |

## Verdict

**Killed** -- Universal micro-price beats naive mid by only 0.031% RMSE. Weighted mid is essentially tied. imb_l1 at 5s horizon carries no exploitable signal in this window.

## Interface (for consumers)

```
input:  bid, ask, imb_l1  (imb_l1 = bid_l1/(bid_l1+ask_l1), in [0,1])
output: micro_px = bid + G(imb_l1) * (ask - bid)
        where G is per-coin logistic k (fallback universal),
        or 10-bucket LUT (piecewise-constant) for robustness.
failure: if imb_l1 missing or spread<=0 -> return mid_t.
kill-switch: config flag mm.use_microprice: false -> use mid_t.
```
