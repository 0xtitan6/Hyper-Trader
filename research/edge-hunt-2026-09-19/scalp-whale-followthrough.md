# Large-fill follow-through (whale momentum vs reversion) — 2026-09-19

Bar: 9bp round-trip taker (0.045% each way). Effect must exceed 9bp NET per trade.

## Design
Two independent tests.

**Test A (historical proxy, large sample).** 1m candles from
`{"type":"candleSnapshot","req":{"coin":C,"interval":"1m",...}}`.
A "whale bar" = a 1m bar whose notional volume (v*close) exceeds the 99th percentile of the
**trailing 1440 bars** (strictly past data — no look-ahead). Direction = sign(close-open).
Entry = **open of the NEXT bar** (first price observable after the signal). Forward returns
measured to bar closes at +1/2/5/10/30m, signed by the whale-bar direction.
Positive = follow-through/momentum. Negative = reversion.
Also tested `avgfill = v*px/n_trades` (targets few-large-fills bars rather than many-small).

**Test B (live tape, true aggressor tag).** WS `trades` subscription (gives `side`:
B = buy aggressor) for 10 coins + `allMids` for an unbiased mid price series.
Entry = mid ~2s AFTER the whale print is observable to us (no look-ahead).

Scripts: wf_candle.py, wf_control.py, wf_drift.py, ws_trades.py, wf_tape.py

## Test A results — 40 coins, 3.5 days of 1m bars (~129k bars scanned)

Raw (not drift-adjusted), top-1% volume bars, n=1929 events:
```
 +1m  mean  +0.86bp  t=+1.21
 +2m  mean  -0.90bp  t=-0.89
 +5m  mean  -4.49bp  t=-2.82
+10m  mean  -8.00bp  t=-3.90
+30m  mean -11.73bp  t=-3.95
```
=> NO follow-through. Mild REVERSION that grows with horizon.

Large-avg-fill (v*px/n) top 1%, n=1666: +1.12bp @1m (t=+2.06), +0.29 @5m, -1.21 @10m,
-4.40 @30m. Top 0.1% (n=249): all |mean| < 11bp, |t| < 1.7. Nothing.

### Control: is the reversion specific to whale bars?
Signed forward return bucketed by trailing volume percentile (128,630 bars):
```
 vol pct        +1m      +5m     +10m     +30m
 [0,50)      +0.39    +0.70    +0.97    +0.73   (t=+6.0/+4.5/+4.2/+1.8)
 [50,90)     +0.37    +0.84    +1.17    +0.13
 [90,99)     +0.89    +1.55    +0.74    -1.05
 [99,99.9)   +0.51    -6.03    -8.94   -11.10   (t=+0.7/-3.6/-4.0/-3.4, n=1607)
 [99.9,100]  +2.58    +4.55    -2.06   -17.77   (n=268)
```
Ordinary bars show tiny *momentum* (~+1bp, far under the bar). The reversion is genuinely
concentrated in the top-1% volume bars. But see the confound below.

### Confound: sample is one bull regime
Unconditional 10m drift over the window = **+4.77bp** (t=+12.2, n=20,819) — BTC ran
76,907 -> 81,383 (+5.8%) in 3.5 days. After removing each coin's own unconditional drift:
```
                ALL               UP-spikes            DOWN-spikes
 +1m   +0.79bp t=+1.09     +2.98bp t=+2.78      -1.52bp t=-1.57
 +2m   -1.00bp t=-0.96     +3.02bp t=+2.03      -5.24bp t=-3.68
 +5m   -4.58bp t=-2.83     +2.63bp t=+1.17     -12.20bp t=-5.32
+10m   -8.08bp t=-3.88     -2.49bp t=-0.87     -13.99bp t=-4.62
+30m  -12.42bp t=-4.18     -7.67bp t=-1.80     -17.44bp t=-4.22
```
The "reversion" is almost entirely **down-spikes bouncing**. Up-spikes show no reversion at
all. That is the signature of "buy the dip worked because the market rallied", not of a
symmetric microstructure effect. Per-coin +10m: 33/40 coins negative (reversion) — broad,
but every coin shares the same 3.5-day regime, so the cross-section is not independent.

### Net-of-fee arithmetic for the best version (fade down-spikes, buy)
+10m: gross +13.99bp - 9bp = **+4.99bp net**, sd 91bp, n=912 -> t = +1.66. Not significant.
+30m: gross +17.44bp - 9bp = **+8.44bp net**, sd 125bp, n=912 -> t = +2.04. Borderline, and
30m is not a scalp; also one regime.

## Longer history (HL caps 1m candles at ~5000 bars; 5m -> 17d, 15m -> 52d)
Tried paginating 1m backwards with endTime (fetch_hist1m.py): HL returns the same ~5100
bars regardless of startTime. 1m history is hard-capped. So longer windows use 5m/15m.

`wf_long.py`, drift-adjusted, top-1% volume bars, signed by bar direction:
```
             ALL              UP-spikes          DOWN-spikes
5m  (17d)  +5m  -2.66 t=-1.7   +5.00 t=+2.3   -9.82 t=-4.4   n=2311
           +30m -5.24 t=-1.8   +9.37 t=+2.0  -18.87 t=-5.3
15m (52d) +15m  -0.40 t=-0.2   +9.26 t=+3.1   -9.98 t=-3.6   n=2421
          +90m  -9.67 t=-2.2   +9.69 t=+1.5  -28.90 t=-4.9
```
Both halves of both samples agree. Note UP-excess ~= -DOWN-excess: that is the signature of
a *constant upward push after any high-volume bar*, i.e. the direction of the bar carries no
information at all. The "signed" number is ~0 because the two sides cancel.

## Sweep bars (top1% volume AND top1% |move| — the clearest whale imprint)
`wf_sweep.py`, signed by direction, entry next open:
```
 1m  +1m ALL  +1.99 t=+0.89 (n=420)   +8m ALL -11.29 t=-2.12
 5m  +5m ALL  -8.45 t=-2.02 (n=612)  +40m ALL -17.70 t=-2.47
15m +15m ALL  -5.49 t=-0.99 (n=623) +120m ALL -15.48 t=-1.14
```
**No follow-through at any horizon or granularity.** The signed effect never exceeds +2bp.

## Survivorship trap found and removed
The 40-coin universe was top-40 by open interest *as of today*. Recent listings that pumped
(ASTER, XPL, MON, PONS, CASHCAT, GRAM, CHIP, LIT) are in it, so "volume spike" selects their
pump episodes. Restricting to 28 coins that were already large well before the window
(`wf_majors.py`) and neutralising BTC:
```
5m MAJORS, btc-neutral, sweep bars (n=417)
  SIGNED-by-direction  +5m  -9.30 t=-2.50 | +10m -14.46 t=-3.49 | +20m -15.99 t=-3.01
  after UP-sweep       +5m  +2.86 t=+0.58 | +10m  -2.04 t=-0.34 | +20m  +6.24 t=+0.72
  after DOWN-sweep     +5m +20.41 t=+3.77 | +10m +25.79 t=+4.64 | +20m +36.28 t=+5.97
15m MAJORS (n=445): signed -10.57 / -14.03 / -10.94; DOWN-sweep +18.0 / +21.6 / +24.7
```
=> The answer to the hypothesis is **REVERSION, not momentum** — and it is entirely one-sided
(down-flushes bounce, up-flushes do nothing). One-sidedness is the fingerprint of buy-the-dip
beta in a rising sample, not of a symmetric liquidity-event microstructure effect.

## Is the down-flush bounce actually tradeable? (`wf_flush.py`, 5m majors, n=218)
```
entry = FIRST print of next bar (o[i+1])         entry = one bar later (cl[i+1])
 hold  5m raw +26.94  net(9bp) +17.94 t=+2.38     hold  5m raw  +8.71  net  -0.29 t=-0.05
 hold 15m raw +51.58  net(9bp) +42.58 t=+5.32     hold 10m raw +24.96  net +15.96 t=+2.44
 hold 35m raw +46.20  net(9bp) +37.20 t=+4.38     hold 30m raw +19.64  net +10.64 t=+1.44
 BTC-neutral, hold 15m: gross +36.28, net of 18bp (two legs) +18.28 t=+3.01
 BTC-neutral entry one bar later, hold 10m: gross +16.18, net of 18bp **-1.82 t=-0.37**
```
**Two thirds of the "edge" is the rebound inside the single bar right after the flush, and it
requires being filled at the first print (at the bid, during peak spread widening).** As a
taker you pay the ask there. Delay entry by one bar — the honest executable assumption — and
the market-neutral version goes to **-1.8bp net, t=-0.37. Dead.**
The only version that still nets +16bp is naked long, unhedged — which is just "be long alts
after a flush during a 17-day rally". h1 +7.9bp vs h2 +23.9bp: unstable across halves.

## Regime split kills the survivor (`wf_regime.py`)
BUY after a 15m DOWN-flush in a major, entry = close of the NEXT bar, hold 30m, 6 sub-periods
of the 52-day sample:
```
 P1 07-28->08-06 BTC  +1.23%  raw net9 +13.21 t=+1.48 | btc-neutral net18  +5.88 t=+0.73  n=16
 P2 08-06->08-15 BTC  -2.61%  raw net9 -20.70 t=-1.49 | btc-neutral net18 -13.26 t=-1.03  n=29
 P3 08-15->08-24 BTC +22.90%  raw net9  +9.94 t=+0.57 | btc-neutral net18  -6.64 t=-0.39  n=48
 P4 08-24->09-01 BTC  +0.01%  raw net9 +59.21 t=+6.27 | btc-neutral net18 +16.35 t=+1.86  n=34
 P5 09-01->09-10 BTC  +0.58%  raw net9  +5.70 t=+0.52 | btc-neutral net18  -8.03 t=-0.81  n=44
 P6 09-10->09-19 BTC  +4.41%  raw net9  -0.55 t=-0.05 | btc-neutral net18 -14.76 t=-1.47  n=49
```
The whole effect is ONE 8-day window (P4). Market-neutral net-of-fee is negative in 4 of 6
sub-periods. There is no stable edge here.

## Book depth (for capacity, measured live 2026-09-19 ~03:0x UTC, one l2Book each)
Taker VWAP slippage vs mid, buy side:
```
BTC  spread 0.12bp  $1k 0.06  $10k 0.06  $50k 0.06  $100k 0.06
ETH  spread 0.38bp  $1k 0.19  $10k 0.19  $50k 0.19  $100k 0.19
SOL  spread 0.88bp  $1k 0.44  $10k 0.44  $50k 0.44  $100k 0.44
XRP  spread 0.71bp  $1k 0.35  $10k 0.35  $50k 0.35  $100k 0.35
HYPE spread 0.21bp  $1k 0.11  $10k 0.27  $50k 1.48  $100k BOOK OUT
DOGE spread 0.11bp  $1k 0.06  $10k 0.19  $50k 2.01  $100k 3.02
LTC  spread 0.34bp  $1k 0.27  $10k 1.66  $50k BOOK OUT
SUI  spread 0.24bp  $1k 0.54  $10k 3.27  $50k BOOK OUT
```
Size is NOT the binding constraint on majors ($10k costs <0.5bp). The 9bp fee is the whole
problem: it is 75x the BTC spread and 20x the ETH spread.

# TEST B — LIVE TAPE, TRUE AGGRESSOR TAG (the decisive test)

Collectors: `ws_trades.py` (WS `{"type":"trades","coin":C}` -> coin/side/px/sz/exchange-ts,
plus OUR local receive ts) and `ws_bbo.py` (WS `{"type":"bbo","coin":C}`), 10 coins:
BTC ETH SOL HYPE DOGE XRP SUI LTC PUMP ASTER. 2026-09-19 ~02:45-03:30 UTC.
Collected **28,682 trades over 43.8 min** and **25,987 BBO snapshots**.

A "whale sweep" = consecutive same-coin same-side prints within 500ms aggregated (one
aggressor order sweeping levels). 9,939 sweeps. Top 1% per coin and >= $20k:
**90 events, median $268k, p90 $706k, max $4.40M.**

**Entry price = mid taken 1000ms AFTER OUR OWN receive timestamp of the last print of the
sweep.** This is the no-look-ahead entry: we cannot trade before we have seen the print.

## Result (`wf_tape3.py` trade-derived mid | `wf_tape2.py` true BBO mid — two independent
price constructions, they agree)
```
                    trade-mid (n=89-90)                    BBO mid (n=66-73)
 impact already gone by entry  +3.56bp t=+8.24      |   +2.75bp t=+6.85
 +  5s   +0.77bp t=+2.91 CI[+0.25,+1.30]            |   +0.91bp t=+2.47
 + 15s   +1.72bp t=+3.22 CI[+0.67,+2.77]            |   +1.83bp t=+2.84
 + 30s   +2.30bp t=+3.85 CI[+1.13,+3.47]            |   +1.70bp t=+2.36
 + 60s   +3.11bp t=+2.97 CI[+1.06,+5.16]            |   +2.61bp t=+2.04
 +120s   +1.39bp t=+1.15 CI[-0.99,+3.77]            |   -0.69bp t=-0.53
 +300s   +0.31bp t=+0.21                            |   -0.44bp t=-0.24
 +600s   +1.29bp t=+0.57                            |   -0.41bp t=-0.17
```
Symmetric: buy-sweeps +2.54bp @60s (n=52), sell-sweeps +3.90bp @60s (n=38). So unlike the
candle test this IS a genuine, two-sided microstructure effect — it is just far too small.

## Size monotonicity (`wf_tape4.py`, BBO mids, all sweeps bucketed by notional)
```
 sweep size        +15s     +30s     +60s    +120s        n
 $2k-$10k        +0.13    -0.08    -0.03    +0.10       911   <- nothing
 $10k-$50k       +0.15    +0.30    +0.55    +0.93       509   <- nothing
 $50k-$200k      +0.42    -0.36    -1.36    -2.28       127
 $200k-$1M       +1.98    +2.36    +3.12    +0.25        58   <- t=+2.6/+2.8/+2.1
 >$1M               --       --       --       --          5   (too few)
 95% CI upper bound for the $200k-$1M bucket at +60s = +6.10bp
```

# VERDICT

**Follow-through is REAL and statistically significant, and it is ~1/3 of the size needed.**

Best case measured: **+3.11bp** (60s hold after a $200k+ aggressive sweep), t=+2.97, n=90,
95% CI [+1.06, +5.16]. **The bar is +9.00bp. The entire 95% CI sits below the bar.**
Anything under $50k of sweep notional has zero signal (n=1,420, |mean| <= 0.9bp).

Anatomy of why: a $268k sweep moves the mid about **6.7bp total**, and **3.56bp of that is
already gone 1 second after we can see the print** (t=+8.24). We can only ever compete for
the residual ~3bp, and we must pay 9bp to do it. The effect is also fully decayed by 120s,
so there is no "hold longer to earn more" escape.

Maker note (for completeness, and it does not rescue anything): maker round trip is 3.0bp,
so +3.11bp @60s would be +0.11bp gross-of-nothing. You cannot reliably get a passive fill on
the side the price is already moving toward — that queue is precisely where you are adversely
selected — and GROUND_TRUTH rule 2 forbids maker-rebate dependence anyway. Stop.

Capacity: irrelevant, because there is no edge. If there were, books support $50-100k clips
on BTC/ETH/SOL/XRP at <0.5bp slippage.

## What would falsify this verdict
- A venue/fee path where round trip < 3bp (e.g. a builder-code fee rebate or a market-maker
  tier). At 2bp round trip the $200k+ 60s signal nets ~+1.1bp/trade — still thin, and n=58.
- Measuring at sub-second latency: the 3.56bp of pre-entry impact means most of the move
  happens inside 1s. If we could act in <100ms the capturable share might be larger. That is
  a colocation/HFT question and we are a Python bot on a shared EC2 box; not our game.
- A much larger sweep bucket (>$1M) — only 5 events in 44 min, would need ~2 weeks of tape
  to get n=100. The $200k-$1M point estimate (+3.12bp) would have to be ~3x larger there.
