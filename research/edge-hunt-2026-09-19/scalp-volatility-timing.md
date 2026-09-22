# Time-of-day volatility & drift on Hyperliquid perps

Slug: `scalp-volatility-timing`. Started 2026-09-19. Bar = **9 bp round trip** (0.045% taker each way).

## Hypothesis
1. Some UTC hour has persistent directional drift > 9bp (tradeable long/short once a day).
2. Some UTC hour has reliably elevated realised vol (useful for sizing / for other scalps,
   even if not directionally tradeable).
Explicit multiple-testing problem: 24 hours x 2 signs; ~1 hour will hit p<0.05 by chance.

## Data
- `candleSnapshot` 1h, top-12 coins by OI (from `data/universe.json`):
  BTC ETH HYPE ZEC SOL NEAR XRP LIT PUMP UNI AAVE XMR
- Fetcher: `fetch_hourly.py` -> `data/<COIN>_1h_long.json`
- **HL 1h candle retention is ~5000 bars.** Probe:
  `{"type":"candleSnapshot","req":{"coin":"BTC","interval":"1h","startTime":now-500d,"endTime":now-200d}}`
  returns 203 bars starting **2026-02-22 17:00 UTC** -> that is the floor. You cannot get
  360 days of 1h data; 208.5 days is the whole archive. So the sample is fixed at
  ~5003 bars/coin = ~208 obs per UTC-hour bucket per coin (not 4000 as the brief hoped).

- Universe widened to all 40 top-OI coins; **36 have the full 5000-bar archive**
  (PONS/CASHCAT/GRAM/CHIP are newer listings, excluded).
- Aligned contiguous grid: **5000 hourly bars = 208.3 days, 2026-02-22 19:00 -> 2026-09-19 03:00 UTC**,
  n = 208-209 observations per UTC-hour bucket per coin.
- Candle `t` = bar OPEN time (verified: last bar 03:00 on the 19th while wall clock was ~03:5x UTC).

## Scripts (all in this directory, run with ../../.venv/bin/python)
- `fetch_hourly.py` — 1h candles -> `data/<COIN>_1h_long.json`
- `tod_analyze.py` — drift & vol by hour / day-of-week, 12-coin index, Bonferroni + BH
- `tod_wide.py` — 36-coin hour-20 coherence, full 36x24 mining grid, circular-shift permutation null
- `tod_exec.py` — bid-ask-bounce kill test (open->close vs close->close)
- `tod_cost.py` — live L2 spread / walk-the-book slippage at $640 and $10k / funding
- `tod_walkforward.py` — walk-forward hour-of-day mining (the decisive process test)
- `tod_xmr_kill.py` — de-trend, drop-best-month, market-beta residual, Newey-West, rolling
- `tod_intrahour.py` — 15m decomposition of hour 20, plus last-52-days-only replication

---

# RESULT 1 (NEGATIVE): no market-wide hour-of-day DRIFT clears 9bp

Equal-weight index of 12 top coins, open->close return of each UTC hour, n=208-209 per hour:

| hr | mean bp | t | p |
|----|---------|---|---|
| 20 | **+9.74** | +2.25 | 0.024 |
| 00 | +6.89 | +1.83 | 0.067 |
| 22 | -6.66 | -1.47 | 0.141 |
| 15 | +5.94 | +0.99 | 0.322 |
| 18 | -5.26 | -1.17 | 0.241 |

(all 24 hours in `tod_analyze.py` output; every other hour is |t| < 1.3)

- **Bonferroni (24 tests, p<0.00208): NO survivors. Benjamini-Hochberg q=0.05: NO survivors.**
- Max |t| observed across the 24 hours = 2.25. Expected max |t| of 24 iid N(0,1) ≈ 2.4.
  **The largest hour effect in the data is smaller than what pure noise produces.**
- Hour-20 index gross is +9.7bp vs a 9bp bar = **+0.7bp net**, i.e. nothing.
- Hour-20 index is outlier-driven: drop the 5 best days -> +4.18bp, t=+1.16; drop 10 best ->
  +0.68bp, t=+0.20. Top-5 days = 58% of the whole sum.
- **Split-half persistence of the 24-hour drift profile: corr(H1,H2) = -0.103** (null 95% band
  ±0.428). The drift profile does not replicate at all.
- OOS: best hour chosen on H1 (hr 01, short, -13.3bp in H1) makes -7.0bp in H2 (t=-1.04),
  i.e. **-16.0bp net**, a loss.
- POWER (so this is not an underpowered null): index hourly sd = 64.8bp, n=208/bucket, so a
  true 9bp/hour drift would give t=2.01; BTC alone (sd 44.4bp) would give t=2.93. Min
  detectable at |t|=2.8 is 12.6bp. **The test can see a 9bp drift; there isn't one.**

## Day of week (7 tests) — also nothing
Full-day UTC index open->close, 208 days, 29-30 per weekday:
Mon +113.7bp (t=+2.10), Tue -12.4 (-0.23), Wed +75.1 (+1.19), Thu +39.7 (+0.55),
Fri +10.6 (+0.14), Sat +33.6 (+0.95), Sun +58.1 (+1.20).
Bonferroni p<0.0071 -> **NO survivors**. Daily sd is ~300bp, so a whole-day hold is a
different (much noisier) trade than a 9bp fee bar suggests; nothing is significant.

## Bid-ask-bounce control (important, and it came out clean)
Worry: a candle `open` printed at the bid biases open->close positive by ~half a spread.
Control = close(h-1)->close(h), where the bias cancels. Measured bias pooled over all bars:
XMR -0.28bp, ZEC -0.19, XPL -0.06, BTC -0.02, ETH -0.03, index -0.25bp/bar.
**Negligible — the hour effects are not a microstructure artifact.** (Hour-20 index:
+9.58bp open->close vs +10.33bp close->close, t=2.22 vs 2.39.)

---

# RESULT 2 (POSITIVE, non-directional): the intraday VOLATILITY clock is real and stable

36-coin average of |open->close| per bar, by UTC hour (n=208-209/hour):

| hr | mean abs bp | x avg | | hr | mean abs bp | x avg |
|----|------|------|-|----|------|------|
| 00 | 59.6 | 0.95 | | 12 | 64.6 | 1.03 |
| 01 | 70.0 | 1.11 | | **13** | **75.9** | **1.20** |
| 02 | 62.9 | 1.00 | | **14** | **81.2** | **1.29** |
| 03 | 59.5 | 0.94 | | **15** | **80.2** | **1.27** |
| 04 | 57.4 | 0.91 | | 16 | 68.5 | 1.09 |
| 05 | 60.7 | 0.96 | | 17 | 67.2 | 1.07 |
| 06 | 56.6 | 0.90 | | 18 | 64.1 | 1.02 |
| **07** | **54.7** | **0.87** | | 19 | 59.1 | 0.94 |
| 08 | 58.8 | 0.93 | | 20 | 60.0 | 0.95 |
| 09 | 56.4 | 0.89 | | 21 | 65.6 | 1.04 |
| 10 | 56.4 | 0.89 | | 22 | 63.6 | 1.01 |
| 11 | 55.7 | 0.88 | | **23** | **55.4** | **0.88** |

- **Bonferroni survivors (24 tests, Welch hour-vs-rest): hours 7, 9, 13, 14, 15, 23.**
  BH q=0.05 adds 4, 6, 11. Loudest 14:00 t=+5.28, quietest 23:00 t=-3.84.
- **Loud/quiet ratio = 1.48x** (14:00 = 81.2bp vs 07:00 = 54.7bp mean absolute move).
- Dollar volume tracks it: rel$vol 1.59x at 14:00 vs 0.74x at 04:00.
- **Split-half corr of the vol profile over 24 hours = +0.850.** OOS: hours in H1's top-6
  average 74.1bp in H2 vs 57.1bp for H1's bottom-6 = **1.30x, held out of sample**.
- Stable every single month (top6/bot6 ratio): Feb 1.42, Mar 1.18, Apr 1.44, May 1.36,
  Jun 1.26, Jul 1.36, Aug 1.27, Sep 1.29. **8/8 months.**
- 13:00-15:00 UTC = 09:00-11:00 ET = US cash equity open. 07:00 and 23:00 UTC are the
  Asia/US handover dead zones.

**How this is and isn't usable.** It is NOT directional, so it earns nothing by itself. Its
value is as a *scheduler* for any other scalp: the same fee bar (9bp) sits against a 1.48x
bigger price move at 14:00 UTC than at 07:00 UTC, so any strategy that captures a fixed
*fraction* of the hour's range has ~1.5x the gross-to-fee ratio if it only runs 12:00-16:00
UTC. Equivalently, a scalper that is marginal all day is 48% less marginal in that window,
and should be switched off 03:00-11:00 and 23:00 UTC. Same logic for stop distances and
position sizing (vol-target sizing should use the hour-of-day factor, not a flat daily vol).

---

# RESULT 3: the ONE directional cell that clears the bar — XMR 20:00 UTC — and why I only
half-believe it

## Mining scope stated up front
36 coins x 24 hours = **864 tests**. Bonferroni threshold p < 5.79e-05 (|t| > ~4.5).
Top cells (open->close):

| coin | hr | mean bp | t | net of 9bp |
|------|----|---------|---|-----------|
| XMR | 20 | +25.51 | **+4.73** | +16.51 |
| XMR | 07 | +24.92 | +4.56 | +15.92 |
| XMR | 12 | -19.88 | -3.40 | -28.88 |
| ETHFI | 22 | -20.05 | -3.31 | -29.05 |
| ONDO | 12 | +25.28 | +3.04 | +16.28 |
| ZEC | 20 | +29.05 | +2.85 | +20.05 |

**Permutation null for the max of 864 |t| values** (300 circular shifts of the whole
36-coin panel by a common random lag — preserves each coin's autocorrelation, the
cross-coin correlation *and* any real market-wide hour-of-day structure, so it is a
conservative null): max|t| p50 = 4.06, p95 = 4.64, max = 4.94.
**XMR hr20 |t|=4.73 -> family-wise p = 0.043.** On the close->close variant the same
procedure gives max|t| p50 4.03, p95 5.14 and **FW p = 0.140**.
So: family-wise p somewhere in **0.04-0.14**. That is *borderline at best* after honest
correction, and it is exactly what a winner's-curse artifact looks like.

## Measured execution cost (live L2, `tod_cost.py`, 2026-09-19)
| coin | mid | spread bp | RT slip $640 | RT slip $10k | funding bp/hr | all-in RT $640 |
|------|-----|-----------|--------------|--------------|---------------|----------------|
| XMR | 568.575 | 0.18 | 0.44 | 6.96 | +0.399 | **9.84** |
| ZEC | 1538.05 | 0.65 | 0.65 | 1.66 | +0.125 | 9.78 |
| XPL | 0.0911 | 0.22 | 1.21 | 6.75 | +0.125 | 10.34 |
| BTC | 81175.5 | 0.12 | 0.37 | 0.97 | +0.125 | 9.50 |
| ETH | 2621.35 | 0.38 | 0.38 | 0.38 | +0.155 | 9.38 |
| ENA | 0.1809 | 3.32 | 4.64 | 10.27 | +1.678 | 15.32 |
XMR top-5 bid depth is only $1,799, but walking the book for $10,000 costs 6.96bp round
trip, so $10k is executable; $640 costs 0.44bp. Longs pay 0.40bp of funding for the 1h hold.
**All-in XMR cost = 9.0 fee + 0.44 slip + 0.40 funding = 9.84bp at $640; ~16.4bp at $10k.**

## XMR hr20 net numbers, n=209 daily trades
- gross +25.51bp, **net +15.71bp/trade**, t = +2.91 on the net series
- median +15.43bp, hit rate 62.2%, 10%-trimmed mean +21.38bp (net +11.6)
- weekly-block bootstrap (B=5000, 7-day blocks): mean +15.34bp,
  **95% CI [+2.79, +29.00]bp, P(net<=0) = 0.0044**
- total +3283bp = **+32.8% of notional over 208 days** at 1 trade/day
- by month, net bp/trade: Feb -26.3 (n=7), Mar -7.7, Apr +18.6, May +19.7, Jun +60.1,
  Jul +3.2, Aug +10.7, Sep +16.8 -> **6 of 8 months positive, last 6 consecutive**

### Kill tests it survived
- de-trended (hr20 minus the same day's mean of the other 23 hours): +25.64bp, t=+4.64
  -> it is NOT just long-beta to a trending XMR (XMR drifted +29.2bp/day over the window)
- residual after regressing on the 36-coin index hr20 (beta 0.37): +21.97bp, t=+4.26
  -> it is NOT just the market-wide 20:00 effect
- drop the best month (June, +69.9bp): +18.07bp, t=+3.56, **net +8.27bp** — still clears
- drop the worst month: +26.96bp, t=+4.93
- Newey-West(5 lags) t = +4.09 (vs iid +4.73) — not an autocorrelation artifact
- **15 of 15 rolling 60-trade windows have net > 0** (range +2 to +40bp)
- last-52-days-only replication (fresh 1h pull): +23.85bp, t=+2.40, **net +14.05bp**, n=52
- 15m decomposition of the hour (52 days): +10.4 / +6.4 / +0.1 / +6.4 bp across the four
  quarters — **spread through the hour, not a single print**, so not a timestamp/oracle
  artifact, and slightly front-loaded (20:00-20:15 is the biggest slice)
- bounce control: close->close version is +26.02bp, t=+4.80 (essentially identical)

### The test it FAILED — and it's the one that matters most
**Walk-forward mining** (`tod_walkforward.py`): each month, pick the best coin-hour by |t| on
*prior months only*, trade it next month, charge measured per-coin cost.

| month | picked | train t | OOS n | OOS gross | net |
|-------|--------|---------|-------|-----------|-----|
| 2026-05 | ETHFI hr10 short | -3.27 | 31 | -3.30 | -15.30 |
| 2026-06 | XMR hr07 long | +3.65 | 30 | +57.85 | +48.05 |
| 2026-07 | XMR hr07 long | +4.21 | 31 | +13.21 | +3.41 |
| 2026-08 | XMR hr07 long | +4.45 | 31 | +1.83 | -7.97 |
| 2026-09 | XMR hr20 long | +4.55 | 18 | +26.56 | +16.76 |

**Top-1 walk-forward: n=141, net +8.00bp/trade, t=+1.07 — not significant.**
**Top-5 walk-forward: n=705, net -3.31bp/trade, t=-0.84 — LOSES money.**

So "mine the hour-of-day grid and trade the winners" is **not** an edge as a process. The
top-1 line only looks decent because it happened to land on XMR; widen the selection by one
notch and it goes negative. Any real money in this is a bet on the *specific* XMR-20:00 cell,
not on the method.

---

# BOTTOM LINE

1. **No market-wide time-of-day directional drift clears 9bp.** Largest index hour effect
   (+9.7bp at 20:00) is +0.7bp net, fails Bonferroni and BH, is 58%-driven by 5 days, and the
   24-hour profile has split-half corr **-0.103**. Day-of-week: nothing survives 7 tests.
   The test is powered to see a 9bp drift (t=2.0 on the index, t=2.9 on BTC). Clean negative.
2. **The time-of-day VOLATILITY clock is real, large and stable: 1.48x from 07:00 to 14:00
   UTC, split-half corr +0.85, 8/8 months.** Not directional, earns nothing alone, but it is
   a free 1.3-1.5x improvement in gross-move-per-9bp-fee for any other scalp, and the right
   way to schedule and size one. This is the reusable output.
3. **XMR 20:00 UTC long, 1h hold: +25.5bp gross, +15.7bp net of a measured 9.84bp all-in
   cost, n=209, block-bootstrap 95% CI [+2.8, +29.0]bp.** It survives de-trending, market-beta
   removal, dropping the best month, Newey-West, all 15 rolling windows and a fresh 52-day
   replication. But it is the maximum of 864 mined cells with **family-wise p = 0.04-0.14**,
   and the walk-forward version of the method is flat-to-negative. Treat it as a *candidate
   requiring forward proof*, not as an established edge.
   - Capacity: $10k executable today (6.96bp RT slip -> net ~+9bp/trade). $640 costs 0.44bp.
   - Expected P&L if real: $640 notional -> ~$1.00/day (~$30/mo); $10k -> ~$9/day.
   - **Forward test: 1 trade/day means 30 fresh observations per month at zero mining cost.**
     60 days of paper/live-at-$50 gives n=60; at sd 78bp the se is 10bp, so a true +15.7bp
     shows up as t≈1.6 in 60 days and t≈2.2 in 120 days. Cheap to settle honestly.
   - **What would falsify it:** 60 forward days at 20:00 UTC with mean net <= 0, or any
     2 consecutive months of negative net (never happened in the last 6).

---

## Rebuttal (look-ahead-and-stats)

Skeptic pass, 2026-09-19. Scripts: `/tmp/v1.py` `/tmp/f2.py` `/tmp/oos.py` `/tmp/oos2.py`
`/tmp/wf.py` `/tmp/volclock.py` `/tmp/final.py` `/tmp/prox.py`
(copies of the analysis live in `rebuttal_scripts/`).

### Verdict per result
| claim | verdict |
|---|---|
| R1: no market-wide hour-of-day drift clears 9bp | **CONFIRMED** (reproduced exactly) |
| R2: intraday vol clock real, stable, non-directional | **CONFIRMED and strengthened** (4.7yr OOS) |
| R3: XMR 20:00 UTC long, +15.7bp net, "candidate requiring forward proof" | **REFUTED** |

### 0. Reproduction — the arithmetic is clean
`/tmp/v1.py` on `data/XMR_1h_long.json` (5003 bars, 0 gaps, 2026-02-22 17:00 -> 2026-09-19 03:00):
XMR hr20 open->close **n=209, mean +25.509bp, sd 78.0, t=+4.729**, median +15.433, hit 62.2%.
Monthly hr20 gross: Feb -16.5 Mar +2.1 Apr +28.4 May +29.5 Jun +69.9 Jul +13.0 Aug +20.5 Sep +26.6.
Every number in the doc reproduces. Also confirmed not outlier-driven: top-5 days = 27.6% of the
sum, drop-top-5 +18.92 (t=+4.11), drop-top-10 +15.18 (t=+3.45), 10%-trim +21.23. So the usual
"it's five prints" attack fails here. The funding assumption also holds up — I pulled the real
`fundingHistory` (5018 hours, `/tmp/f2.py`): XMR mean funding **+0.351bp/hr at hour 20**
(median +0.125, p90 +0.85) vs the 0.399bp assumed. Cost of 9.84bp all-in is fair, even slightly
conservative. Funding, outliers, bid-ask bounce and NW autocorrelation are NOT where this dies.

### 1. THE FATAL FLAW: the "unobtainable" out-of-sample data exists on another venue
The doc's binding constraint is `HL DATA HORIZON: 1h candleSnapshot retains exactly ~5000 bars
... 180-360 days of 1h data is NOT obtainable; 208.5 days is the entire archive`. True of
Hyperliquid — and false of the instrument. **Bybit XMRUSDT linear perp gives 41,009 contiguous
1h bars, 2022-01-14 11:00 -> 2026-09-19 03:00 UTC, 0 gaps** (`/tmp/byb.py`,
`GET /v5/market/kline?category=linear&symbol=XMRUSDT&interval=60&limit=1000&end=<ms>`, paged back
42 times).

Proxy validity, `/tmp/prox.py`, 5003 overlapping bars:
**corr(HL bar return, Bybit bar return) = +0.9966**; on hour-20 bars only **+0.9968**;
Bybit hr20 in the same window **+24.67bp t=+4.61** vs HL +25.51 t=+4.73. Same asset, same effect.
The 24-hour Bybit profile in the HL window matches cell-for-cell (hr07 +24.22 vs +24.92,
hr12 -19.33 vs -19.88). So Bybit history is a legitimate extension of the series, and the
"forward proof" the doc asks for already exists — backwards, and it is negative.

**XMR hour 20 long, TRUE out-of-sample, 2022-01-14 -> 2026-02-22 (the 1500 days immediately
before the HL archive floor, never touched by the mining):**

| window | n | gross bp | t | net of 9.84bp |
|---|---|---|---|---|
| HL mining window 2026-02-22 -> 09-19 | 209 | **+24.67** | +4.61 | +14.83 |
| **TRUE OOS 2022-01-14 -> 2026-02-22** | **1500** | **+0.94** | **+0.41** | **-8.90** |
| entire 4.7yr Bybit history | 1709 | +3.84 | +1.82 | **-6.00** |

Cumulative net bp of "XMR hr20 long, 1/day" over the whole 4.7 years: **-10,250bp = -102.5% of
notional.** Half-year checkpoints: -1786 / -2578 / -5175 / -6083 / -7599 / -12191 / -11420 /
-11760 / -10250. The 208-day discovery window is a local up-tick on a curve that spent four
years going down.

By calendar year (gross / net): 2022 +2.52 / -7.32 (n=352), 2023 +0.24 / -9.60 (365),
2024 -6.85 / -16.69 (366), 2025 +11.02 / +1.18 (365), 2026 +15.62 / +5.78 (261).
Pre-2025 pooled: **-1.42bp, t=-0.53, net -11.26bp, n=1083.**

OOS block bootstrap (`/tmp/final.py`, B=5000, 7-day blocks, n=1500):
OOS net mean **-8.98bp, 95% CI [-14.01, -4.30], P(net>0) = 0.0002,
P(OOS net >= the claimed +15.71bp) = 0.00000.**

IS-vs-OOS Welch test: +24.67 vs +0.94, difference **+23.73bp, se 5.82, t = +4.08.** The
discovery window is not a draw from the same population as the other 1500 days. That is the
signature of a selected window, not of a clock.

The doc states its own falsifier: *"60 forward days at 20:00 UTC with mean net <= 0."* 1500
backward days give mean net -8.98bp. The falsifier is met 25x over.

Even the friendliest honest slice fails. **2025-01-01 -> 2026-02-22** (417 days, entirely
outside the mining window, same bull regime): hr20 **+7.06bp t=+1.60 -> net -2.78bp, loses.**
And hour 20 is not even the standout there — the max|t| cell is hr12 at -16.37, t=-3.99.

### 2. Mechanism: hour 20 is a 0.52-beta to XMR's contemporaneous drift, not a clock
Across 7 non-overlapping segments (`/tmp/final.py`):

| segment | XMR drift bp/day | hr20 mean bp | n |
|---|---|---|---|
| 2022 | +0.1 | +2.52 | 352 |
| 2023 | +6.3 | +0.24 | 365 |
| 2024 | +12.9 | -6.85 | 366 |
| 2025H1 | +38.0 | +14.10 | 181 |
| 2025H2 | +25.8 | +7.99 | 184 |
| **2026-01-01..02-22 (the 7 weeks just before the archive floor)** | **-35.7** | **-20.73** | **52** |
| HL mining window | +35.3 | +24.67 | 209 |

**corr(segment daily drift, segment hr20 mean) = +0.901; regression slope 0.520.** Hour 20 alone
absorbs about half of whatever XMR's whole-day drift happens to be. A genuine hour-of-day clock
would have slope ~0; a pure 1/24 share would be slope 0.042. At 0.52 this cell is a levered,
unhedged bet on XMR trending up during the hold — which is not knowable at 20:00:00.

Note the 2026-01/02 row: had the HL 5000-bar archive begun seven weeks earlier, the same mining
grid would have scored XMR hr20 at roughly **-20bp** and never surfaced it. The cell's existence
is an artifact of where HL's retention window happens to start.

**This is why the doc's kill tests all passed and proved nothing.** The de-trend control
("hr20 minus the same day's mean of the other 23 hours") removes drift/24 = ~1.5bp, while hour 20
carries ~0.52 of the drift; it cannot possibly separate the two hypotheses. Demonstration: run
the identical de-trend on the OOS data — 2022-2024 **-1.87bp t=-0.68**, OOS<2026-02-22
**+0.42bp t=+0.18**, HL window +24.22 t=+4.44. The control "passes" in exactly the world where
the effect is pure trend-concentration, so it has ~zero discriminating power. Same for the
market-beta residual (beta 0.37 on a 36-coin index): it removes market beta and leaves XMR's
*idiosyncratic* +75% run over the window fully loaded.

### 3. The doc's confirmatory tests are in-sample, not replications
- "last-52-days-only replication (fresh 1h pull): +23.85bp, n=52" — those 52 days are a **subset
  of the 208 days used to select the cell**. A fresh HTTP request is not a fresh sample. Zero
  independent information.
- "15 of 15 rolling 60-trade windows net>0" — windows of 60 stepped by 10 over 209 trades = about
  **2.5 independent windows**. It restates "the equity curve didn't dip", not 15 successes.
- "drop the best month", "drop the worst month", "Newey-West", "15m slices", "close->close" — all
  in-sample re-slices of the same 209 observations. None can detect window selection.
- Search space is larger than the 864 stated: 36 coins x 24 hours x {open->close, close->close}
  x {12-coin index, 36-coin index, day-of-week} and a second-place cell (XMR hr07, t=+4.56) was
  also inspected. The doc's own family-wise p of 0.043 was computed from 300 permutation reps —
  13/300 exceedances, se 0.0117, so the honest interval on that p is [0.020, 0.066] even before
  adding the close->close arm, which the doc reports at **FW p = 0.140**. A borderline FW p on a
  grid whose winner is zero out of sample is what winner's curse looks like.

### 4. Walk-forward, extended to 4.7 years: still not an edge (and it doesn't pick hour 20)
`/tmp/wf.py`, expanding-window: each month pick XMR's max-|t| hour on all prior months, trade it
next month, charge 9.84bp.
- min 12 months train: **n=1357, gross +7.34bp, net -2.50bp, t(net) = -1.20** (loses)
- min 24 months train: **n=992, gross +9.99bp, net +0.15bp, t(net) = +0.06** (flat)

This reproduces the doc's own failed test at ~7-10x sample. Worse for the specific claim: from
2026-02 onward the process picks **hr12 SHORT** every single month, never hr20 long. So the
strategy an honest implementation would have been running in 2026 is not the one being proposed.

### 5. What survives — and it is the non-directional result
Result 2 holds up better OOS than in the doc. `/tmp/volclock.py`, 4 coins (BTC/ETH/SOL/XMR),
Bybit, mean |open->close| normalised within each year:

| year | loudest | quietest | loud/quiet |
|---|---|---|---|
| 2022 | hr14 1.29 | hr04 0.74 | 1.75x |
| 2023 | hr15 1.32 | hr04 0.72 | 1.85x |
| 2024 | hr14 1.40 | hr11 0.82 | 1.70x |
| 2025 | hr14 1.44 | hr11 0.82 | 1.77x |
| 2026 | hr14 1.41 | hr04 0.79 | 1.77x |

Cross-year correlation of the 24-hour vol profile: **+0.79 to +0.97** (2024/2025 +0.974,
2025/2026 +0.925, 2022/2026 +0.829). Rank hours on 2022-2024, measure on 2025-2026:
train-top-6 = 1.219 rel vol vs train-bottom-6 = 0.858, **ratio 1.42x held out across two years**,
profile corr **+0.925**. Loudest hour is 14:00 UTC in 4 of 5 years. This is a genuine, stationary
5-year clock. It is still non-directional and earns nothing on its own; it is a scheduler/sizer.

### Bottom line of the rebuttal
The two results the doc labels negative/non-directional are right, and the vol clock is more
robust than claimed. The single tradeable directional claim is dead: **XMR 20:00 UTC long is
+0.94bp (t=+0.41) over the 1500 days immediately preceding the window it was mined in, -8.98bp
net with 95% CI [-14.0, -4.3] and P(net>0)=0.0002, and -6.00bp net over the full 4.7-year
history.** Its in-window size is a 0.52-beta to XMR's drift regime (corr +0.90 across segments),
including -20.7bp in the 7 weeks just before the HL archive starts. Do not forward-test it; the
forward test is already in the tape, on the other side of a retention window. **Do not allocate.**

Method note for future hunts: HL's 5000-bar cap is not a data limit on the *asset*. Bybit/OKX
hourly klines go back years for the same perps at bar-return corr +0.997. Any hour-of-day,
day-of-week or regime claim mined on HL's 208-day archive can and must be checked there first —
it cost 42 HTTP calls and killed a cell that had survived seven in-sample robustness tests.
