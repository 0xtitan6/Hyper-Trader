# Adverse-Selection Scoring v0

Generated: 2026-09-25T00:26:52.220933Z

## Method

For each `own_fill`, look up the forward mid at ts_fill + horizon and compute mark-out in bps. Positive = mid moved in our favor (we captured edge). Negative = we got picked off.

- HIP-4 outcomes (`#nnn`): forward mid from `state/book_snapshots/h<coin>.jsonl` at t+30s (+/- 10s tolerance).
- Base perps (BTC/ETH/...): 1m candle close containing t+60s (fallback: next candle open within 60s).
- HIP-3 (`xyz:*`, `para:*`): no market-data source in `state/candles/` or `state/book_snapshots/` -> **all skipped**.

## Input coverage

- Total `own_fill` events: **288**
- Matched per class: `{'base_perp': 7}`
- Skipped per class: `{'hip3_perp': 80, 'base_perp': 22, 'hip4_outcome': 179}`
- Skip reasons: `{'hip3_no_market_data': 80, 'base_perp_no_forward_candle': 22, 'outcome_no_forward_snapshot': 179}`

The book_snapshot window is ~22 minutes (2026-09-25 window); nearly all outcome fills fall outside it.
HIP-3 has no market data on disk, so all HIP-3 fills are excluded from this pass.

## Per-class mark-out (bps)

| class | n | mean | 95% CI | median | std | frac negative |
|---|---:|---:|---|---:|---:|---:|
| base_perp | 7 | -3.84 | [-15.45, 7.77] | -13.83 | 15.67 | 0.571 |
| hip3_perp | 0 | n/a | n/a | n/a | n/a | n/a |
| hip4_outcome | 0 | n/a | n/a | n/a | n/a | n/a |

## Pooled hour-of-day (UTC)

| hour | n | mean | median | std | frac negative |
|---:|---:|---:|---:|---:|---:|
| 13 | 1 | -13.83 | -13.83 | 0.00 | 1.000 |
| 14 | 1 | -15.16 | -15.16 | 0.00 | 1.000 |
| 17 | 3 | 12.09 | 10.89 | 8.19 | 0.000 |
| 20 | 2 | -17.07 | -17.07 | 0.00 | 1.000 |

## Per-coin (n >= 3)

| coin | n | mean | median | std | frac neg |
|---|---:|---:|---:|---:|---:|
| HYPE | 3 | -8.14 | -13.83 | 11.02 | 0.667 |
| ZEC | 4 | -0.61 | -3.09 | 19.44 | 0.500 |

## Top-5 most adversely-selected matched fills

| coin | class | ts (UTC) | side | px | mid_after | mark_out_bps |
|---|---|---|---|---:|---:|---:|
| ZEC | base_perp | 2026-09-21T20:42:16.950551 | B | 1464.500000 | 1462.000000 | -17.07 |
| ZEC | base_perp | 2026-09-21T20:42:16.977896 | B | 1464.500000 | 1462.000000 | -17.07 |
| HYPE | base_perp | 2026-09-21T14:05:40.084244 | B | 94.313000 | 94.170000 | -15.16 |
| HYPE | base_perp | 2026-09-21T13:22:49.994889 | B | 95.422000 | 95.290000 | -13.83 |
| HYPE | base_perp | 2026-09-21T17:54:47.260896 | B | 92.054000 | 92.096000 | 4.56 |

## Verdict

**Coverage is the dominant finding.** The `state/book_snapshots/` archive spans only ~22 minutes, so the 179 HIP-4 outcome fills reduce to a handful of matches. There are no candles for HIP-3 markets on disk, so all 80 HIP-3 fills are unmatched. Only base-perp fills against 1-minute HL candles give us any real sample and even those are shallow.

- **base_perp** (7 fills): mean -3.84 bps, 95% CI [-15.45, 7.77] — CI straddles zero, inconclusive.
- **hip3_perp**: 0 matched, no verdict possible.
- **hip4_outcome**: 0 matched, no verdict possible.

**Actionable:** the only way to make this analysis load-bearing is to backfill more book-snapshot coverage (outcomes) and stream L2/mids for `xyz:*` and `para:*` (the two classes where we take the most flow: 44 fills on `xyz:SKHX` and 24 on `para:VST`). Until then, treat any per-class number here as directional at best.
