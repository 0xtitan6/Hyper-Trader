# scalp-lead-lag — Does BTC/ETH/HYPE lead altcoins on HL at 1-5m?

Bar: 9 bp round-trip taker (0.045% each way). Effect must exceed that PER TRADE.

## Data situation (checked first)
`data/*_1m_long.json` already existed for my exact 20 coins BUT only covers
**3.6 days (~5,150 minutes)**, not the 30 days the fetch script intended.
Cause: `fetch_hist1m.py` pages backwards via `end=min(rows)-60000`, but HL's
`candleSnapshot` caps the response and the loop re-received the same recent
window each time, so the dedupe dict never grew. Documenting so nobody trusts
those files as 30d.

Action: re-fetch with verified backward pagination (test below).

## HARD DATA CONSTRAINT (kills the "30-60 days of 1m" plan)
HL `candleSnapshot` on `interval:"1m"` returns **at most ~5,190 rows and will not go
back further than ~3.6 days**, regardless of `startTime`:

```
req 60d wide -> rows 5190  09-15 12:44 .. 09-19 03:13
req 30d wide -> rows 5190  09-15 12:44 .. 09-19 03:13
req 10d wide -> rows 5190  09-15 12:44 .. 09-19 03:13
req  4d wide -> rows 5190  09-15 12:44 .. 09-19 03:13
```
And an explicit historical window returns nothing:
`{"coin":"BTC","interval":"1m","startTime":now-20d,"endTime":now-19d}` -> **rows 0**.

So 30-60 days of 1m candles is NOT obtainable from this API. Available:
1m = 3.6d, 5m = ~17d, 5000 bars, 15m = ~52d, 5000 bars.
I ran 1m over the 3.48d contiguous aligned window (**n = 5,010 minute-returns per
coin, 20 coins**) and used 5m/15m as an independent longer out-of-sample check.

Scripts: `ll_candle.py` (corr + naive trade), `ll_clustered.py` (honest sample size),
`ll_bbo.py` (live sub-minute BBO collector), `ll_subminute.py`.

## Result 1 — contemporaneous corr is large, lag-1 corr is ~zero
`corr(r_leader[t-k], r_alt[t])`, 1m log returns, N=5,010. Null 95% band = +/-0.0277.

| pair | k=0 | k=1 | k=2 | k=3 | k=4 | k=5 |
|---|---|---|---|---|---|---|
| HYPE->LTC  | +0.3412 | **+0.1446** | -0.0163 | -0.0057 | +0.0289 | +0.0117 |
| HYPE->AVAX | +0.4178 | **+0.1184** | -0.0141 | +0.0260 | +0.0158 | +0.0255 |
| HYPE->BNB  | +0.4699 | **+0.1164** | +0.0071 | +0.0210 | +0.0042 | +0.0093 |
| ETH->INJ   | +0.3877 | **+0.1045** | -0.0167 | +0.0420 | +0.0090 | -0.0317 |
| HYPE->INJ  | +0.2887 | +0.0973 | -0.0193 | +0.0261 | +0.0215 | -0.0034 |
| HYPE->AAVE | +0.4620 | +0.0629 | +0.0037 | +0.0223 | +0.0207 | +0.0181 |
| ETH->ARB   | +0.3192 | +0.0290 | -0.0188 | +0.0218 | -0.0121 | -0.0052 |
| HYPE->ARB  | +0.2412 | +0.0047 | -0.0282 | +0.0093 | -0.0184 | +0.0037 |

k=0 is 0.24-0.65. k=1 is 0.00-0.14, i.e. **k=1 explains r^2 = 0.02% to 2.1% of alt
variance** vs 6-42% contemporaneously. k>=2 is inside the noise band everywhere.
Contemporaneous correlation is NOT lead-lag. The lead-lag component is ~1/20th the
size of the co-movement component.

## Result 2 — the naive trade "works", and it is pseudo-replication
Trade: leader moves >= thr bps in bar t; at the bar boundary (when you first know it)
enter the alt at bar t+1 OPEN, taker; exit at bar t+h CLOSE, taker. Cost 9 bp.

Pooling 19 alts per event gives big t-stats. But the alts are 0.24-0.65 correlated with
each other contemporaneously, so 19 alt-rows at one BTC spike is ~**1 draw, not 19**.
Re-running with one equal-weight-basket observation per event:

| leader | thr | h | naive n | naive t | **events** | bp | **clustered t** | net vs 9bp |
|---|---|---|---|---|---|---|---|---|
| BTC | 20 | 2 | 1140 | +6.93 | **60** | +9.41 | **+1.84** | +0.41 |
| BTC | 20 | 5 | 1140 | +7.65 | **60** | +20.80 | **+1.98** | +11.80 |
| ETH | 40 | 1 | 418 | +5.60 | **22** | +9.75 | **+1.52** | +0.75 |
| ETH | 40 | 5 | 418 | +5.07 | **22** | +29.68 | **+1.25** | +20.68 |
| ETH | 30 | 5 | 969 | +4.55 | **51** | +14.67 | **+1.16** | +5.67 |
| HYPE | 40 | 5 | 1083 | +4.38 | **57** | +10.11 | **+1.15** | +1.11 |
| HYPE | 30 | 1 | 2641 | +6.72 | **139** | +3.05 | **+1.99** | -5.95 |
| BTC | 40 | 2 | 152 | -3.65 | **8** | -11.31 | **-1.06** | -20.31 |
| BTC | 40 | 5 | 152 | -3.60 | **8** | -22.53 | **-0.96** | -31.53 |

**Not one cell reaches clustered t = 2.0.** The naive t-stats were inflated ~4x purely
by counting correlated alts as independent observations.

It is also non-monotonic in threshold, which a real effect would not be: BTC thr=20 h=5
is **+20.8 bp** but BTC thr=40 h=5 is **-22.5 bp** (bigger signal, opposite sign).

And the events are not spread across the window — BTC |r|>=20bp, 60 events total:
```
day 20711: 20 events
day 20712: 27 events
day 20714: 12 events
day 20715:  1 event
```
47 of 60 on two days. This is 2-3 market moves, not 60 independent trials.

## Result 3 — beta-shortfall catch-up: real sign, wrong direction, too small
shortfall_t = beta*r_L[t] - r_A[t] (alt under-reacted). Trade sign(shortfall):

| leader | pct | h | naive n | bp | naive t |
|---|---|---|---|---|---|
| BTC | 95 | 1 | 4765 | **-1.52** | -4.42 |
| BTC | 95 | 2 | 4764 | **-1.70** | -3.48 |
| HYPE | 95 | 2 | 4766 | **-2.59** | -5.15 |
| HYPE | 90 | 2 | 9512 | -1.47 | -4.70 |
| ETH | 95 | 2 | 4766 | -1.61 | -3.30 |

Consistently NEGATIVE across all 3 leaders x 4 percentiles x 2 horizons (24/24 cells),
monotone in percentile. So alts do **not** catch up to the leader — they continue away
from it. Trading the reverse gives +1.5 to +2.6 bp gross, **still 6-7 bp short of the
9 bp bar**, and that is before the pseudo-replication haircut.
