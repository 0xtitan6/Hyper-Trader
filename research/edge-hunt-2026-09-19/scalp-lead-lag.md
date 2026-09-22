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

## Result 4 — out-of-sample on longer windows: the 1m "winners" do not replicate
Same event-clustered trade at 5m (17.4 days, 5x more events) and 15m (52.1 days).

BTC leader, clustered mean bps (net of nothing; bar is 9 bp):

| cell | 1m / 3.5d | 5m / 17.4d | 15m / 52.1d |
|---|---|---|---|
| thr=20 h=2 | **+9.41** (60 ev, t+1.84) | **-3.39** (298 ev, t-1.28) | -0.79 (863 ev, t-0.36) |
| thr=20 h=5 | **+20.80** (60 ev, t+1.98) | **-2.43** (298 ev, t-0.71) | -1.16 (863 ev, t-0.35) |
| thr=40 h=5 | -22.53 (8 ev) | **-20.17** (42 ev, t-1.97) | +0.33 (200 ev, t+0.04) |
| thr=30 h=2 | +6.52 (23 ev) | **-10.72** (98 ev, t-1.67) | -1.06 (399 ev, t-0.31) |

The 1m in-sample "+9 to +21 bp" cells go to **negative** out-of-sample with 5-14x the
events. That is what a fitted artifact looks like.

## Result 5 — the ONE robust effect, and it is 5x too small
The only cells anywhere in the study with clustered t >= 2.0, at 15m / 52 days:

| leader | thr | h | events | bp | clustered t | alts positive | net vs 9 bp |
|---|---|---|---|---|---|---|---|
| ETH  | 10 | 1 | 2,477 | **+1.755** | **+2.27** | **19/19** | **-7.25** |
| HYPE | 20 | 1 | 2,456 | **+1.557** | **+2.07** | **19/19** | **-7.44** |
| HYPE | 10 | 1 | 3,625 | +1.102 | +1.94 | 19/19 | -7.90 |
| BTC  | 10 | 1 | 2,005 | +1.160 | +1.29 | 18/19 | -7.84 |
| HYPE | 30 | 1 | 1,637 | +1.236 | +1.35 | 18/19 | -7.76 |

This is a genuine, internally consistent effect: only the FIRST bar after the signal is
positive (h=2 and h=5 collapse to ~0 or negative for every leader), and 18-19 of 19 alts
share the sign, which is exactly the signature of a real one-period follow-through.
**Magnitude +1.1 to +1.8 bp against a 9 bp bar — roughly one fifth of the fee.**

## Result 6 — the real bar is NOT 9 bp; for alts it is 9.1-12.9 bp
A taker also pays the half-spread each way. Measured from live BBO (16,964 top-of-book
updates, 16 coins, 227 s):

| coin | BBO updates | median spread bp | half-spread bp | TRUE round-trip cost bp |
|---|---|---|---|---|
| HYPE | 1296 | 0.106 | 0.053 | **9.11** |
| BTC  | 1124 | 0.123 | 0.062 | **9.12** |
| ETH  | 1202 | 0.381 | 0.190 | **9.38** |
| DOGE |  547 | 0.454 | 0.227 | 9.45 |
| XRP  | 1017 | 0.707 | 0.353 | 9.71 |
| LINK |  672 | 0.804 | 0.402 | 9.80 |
| SOL  |  907 | 0.880 | 0.440 | 9.88 |
| NEAR | 1492 | 1.051 | 0.526 | 10.05 |
| LTC  |  503 | 1.189 | 0.595 | 10.19 |
| AVAX |  783 | 1.282 | 0.641 | 10.28 |
| SUI  |  679 | 1.451 | 0.725 | 10.45 |
| TAO  | 1117 | 1.546 | 0.773 | 10.55 |
| WLD  |  707 | 1.622 | 0.811 | 10.62 |
| UNI  | 1366 | 1.636 | 0.818 | 10.64 |
| ARB  | 1251 | 1.838 | 0.919 | 10.84 |
| ENA  | 1223 | 3.897 | 1.949 | **12.90** |

The alts we would be trading (the followers) are the expensive side: **median true cost
~10.3 bp, up to 12.9 bp on ENA.** The bar for this strategy is therefore 10-13 bp, not 9.
The best measured effect (+1.76 bp) is **6x short**, not 5x.

## Result 7 — WHERE THE LAG ACTUALLY LIVES: ~1 second, not 1-5 minutes
This is the part 1m candles structurally cannot answer, so I collected live BBO
(event-driven top-of-book, server-timestamped) and binned mids at 250ms/1s.

`ll_subminute.py 1000 ws_bbo.jsonl` — 18,300 BBO updates, 23.1 min, 10 coins,
1,385 one-second return observations. Null 95% band = +/-0.053.

corr(r_leader[t-k], r_alt[t]) at 1-SECOND lags:

| pair | k=0 | k=1s | k=2s | k=3s | k=5s | k=10s | k=30s |
|---|---|---|---|---|---|---|---|
| BTC->ETH  | **+0.3964** | +0.1280 | +0.1169 | +0.0194 | +0.0825 | +0.0213 | -0.0331 |
| BTC->SOL  | **+0.3390** | +0.1486 | +0.0584 | +0.0517 | +0.0065 | +0.0504 | -0.0071 |
| BTC->XRP  | **+0.3524** | +0.0964 | +0.0495 | +0.0355 | +0.0064 | +0.0371 | +0.0012 |
| BTC->DOGE | **+0.2880** | +0.1634 | +0.0852 | +0.0228 | +0.0207 | +0.0269 | -0.0177 |
| BTC->SUI  | **+0.1922** | +0.1370 | +0.0186 | -0.0423 | -0.0080 | +0.0036 | -0.0056 |
| ETH->SOL  | **+0.3548** | +0.1271 | +0.0514 | +0.0081 | +0.0326 | +0.0211 | -0.0383 |
| ETH->DOGE | **+0.2947** | +0.1440 | +0.0059 | +0.0063 | +0.0134 | +0.0366 | -0.0172 |

**argmax lag distribution over all 27 leader-alt pairs: {k=0: 21, k=1: 1, k=3: 1,
k=5: 1, k=6: 1, k=7: 1, k=27: 1}. 21/27 pairs peak at k=0.** The six that peak later
are exactly the pairs with no contemporaneous signal at all (HYPE->ASTER k=0 corr
+0.021, HYPE->BTC +0.063, HYPE->LTC +0.021) and their "peaks" are 0.066-0.090, i.e. at
the +/-0.053 noise band — that is argmax-over-61-lags selection bias, not a lag.

Decay: BTC->SOL loses 56% of its correlation in the first second and 83% by two
seconds. **The adjustment is essentially complete in 1-2 seconds.** A 1m candle
averages over the entire response, which is why 1m "lag-1" correlation is ~0.01-0.14.

**So yes: 1m candle granularity is far too coarse to resolve the real lag, and I am
saying so as instructed. But the finding cuts against tradeability, not for it** — the
true lag is ~1s, which is shorter than we can act in, not longer.

## Result 8 — impulse response: how much is left to capture after you can see it
`ll_response.py ws_bbo.jsonl 250 1.5` — 250ms bins. `cum[h]` = signed EW-basket alt
move from the start of the leader's signal bin; the leader's move is only OBSERVABLE at
h=1, so everything up to h=1 is already gone and `EXECUTABLE = cum[h] - cum[1]`.

leader ETH, thr 1.5 bp/250ms, **44 events**, 9 alts:

| h | ms | cum bp | +/-se | % of total | EXECUTABLE bp | t |
|---|---|---|---|---|---|---|
| 1 | 250 | **+0.533** | 0.123 | **60.5%** | +0.000 | — |
| 2 | 500 | +0.691 | 0.150 | 78.5% | +0.158 | +2.74 |
| 4 | 1000 | +0.769 | 0.198 | 87.3% | +0.236 | +1.89 |
| 8 | 2000 | +0.857 | 0.223 | 97.3% | +0.324 | +2.18 |
| 20 | 5000 | +0.841 | 0.247 | 95.4% | +0.308 | +1.70 |
| 40 | 10000 | +0.881 | 0.390 | 100.0% | +0.348 | +1.01 |

**60.5% of the alt's entire response happens inside the leader's own 250ms bin — gone
before the signal exists.** Best executable residual over any horizon <= 10s:
**+0.351 bp** vs median alt true round-trip cost 9.85 bp -> **net -9.50 bp**.

Same run on my own denser 16-coin feed (`ll_bbo.py`, 25,555 updates, 75 updates/s):

| leader | thr | events | best EXECUTABLE bp <=10s | alt cost bp | net |
|---|---|---|---|---|---|
| ETH  | 1.0 | 13  | +1.987 | 10.05 | **-8.06** |
| HYPE | 1.0 | 93  | +0.603 | 10.05 | **-9.45** |
| HYPE | 1.5 | 57  | +1.075 | 10.05 | **-8.98** |
| HYPE | 3.0 | 39  | +0.959 | 9.85  | **-8.89** |

Every cell: executable residual +0.35 to +1.99 bp against a ~10 bp bar.

## Result 9 — the one real effect, fully characterized (split-half stable)
`ll_splithalf.py`, 15m bars, 52.1 days, 20 coins, hold exactly 1 bar:

| cell | events | bp | clustered t | 1st half | 2nd half | alts + |
|---|---|---|---|---|---|---|
| ETH thr=10  | 2,477 | **+1.755** | **+2.27** | +1.564 (t 1.39) | +1.947 (t 1.83) | **19/19** |
| HYPE thr=20 | 2,456 | **+1.557** | **+2.07** | +1.272 (t 1.17) | +1.841 (t 1.77) | **19/19** |
| BTC thr=10  | 2,005 | +1.160 | +1.29 | +1.294 (t 0.96) | +1.027 (t 0.86) | 18/19 |

Per-alt response to ETH (naive mean bp):
`ARB+3.54 UNI+3.07 NEAR+2.80 LINK+2.46 WLD+2.37 ENA+2.25 INJ+2.17 XRP+2.06 AVAX+1.77
SUI+1.74 TAO+1.73 SOL+1.46 DOGE+1.16 AAVE+1.16 ADA+0.92 HYPE+0.91 BTC+0.72 BNB+0.64
LTC+0.41`

This is a **real effect**, not noise: split-half stable, 19/19 alts share the sign, and
the cross-sectional ordering is economically coherent (high-beta / less-liquid alts
ARB/UNI/NEAR/LINK respond most; majors BTC/BNB/LTC least). Only h=1 is positive —
h=2 and h=5 collapse to ~0 or negative for all three leaders, the signature of a
genuine single-period follow-through that then mean-reverts.

**And it is 5.5x too small.** Break-even requires round-trip cost < **1.76 bp**, i.e.
**0.878 bp per side**. Our measured all-in cost is ~9.7 bp (8.64 bp taker with the
active 4% referral discount + ~1.05 bp median alt spread). Per `FINDINGS.md` #7, the
best taker on the entire HL ladder does not approach 0.88 bp/side, and rebate tiers are
unreachable at $641, $10,000 or $1,000,000 — so this is **not** a "wait until we have
volume" edge. It is structurally closed.

## VERDICT: NO_EDGE
- **Effect: +1.76 bp** (best robust cell; ETH leader, 15m, 2,477 events, clustered t +2.27).
- **Bar: 9 bp fees alone; 9.1-12.9 bp measured true cost incl. spread (median alt 10.3 bp).**
- **Net: -7.2 bp (vs 9 bp fee bar) to -8.5 bp (vs measured alt cost).**
- Cross-coin lead-lag on HL is REAL and MEASURABLE but ~1/5th of the fee.
- The lag lives at **~1 second** (21/27 pairs peak at lag 0; 56% of correlation gone in
  1s, 83% in 2s; 60.5% of the response completes inside the leader's own 250ms bin).
  1m candles cannot resolve it — and the resolution reveals the lag is too SHORT to
  trade, not long enough.
- The 1m "+9 to +21 bp" cells were pseudo-replication (19 correlated alts counted as 19
  independent draws, 4x t-inflation) over 2-3 market events on two days; they go
  NEGATIVE out-of-sample at 5m/17d and 15m/52d.
- Beta-shortfall catch-up: wrong sign, 24/24 cells, alts diverge from the leader.
- **Capacity: $0 deployable.** Not a size problem — the edge is smaller than the fee at
  any size.

### What would falsify this
A maker fill. The entire gap is execution cost: the effect is +1.76 bp and needs
<0.88 bp/side. A resting limit order at 0.0 bp maker (HL's $500M/14d top tier) plus
zero spread cost would make +1.76 bp gross viable. That is exactly the
maker-rebate-dependent strategy class GROUND_TRUTH constraint 2 forbids and
FINDINGS.md #7 proved unreachable. Absent that: nothing falsifies this at our fee tier.
A second, cheaper falsification: if HL ever backfills >30 days of 1m candles, re-run
`ll_clustered.py 1m_long` with ~1,000 independent BTC events instead of 60 — but the
15m/52d run already gives 863-2,477 events and shows +1.1 to +1.8 bp, so the 1m result
would have to be ~6x larger than the 15m result to change the verdict.

### Files
- `ll_candle.py` — corr matrix + naive trade (1m/5m/15m)
- `ll_clustered.py` — event-clustered t-stats (the honest sample size)
- `ll_splithalf.py` — split-half + per-alt on the one robust cell
- `ll_bbo.py` — live 16-coin BBO collector -> `data/ll_bbo.jsonl`
- `ll_subminute.py` — 1s-lag cross-correlation + per-coin true taker cost
- `ll_response.py` — 250ms impulse-response / executable-residual
