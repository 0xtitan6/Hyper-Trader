# Scalp: funding-settlement clock (HL hourly funding)

Hypothesis: HL funding settles hourly on the hour (UTC). Does price systematically move
into / out of the funding stamp? If crowded longs pay, do we get a predictable squeeze?
Bar: 9bp round trip (0.045% taker each way).

## Data constraints found (important, cost me the original plan)
`candleSnapshot` on HL retains only ~5000 candles PER INTERVAL, regardless of startTime:
```
1m   5146 candles  2026-09-15 12:44 -> 2026-09-19 02:29   (3.6 days)
5m   5029 candles  2026-09-01 15:25 -> 2026-09-19 02:25   (17.5 days)
15m  5009 candles  2026-07-28 22:15 -> 2026-09-19 02:15   (52 days)
1h   5002 candles  2026-02-22 17:00 -> 2026-09-19 02:00   (209 days)
```
Requests with endTime in the past return `[]`. So the "1m over 30-60 days" plan is
IMPOSSIBLE from this API. Recovered sample size by widening the cross-section to the
top 40 non-HIP-3 coins by OI instead of 10, and using 5m as the workhorse resolution
(17.5d x 40 coins ~ 16.8k coin-hours) with 1m for fine structure (3.6d x 40 ~ 3.4k).

`fundingHistory` caps at 500 rows/page, paginated with startTime; 60d pulled per coin.

## Setup
Universe: top 40 non-HIP-3 perps by OI (BTC ETH HYPE ZEC SOL NEAR XRP LIT PUMP UNI AAVE XMR
ENA VVV LINK DOGE PONS XPL CASHCAT TAO WLD BNB SUI ZRO ONDO ARB ADA LTC MON kPEPE FARTCOIN
GRAM ASTER INJ ETHFI PAXG CRV AERO AVAX CHIP).
Scripts (all in this dir): fetch2.py (download), analyze.py .. analyze6.py (tests).
Data cached in ./data/{COIN}_{1m,5m,15m}.json and {COIN}_funding.json.

## 0. Funding timing convention — VERIFIED, not assumed
n = 18,040 coin-hours (15m panel):
  corr(fundingRate stamped at H, return over PRECEDING hour [H-1,H)) = +0.1401
  corr(fundingRate stamped at H, return over FOLLOWING hour [H,H+1)) = -0.0089
So the rate printed at H is built from the premium during the hour BEFORE H. Therefore
ANY test that sorts on f_H and looks at returns before H is mechanically lookahead-biased.
All tradeable results below use f_{H-1h}, which is strictly known before the stamp.

Lookahead demo (5m panel, n=417 hours), sort on f_H, low-funding-quintile MINUS high:
  [-60,-55) -3.54 t=-3.93 | [-45,-40) -3.51 t=-3.68 | cumulative over the pre-hour -24.6 bps
Same test on f_{H-1h}: -0.95 / -0.19 / cumulative +3.75 bps, no |t|>2.2 in 25 buckets.
The "squeeze" is entirely an artifact of the funding formula. This is the trap in this idea.

## 1. Is there a common clock effect? (equal-weight all 40 coins)
5m panel, 418 hours, 16,656 coin-hours. Mean bucket return, t across hours:
  worst/best of the 25 buckets: [-55,-50) -1.15 t=-1.09 ; [+15,+20) +1.35 t=1.51
  NO bucket has |t| > 1.6. Stamp bucket [0,+5m) = +0.67 bps, t=0.60.
1m panel, 83 hours (1m retention is only 3.6 days), minute-by-minute -15..+15:
  minute containing the stamp = +1.42 bps, t=1.07
  vs mean of the other 30 minutes 0.224 bps, sd 1.028  ->  z = 1.17
Largest single minute anywhere in the window: -2 min, +2.02 bps t=2.12 (1 of 31, expected).

15m panel, WITHIN-HOUR DEMEANED (r of :00-:15 quarter minus mean of other three quarters —
this removes all coin drift and all market beta), 453 hours / 18,120 coin-hours:
  ALL COINS:  excess at stamp = -0.804 bps,  t = -0.42
=> The common funding-clock price effect is 0 to +1.4 bps. The bar is 9 bps. DEAD.

## 2. Volatility / liquidity at the stamp (15m, 18,120 coin-hours)
  :00-:15  |ret| 42.28 bps (1.03x)  trades 672 (1.03x)   <- stamp quarter
  :15-:30  |ret| 39.79 bps (0.97x)  trades 617 (0.95x)
  :30-:45  |ret| 43.44 bps (1.05x)  trades 676 (1.04x)
  :45-:00  |ret| 38.67 bps (0.94x)  trades 636 (0.98x)
There is NO volatility or activity event at the funding stamp. The intra-hour amplitude is
~11% peak-to-trough and it does not peak at :00. Nothing to fade or to avoid.

## 3. Conditional on funding magnitude (the "crowded longs" version)
Funding distribution, 56,615 coin-hours over 60 days, bp per HOUR:
  p1 -0.353 | p5 -0.097 | p25/p50/p75 = 0.125 (68.9% of all hours sit exactly on the
  0.00125%/hr floor) | p95 0.529 | p99 1.567 | p99.9 4.451 | mean 0.156 | 9.8% negative
Carry alone needs 72h at median funding (5.7h at p99) to pay one 9bp round trip. Not a scalp.

Naive result (15m, sort on f_{H-1}): SHORT the high-funding coin across the stamp LOSES
  f>0.5bp n=861 : -10.9 bps over [0,+15m), t=-2.62
  f>2.0bp n= 80 : -49.7 bps over [0,+15m), t=-2.71
i.e. crowded-long coins keep going UP, the opposite of the squeeze hypothesis. So flip it
and go LONG. That is the only thing in this whole hypothesis that clears 9bp gross. It does
not survive:
  a) It is NOT a clock effect. Within-hour demeaned (stamp quarter vs the other three
     quarters of the SAME hour, same coins): +11.6 bps, t = 1.63, n_hours=298. Insignificant.
     The 5m version: stamp bucket +3.92 bps vs other-bucket mean +1.74, sd 3.65 -> z=0.59.
     It is ordinary cross-sectional momentum in hot alts, available at any minute.
  b) It is one coin. Leave-one-coin-out on the 11.6 bps / t=1.63 estimate:
       drop PONS -> 2.75 bps t=0.44   (PONS = 115 of 854 obs)
       drop XPL  -> 9.14 t=1.26 | drop CHIP -> 9.74 t=1.28 | drop CASHCAT -> 15.8 t=2.23
  c) Day-block bootstrap (20 distinct days, 20,000 reps): mean 11.1 bps,
     95% CI [-1.14, +23.94].  P(effect > 9bp bar) = 0.62, P(effect < 0) = 0.04.
     The CI contains zero AND contains the bar. Undetermined, not an edge.
  d) Sample is 3 coins/hour on average, all thin alts (XMR, PONS, VVV, CASHCAT, CHIP),
     so even if real the capacity is small and slippage would eat a 2bp net margin.
  Full-hour hold version, long f_{H-1}>0.5bp: +25.3 bps t=1.91 (n=300 hours, 861 obs);
  f>2bp: +38.6 bps t=0.98 (n=80). Same concentration problem, same insignificance.

## VERDICT: NO EDGE.
The funding settlement stamp is not a price event on Hyperliquid. Clean measurement:
-0.8 bps (t=-0.42, 18,120 coin-hours) within-hour demeaned across all 40 coins;
+1.4 bps (t=1.07, 83 hours) at 1m resolution for the stamp minute. Bar is 9 bps.
The apparent large effects in this hypothesis are (i) lookahead from the funding formula
and (ii) alt-coin momentum concentrated in one ticker, not a clock effect.
