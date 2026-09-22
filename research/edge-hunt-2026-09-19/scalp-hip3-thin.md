# HIP-3 thin-book scalping — working notes
Agent slug: scalp-hip3-thin. Started 2026-09-19 ~03:25 UTC.
Hypothesis: HIP-3 builder-dex books (xyz:/para:/io:) are thin => wide spreads + stale-then-jump
pricing. Decisive question: can a TAKER (0.045%/side = 9bp round trip) capture any dislocation,
or is the spread we must cross larger than anything we could capture?

## REGIME WARNING (record this first)
Sampling window is **Saturday 03:2x-03:5x UTC**. US equities closed Fri 20:00 UTC; index
futures reopen Sun 22:00 UTC. So xyz:/io:/mkts: equity+commodity perps are in their WEEKEND
regime: no live underlying, no external reference price, market-maker quotes on a closed cash
market. Any spread/jump numbers below are weekend numbers and are an UPPER bound on staleness
and likely an upper bound on spread too. Base-dex BTC/SOL are in-session 24/7 controls.

## Step 0: which HIP-3 venues are even alive
`{"type":"perpDexs"}` -> 11 venues: base, xyz, flx, vntl, hyna, km, abcd, cash, para, mkts, io.
`{"type":"metaAndAssetCtxs","dex":<name>}` 24h notional volume (script /tmp/hip3_pick.py):
  base 9.1B | xyz 2.04B | io 24.8M | mkts 11.7M | para 5.7M | flx/vntl/hyna/km/abcd/cash = $0
(agrees with sibling agent hip3-dislocation.md). Live HIP-3 = xyz, io, mkts, para only.

Top-volume names picked for L2 sampling (24h vlm $, mark px):
  xyz:XYZ100 277.6M @29631 | xyz:SP500 251.8M @7654 | xyz:SNDK 174.5M @1778.2
  xyz:CL 158.9M @96.014 | xyz:SKHX 127.0M @1338.2 | xyz:SILVER 110.6M @66.441
  xyz:GOLD 45.7M @4378 | io:SNDK 14.2M @1777.3 | io:ANTH 5.1M @2165.2 | io:NBIS 3.0M @220.6
  para:ANSEM 1.6M @0.1634 | para:VST 0.27M @141.54 | mkts:US500 6.4M @763.5
  controls: BTC 3.86B @81261, SOL 437M @113.5

## Step 1: first l2Book probe (single snapshot, /tmp/probe_l2.py)
  xyz:SP500  bid 7653.9 x0.071 (n=5) / ask 7654.0 x0.142 (n=4)  -> spread 0.13 bps
  io:ANTH    bid 2164.6 x0.056 (n=1) / ask 2164.9 x0.284 (n=7)  -> spread 1.39 bps
  para:ANSEM bid 0.1649 x752    (n=1) / ask 0.167  x2411  (n=1)  -> spread 126 bps
  BTC        bid 81245 x0.347 (n=10) / ask 81246 x16.71 (n=67)   -> spread 0.12 bps
First read: spread is NOT uniformly wide on HIP-3. xyz top-of-book is majors-tight; para is
catastrophically wide. Top-of-book *size* is the thin part ($543 on the xyz:SP500 bid).
Note 2x HTTP 429 on the first calls -> parallel agents share the IP; sleeps raised to 0.55s.

## Step 2: continuous L2 sampling (running)
/tmp/hip3_l2_sampler.py 150 -> data/hip3_l2.jsonl (15 coins x 20 levels each side,
one pass every ~8.3s, 150 passes ~= 21 min). Records px/sz/n per level so depth-slippage
and mid-jump stats can be computed offline.

## Step 3: SPREADS ARE NOT WIDE — the hypothesis' premise is wrong
Analyzer: research/edge-hunt-2026-09-19/hip3_spread_analyze.py over data/hip3_l2.jsonl.
First 13 passes (13 snapshots/coin, ~110s of wall clock, 03:26-03:28 UTC Sat).
`rt$N` = round-trip SLIPPAGE ONLY (take $N on the ask + take $N on the bid, VWAP vs mid,
summed, in bps) / % of snapshots where the 20-level book could absorb $N at all.

coin           n  spr_med  spr_p90  bid$@best  ask$@best   rt$100     rt$1k      rt$10k     book$(40 lv)
BTC           12    0.12     0.12      35,905  1,015,680   0.1/100%   0.1/100%   0.1/100%    9,516,487
SOL           12    0.88     0.88      49,646     69,177   0.9/100%   0.9/100%   0.9/100%    7,927,896
xyz:SP500     13    0.13     0.13         528      1,087   0.1/100%   0.3/100%   0.6/100%    3,560,464
xyz:SILVER    13    0.15     0.15       6,338      1,954   0.2/100%   0.2/100%   0.8/100%      233,508
xyz:GOLD      13    0.23     0.23     160,050     36,429   0.2/100%   0.2/100%   0.2/100%      856,930
xyz:XYZ100    13    0.34     0.34       1,793     33,034   0.3/100%   0.3/100%   0.6/100%    3,003,862
xyz:CL        13    0.52     0.62       1,000      1,034   0.6/100%   0.7/100%   1.3/100%      224,068
xyz:SNDK      13    0.56     0.56       5,889      7,647   0.6/100%   0.6/100%   0.9/100%    1,893,581
xyz:SKHX      13    0.75     1.49       3,322        756   0.7/100%   1.4/100%   2.5/100%    1,220,617
mkts:US500    12    0.13     0.13       4,366        305   0.1/100%   0.6/100%   nan/  0%       33,618
io:ANTH       12    0.46     2.31         464        619   0.5/100%   2.4/100%  15.9/ 75%       31,106
io:SNDK       13    0.56     1.13         362        850   0.7/100%   2.0/100%   9.2/100%       56,109
io:NBIS       12    1.81     1.81         389        232   1.8/100%   4.8/100%  13.5/100%       79,734
para:VST      12    3.53     3.53          16         17  10.6/100%  27.5/ 42%   nan/  0%      228,868
para:ANSEM    12  121.80   123.62         260        402 122.4/100% 134.5/100% 223.7/ 75%       39,272
(0 fetch errors)

KILL SHOT on the premise: the 7 liquid xyz names quote 0.13-0.75 bps spread, i.e. TIGHTER
than base-dex SOL (0.88 bps) and comparable to BTC (0.12 bps). $10k round trips for
0.2-2.5 bps of slippage. "Thin book => wide spread" is simply false for xyz's top names.
It IS true for para (ANSEM 122 bps spread, VST can't absorb $1k half the time).

Also a correction to our own memory note "xyz:* perps unexecutable at size": at $10k clip
size the top-7 xyz names are fine (<=2.5 bps round-trip slippage). What is unexecutable is
xyz *tail* names and para/io tails, plus whatever the $500 per-dex collateral cap blocks.

Consequence for the hypothesis: cheap spreads mean the cost side is dominated by FEES, not
spread. Taker round trip on xyz:SP500 = 9.0 bp fees + 0.13 bp spread = 9.1 bp. So the whole
question collapses to: is there any 9.1bp-sized predictability? Spread being small does NOT
create an edge, it only removes an excuse. Next: event study on 1m candles (7 days).

## Step 4: weekend mid dynamics — the mids are FROZEN, not stale-then-jumping
Same sampler, 21-22 intervals/coin (~3 min, 8.3s apart), 03:26-03:30 UTC Sat. `frz%` = share of
consecutive samples with mid change EXACTLY 0. `jump>cost%` = share of intervals whose |mid move|
exceeds that coin's own taker round-trip cost (9bp fees + its median spread).

coin          n_int  frz%  |d|med  |d|p95  maxjump  ac1     jump>cost%
xyz:SP500      22   100.0   0.00    0.00     0.00   n/a        0.0
xyz:XYZ100     22   100.0   0.00    0.00     0.00   n/a        0.0
xyz:GOLD       22   100.0   0.00    0.00     0.00   n/a        0.0
mkts:US500     21   100.0   0.00    0.00     0.00   n/a        0.0
xyz:SILVER     22    90.9   0.00    0.00     1.35   +0.442     0.0
xyz:SNDK       22    72.7   0.00    1.12     1.69   -0.019     0.0
xyz:CL         22    54.5   0.00    0.10     0.31   -0.038     0.0
xyz:SKHX       22    36.4   0.37    0.75     1.87   -0.446     0.0
io:SNDK        22    68.2   0.00    0.56     3.38   +0.140     0.0
io:ANTH        21    52.4   0.00    1.16     2.31   -0.388     0.0
io:NBIS        21    57.1   0.00    0.68     2.49   -0.032     0.0
para:VST       21    61.9   0.00    2.83     3.53   +0.506     0.0
para:ANSEM     21    28.6   1.21   12.06    44.16   -0.106     0.0
BTC (control)  21    57.1   0.00    0.98     1.23   +0.101     0.0
SOL (control)  21    66.7   0.00    2.64     5.29   +0.254     0.0

The `jump>cost%` column is 0.0 for EVERY coin, including base-dex BTC/SOL: across 316 coin-
intervals not one 8-second mid move was as large as the 9bp round-trip fee. The single largest
mid move anywhere in the sample was 44 bps on para:ANSEM — whose spread is 75-122 bps, i.e. the
"jump" is smaller than the spread you'd cross to trade it. That is the whole hypothesis in one
number: on HIP-3 the dislocation is *smaller* than the cost of touching it.
The equity/index/metal names on xyz + mkts are literally frozen (100% zero-change) because the
underlying cash market is shut. There is no stale-then-jump to front-run; there is just nothing.
Caveat: 3 minutes, weekend. In-session behaviour is tested next on 7 days of 1m candles.

## Structural constraints on HIP-3, independent of any edge
- Separate clearinghouses: INVARIANTS.md #2 — each HIP-3 dex settles against its OWN collateral.
  To scalp xyz you must pre-fund the xyz clearinghouse; that capital cannot simultaneously back
  base-dex positions. A multi-dex scalper fragments a $641 account into sub-$200 buckets, each
  of which then trips the $10 HL minimum order value after ~20 concurrent clips.
- config.yaml `risk.max_dex_exposure_usd: 500` (line 892) and xyz already sits near it, so any
  xyz strategy competes with the existing copy book for the same cap.
- So even a real edge would be capacity-limited to ~$500 of xyz notional here, i.e. a 10bp edge
  = $0.50/round-trip before we hit the cap.

## Step 5: microstructure event study on L2 mids (research/.../hip3_mid_event.py)
Condition: any NONZERO mid change between consecutive 8.3s samples (the "jump"). Then measure
the mid return over the next h intervals, SIGNED by the jump direction (positive = continuation).
31-32 snapshots/coin, 03:26-03:31 UTC Sat. `cost` = 9bp taker round trip + that coin's median spread.

coin           N    n_ev   f+1(8s)  t      f+3(25s)  t      f+10(83s)  t      cost
BTC           31      8     +0.26  1.51     +0.52  1.23     +0.38   0.44     9.12
io:ANTH       31      9     +0.03  0.08     +0.10  0.37     +1.26   1.86     9.46
io:NBIS       31      8      0.00  0.00     -0.42 -1.24     -0.28  -0.54    10.81
xyz:CL        32     10      0.00  0.00     -0.02 -0.34     +0.09   1.13     9.36
xyz:SKHX      31     13     -0.43 -2.65     -0.32 -1.50     -0.78  -1.77     9.75
para:ANSEM    31     14     -2.53 -0.58     -7.64 -1.14     -6.91  -1.26    51.24
(SOL, io:SNDK, para:VST, xyz:SNDK/SP500/XYZ100/GOLD/SILVER, mkts:US500: <8 nonzero-mid events
 in 5 minutes — nothing to condition on)

Largest conditional continuation anywhere: **+1.26 bps** (io:ANSEM… io:ANTH, 83s ahead, t=1.86,
n=9). Against a 9.46 bp cost. The one statistically significant number is xyz:SKHX at
-0.43 bp (t=-2.65) — mild mean REVERSION, 21x too small to trade as a taker, and capturing it
would require being the resting maker (explicitly excluded by GROUND_TRUTH constraint #2).
n is tiny here by construction (frozen books); the 7-day candle study below carries the weight.

## Step 6 (FINAL L2 numbers, 37-38 snapshots/coin, 03:26-03:32 UTC Sat)
mid dynamics (8.3s intervals):
coin        frz%  |d|p95  maxjump   ac1     jump>cost%   |  event study: f+1(8s)  f+3(25s)  f+10(83s)   cost
xyz:SP500   97.3   0.00     0.07   -0.00      0.0        |   no events (0 nonzero mid changes)     9.13
xyz:GOLD   100.0   0.00     0.00    n/a       0.0        |   no events                            9.23
xyz:XYZ100  91.9   0.17     0.67   +0.176     0.0        |   no events                            9.34
mkts:US500 100.0   0.00     0.00    n/a       0.0        |   no events                            9.13
xyz:SILVER  86.5   0.30     1.35   +0.450     0.0        |   2 events                             9.15
xyz:CL      48.6   0.31     0.52   -0.100     0.0        |  0.00  -0.02(t-0.5)  +0.07(t+0.7)      9.31
xyz:SKHX    43.2   2.24     2.62   +0.103     0.0        | -0.20  -0.55(t-2.45) -0.90(t-2.39)     9.75
xyz:SNDK    64.9   2.25     6.18   +0.219     0.0        | -0.07  -0.56(t-1.10) -1.76(t-1.07)     9.56
io:SNDK     62.2   2.81     7.87   +0.103     0.0        | +0.56  +0.91(t+1.50) -2.18(t-1.28)     9.56
io:ANTH     54.1   2.31     4.62   +0.031     0.0        | +0.08  +0.17(t+0.82) +0.44(t+0.51)     9.46
io:NBIS     48.6   1.36     2.49   +0.105     0.0        | -0.06  -0.31(t-1.51) +0.13(t+0.30)    10.81
para:VST    51.4  11.28    26.07   -0.186     5.4        | +0.07  -2.71(t-1.13) -0.67(t-0.36)    12.53
para:ANSEM  43.2  32.56    44.16   -0.119     0.0        | -2.51  -4.80(t-0.80) -4.47(t-0.79)    62.29
BTC ctrl    62.2   0.98     4.06   +0.013     0.0        | +0.24  +1.10(t+2.22) +1.31(t+1.67)     9.12
SOL ctrl    58.3   3.53     5.30   +0.038     0.0        | +0.10  +1.08(t+0.93) +0.88(t+0.91)     9.88
Only para:VST ever jumped past its own cost (5.4% of intervals) — and para:VST cannot absorb
$1k half the time and $10k never (Step 3), so those jumps are not takeable at our size.
Largest conditional continuation in the whole L2 sample: +1.31 bp (BTC, 83s) vs 9.12 bp cost.

## Step 7: 7 days of 1m candles (n=5004-5203 bars per coin) — the powered test
Fetcher /tmp/hip3_candles.py -> data/hip3_1m.json. Analyzers hip3_candle_analyze.py,
hip3_session_analyze.py. Volatility, in-session (Mon-Fri 13:30-20:00 UTC) vs off:
coin        n_in  sd_in(bp)  zero_in%   n_off  sd_off  zero_off%   min_to_9bp(in-session)
xyz:SP500   1482    2.31       3.5      3597    1.02     15.2          15.1
xyz:XYZ100  1560    2.99       8.0      3641    1.62     16.2           9.1
mkts:US500  1468    2.13      24.9      3589    0.86     59.8          17.9
xyz:GOLD    1560    4.92      16.9      3636    2.68     29.5           3.4
xyz:CL      1537    7.40       2.4      3597    5.76      3.9           1.5
xyz:SILVER  1544    8.14       1.2      3597    5.02      6.4           1.2
xyz:SKHX    1553    9.49       4.6      3597    6.84      8.0           0.9
xyz:SNDK    1560   15.40       2.6      3605    5.34      8.4           0.3
io:ANTH     1413    4.54      13.8      3597    3.96     20.0           3.9
io:SNDK     1411   15.10       3.1      3597    5.46      7.1           0.4
io:NBIS     1406   20.96       3.4      3597    7.87      6.2           0.2
para:VST    1484   10.70      52.0      3597    4.81     87.6           0.7
para:ANSEM  1443   62.98      39.9      3597   55.18     42.0           0.0
BTC ctrl    1560    8.93       0.8      3642    4.33      4.1           1.0
SOL ctrl    1560   13.43       2.4      3631    7.20      4.3           0.4
min_to_9bp = (9/sd_1m)^2 minutes: how long a 1-sigma move needs to just EQUAL the fee.
xyz:SP500 needs ~15 minutes of 1-sigma drift to pay for the round trip. That is not scalping.

### THE DECISIVE NUMBER — pooled jump-continuation, in-session, 10 liquid xyz+io names
Signed forward return after a 1m move of |r|>=THR (positive = continuation), bps:
 THR      n     f+1m     t       f+5m     t      f+15m     t     | bar to beat
   5   5326    -0.08  -0.40     -0.13  -0.28     -1.28  -1.81    |    9.0
  10   2488    -0.05  -0.13     +0.34  +0.39     -1.07  -0.84    |    9.0
  15   1356    +0.24  +0.39     +0.64  +0.46     -1.71  -0.87    |    9.0
  25    532    +1.45  +1.11     +3.24  +1.17     +0.59  +0.15    |    9.0
  50     87    +2.13  +0.49    +14.58  +1.62    +23.34  +1.97    |    9.0
 100      8   (too few)
At the only well-powered thresholds (n=2488 at THR=10, n=5326 at THR=5) the effect is
**+0.34 bps at best, t=0.39** — i.e. 0.34 bps of signal against a 9.0 bps toll. Net -8.66 bps
per round trip. Zero, measured, with 2,488 events.

### The one cell that looked like an edge, and why it is not
THR=50, h=15m: +23.34 bps, t=1.97, n=87 (script hip3_thr50_robust.py / hip3_thr50_cluster.py).
It fails every robustness check:
- Event dates: 09-16 x35, 09-17 x30, 09-18 x20, 09-15 x2. Three days.
- Coins: io:NBIS 34, xyz:SNDK 24, io:SNDK 20 — Nebius/SanDisk single-stock news week.
- Non-overlapping events only (>=15min apart, same coin): +22.53 bps but **t=1.29, n=46**.
- Cluster by (coin,day), t across 15 clusters: h=15 **+14.40 bps, t=1.22**; h=5 **+1.90, t=0.16**.
  Cluster means run -73.3 (xyz:SNDK 09-15) to +78.7 (io:SNDK 09-17) — and the sign is
  essentially a DAY effect (09-16 clusters mostly negative, 09-17 mostly positive). That is
  trend-day drift, not jump-continuation.
- Multiple comparisons: the sweep is 6 thresholds x 3 horizons pooled plus 15 coins x 3 x 3
  per-coin = 135+ tests. One |t|~2 is exactly the expected count of false positives.
- And a 15-minute hold is not "seconds-to-hours scalping" in any case.

### Reversion instead of momentum?
The significant signs are mostly NEGATIVE (reversion), which is what a thin book does:
xyz:SKHX L2 f+3 -0.55 bp (t=-2.45); io:ANTH 1m THR=10 f+1m -2.63 bp (t=-4.59, n=179);
para:ANSEM -9.71 bp (t=-7.34, n=2333); para:VST -1.65 bp (t=-3.05, n=422).
These are bid-ask bounce, not edge: para:ANSEM's "reversion" of 9.7-16.5 bp sits inside a
75-122 bp spread, and io:ANTH's 2.63 bp inside a spread whose p90 is 2.31 bp. Harvesting bounce
means being the resting maker on both sides — barred by GROUND_TRUTH constraint #2 (no
maker-rebate dependence), and at 0.015% maker each way it still needs >3 bp of bounce to clear.

## VERDICT: NO EDGE. Hypothesis falsified, and falsified for the OPPOSITE reason than expected.
The premise ("HIP-3 books are thin, so spreads are wide") is wrong for the names that matter:
xyz's 7 liquid perps quote 0.13-0.75 bps and eat $10k for 0.2-2.5 bps. There IS no wide-spread
staleness to exploit on liquid xyz. Where spreads ARE wide (para: 3.5-122 bps) the book cannot
absorb $1k, and the dislocations (max 44 bps) are smaller than the spread crossed to reach them.
Everything in between is a 0.3 bp signal against a 9 bp toll.
Bottom line for the fee question: with taker fees at 0.045%/side, the cost is 9.0 bps and HIP-3
spreads add only 0.1-0.8 bps on liquid names. Fees, not spreads, are the binding constraint —
so "find a thinner book" is structurally the wrong direction. Anything that trades HIP-3
profitably at our fee tier needs >9 bps of per-trade alpha, and nothing here is within 25x.
What would falsify this conclusion: a single instrument+condition with >=200 non-overlapping
in-session events whose signed forward return over <=5 minutes is >=12 bps with a
cluster-robust t>=3. Nothing in 15 instruments x 7 days x 75,000 bars came within 25x of that.
