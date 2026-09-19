# Spot-Perp Basis on Hyperliquid — edge hunt 2026-09-19

Hypothesis: the perp mark vs spot mid basis on HL widens enough, often enough, and
converges predictably enough to beat 18bp round-trip taker cost on BOTH legs.

Cost model (from GROUND_TRUTH.md): 4.5bp taker per side per leg.
A cash-and-carry basis trade = 2 legs (spot + perp), open + close = 4 taker fills
= 18bp of notional round trip. Plus spot leg on HL charges the same taker rate.
That is the bar. Anything under 18bp gross is dead.

## Log

### Step 1 — enumerate the overlap (spotMeta x meta)
Command: `.venv/bin/python /tmp/enum.py` (POST /info {"type":"meta"} and {"type":"spotMeta"})
- 234 perps, 328 spot pairs, 311 USDC-quoted.
- Direct name overlap: 8 — PURR, TRUMP, PUMP, HYPE, BERA, MON, STABLE, AZTEC.
- PLUS Unit-bridged spot tokens whose base maps to a perp (U-prefix):
  UBTC(@142)->BTC, UETH(@151)->ETH, USOL(@156)->SOL, UPUMP(@188)->PUMP,
  UENA(@206)->ENA, UXPL(@210)->XPL, UWLD(@224)->WLD, UMON(@243)->MON,
  UMEGA(@257)->MEGA, UZEC(@272)->ZEC, UAVAX(@306)->AVAX.
=> 19 candidate spot/perp pairs total.
Note: Unit tokens are BRIDGED. Spot/perp deviation there can be bridge friction,
not free money — you cannot fungibly deliver UBTC into a BTC perp.

### Step 2 — 90d hourly basis distribution (1h candleSnapshot, close-vs-close)
basis_bps = (perp_close - spot_close)/spot_close * 1e4.  n = matched hourly bars, 90 days.
Script /tmp/basis.py, data /tmp/candles.json.

```
pair                 n    mean     med    m|b|     p50     p90     p99      max  %>18bp  spot$vol/h  trd/h
@9|TRUMP          191966738614.579280322.666738614.579280322.692446521.7103049782.6104750870   100.0           0      0
@20|PUMP          2160280139.0237264.7280139.0237102.2474892.7535924.4   569027   100.0           0      0
@117|BERA         19622694379.42670062.52694379.42670000.03173620.73410028.1  3658713   100.0           0      0
@129|MON          2025 87734.2 12657.6 87734.2 12657.6427764.7451137.3   507011   100.0           0      0
@285|AZTEC        2158   -44.5    13.0   336.2   156.5   891.4  1728.4     1850    91.5           0      0
@258|STABLE       2153   -30.9   -24.0   125.2    78.3   288.7   517.1     5177    85.9           0      0
@306|AVAX         2161    13.2    15.7    73.5    50.8   147.7   441.3     1336    82.5           0      0
@206|ENA          2161    39.2    24.3    86.1    53.9   180.9   607.2     1127    80.8          84      2
@243|MON          2161     7.6     5.3    46.1    34.7   102.7   201.6      340    70.5          38      1
PURR/USDC|PURR    2161    26.6    23.4    35.2    28.4    75.2   129.2      197    65.5       21688    122
@210|XPL          2161     5.4     4.9    17.6    12.2    40.5    85.5      299    35.7        2800     32
@188|PUMP         2161     8.4     8.3    12.8    10.3    26.2    52.4      272    23.0       36617    179
@272|ZEC          2161     1.3     4.5    13.5     8.6    25.1    86.8      677    19.3      100577    247
@156|SOL          2161     2.6     2.9     5.2     4.4    10.2    17.9       25     1.0      136194    196
@151|ETH          2161     3.3     3.3     4.8     4.2     9.5    15.4       26     0.7      263806    321
@107|HYPE         2161    -1.2    -1.8     3.7     3.2     7.2    12.1       21     0.2     2169158   2414
@142|BTC          2161     3.5     4.2     4.8     4.5     8.4    12.5      101     0.2      708208    653```

READ: the top 4 rows (@9 TRUMP, @20 PUMP, @117 BERA, @129 MON) show basis of
10,000-6,700,000 bps and have MEDIAN SPOT $VOLUME OF $0/hour and 0 trades/hour.
These are dead ghost spot listings (superseded by the Unit @188/@243 listings).
Their "basis" is a stale/never-traded print, not a price. DISCARDED — not tradeable.
Same for @285 AZTEC and @258 STABLE and @306 AVAX and @206 ENA and @243 MON:
median spot volume $0-84/hour. At $10 min order size these books cannot absorb anything.

The ACTUALLY LIQUID overlap (median spot $vol/hour):
  HYPE $2.17M, UBTC $708k, UETH $264k, USOL $136k, UZEC $101k, UPUMP $37k,
  PURR $22k, UXPL $2.8k.
For those, |basis| p90 = 7.2 / 8.4 / 9.5 / 10.2 / 25.1 / 26.2 / 75.2 / 40.5 bps
and the fraction of hours with |basis| > 18bp (the cost bar) is:
  HYPE 0.2%, BTC 0.2%, ETH 0.7%, SOL 1.0%, ZEC 19.3%, PUMP 23.0%, PURR 65.5%, XPL 35.7%

### Step 3 — convergence test, and the artifact that kills it
Signal: fair = 168h rolling mean of basis; trade when |basis - fair| > thr, toward fair.
Gross = basis change in our favour, in bps. COST = 18bp. hold = 8h.
`lag` = hours between observing the closing basis and entering (lag 0 = same bar close,
which is NOT executable; lag 1 = the first bar you could actually trade on).
t is computed on NON-OVERLAPPING signals only (n_no).

```
PURR_USDC_PURR       20   0    8  1146   33.93   15.93     12.24   227
PURR_USDC_PURR       20   1    8  1145    5.56  -12.44      1.14   202
PURR_USDC_PURR       20   2    8  1144    5.16  -12.84      0.92   183
PURR_USDC_PURR       30   0    8   788   39.85   21.85     13.04   207
PURR_USDC_PURR       30   1    8   787    8.16   -9.84      1.50   184
PURR_USDC_PURR       30   2    8   787    5.54  -12.46      2.15   172
@272_ZEC             20   0    8   357   36.41   18.41      6.43   119
@272_ZEC             20   1    8   357   14.20   -3.80      0.33   114
@272_ZEC             20   2    8   357   13.55   -4.45      3.16   106
@272_ZEC             30   0    8   151   62.15   44.15      6.09    81
@272_ZEC             30   1    8   151   21.05    3.05      0.77    76
@272_ZEC             30   2    8   151   22.05    4.05      3.02    73
@188_PUMP            20   0    8   241   31.48   13.48     10.40   111
@188_PUMP            20   1    8   241    1.34  -16.66      0.85   105
@188_PUMP            20   2    8   241    0.69  -17.31      0.52   102
@188_PUMP            30   0    8    99   44.36   26.36      9.53    67
@188_PUMP            30   1    8    99    2.50  -15.50     -0.06    62
@188_PUMP            30   2    8    99    1.04  -16.96      0.28    61
@210_XPL             20   0    8   572   38.01   20.01     14.63   181
@210_XPL             20   1    8   572    1.04  -16.96     -0.21   163
@210_XPL             20   2    8   572   -1.22  -19.22      1.23   149
@210_XPL             30   0    8   348   46.76   28.76     15.69   151
@210_XPL             30   1    8   348    3.54  -14.46      1.51   139
@210_XPL             30   2    8   348   -0.01  -18.01     -0.08   129```

VERDICT ON CONVERGENCE: the whole effect is a same-bar artifact.
  PURR   thr30: lag0 +39.9bp -> lag1 +8.2bp (net -9.8bp), t 13.0 -> 1.5
  XPL    thr30: lag0 +46.8bp -> lag1 +3.5bp (net -14.5bp), t 15.7 -> 1.5
  PUMP   thr30: lag0 +44.4bp -> lag1 +2.5bp (net -15.5bp), t 9.5 -> -0.06
  ZEC    thr30: lag0 +62.2bp -> lag1 +21.1bp (net +3.1bp), t 6.1 -> 0.77 (n.s.)
This is textbook bid-ask bounce: on a thin spot book the hour's LAST TRADE prints at
the bid or the ask, the close-vs-close basis looks extreme, and it "reverts" on the
next print because that one lands on the other side. You cannot trade a stale print.
One bar of execution delay removes 85-95% of the measured effect and puts every
liquid pair below the 18bp cost bar.

### Step 4 — LIVE executable basis + book depth (12 simultaneous l2Book snapshot rounds, ~10min, 2026-09-19)
midbas = (perp_mid-spot_mid) in bps. exA = (perp_bid - spot_ask)/spot_ask (the basis you
actually capture buying spot / shorting perp). spotSpr/perpSpr = full quoted spread in bps.
$25bp = min(bid-side,ask-side) resting notional within 25bp of mid. Script /tmp/l2.py.

```
pair               n   midbas     exA     exB  spotSpr  perpSpr  spot$25bp  perp$25bp
PURR/USDC|PURR    12      6.4   -16.0   -28.9     29.4     15.6        150        330
@107|HYPE         12      2.9     2.4    -3.4      0.9      0.1     135117      46164
@142|BTC          12      8.7     8.6    -8.9      0.1      0.1     470688    2550093
@151|ETH          12     10.4    10.1   -10.8      0.4      0.4     322424    3712750
@156|SOL          12      2.6     1.6    -3.6      1.1      0.9     279964    3677888
@272|ZEC          12     -6.9    -8.4     5.4      2.4      0.6      83866     500429
@188|PUMP         12      2.7     0.6    -4.8      1.5      2.7       6488      83162
@210|XPL          12     11.9     7.0   -16.7      8.7      1.0       5470      11755```
All-in round-trip cost of a cash-and-carry = spotSpr + perpSpr + 18bp fees:
  BTC 18.2, ETH 18.8, HYPE 19.0, SOL 20.0, ZEC 21.0, PUMP 22.2, XPL 27.7, PURR 63.0
The live mid-basis is 2.6-11.9bp on every liquid pair — BELOW the 18bp fee bar before
you even pay a spread. There is no instantaneous arb.
CAPACITY, spot leg within 25bp: HYPE $135k, BTC $471k, ETH $322k, SOL $280k, ZEC $84k,
PUMP $6.5k, XPL $5.5k, **PURR $150**. PURR's 29bp spread and $150 of depth make its
wide basis untradeable at any size, which is exactly why the basis stays wide.

### Step 5 — funding history, 90d (fundingHistory, n=2160 hourly prints per coin)
```
PURR  sum=+725.7bp  mean=+0.336bp/h  APR 29.43%  100.0% of hours positive
HYPE  sum=+246.0bp  mean=+0.114bp/h  APR  9.98%   91.3% positive
ZEC   sum=+310.4bp  mean=+0.144bp/h  APR 12.59%   93.5% positive
PUMP  sum=+322.6bp  mean=+0.149bp/h  APR 13.09%   96.2% positive
XPL   sum=+299.2bp  mean=+0.139bp/h  APR 12.14%   98.2% positive
BTC   sum=+198.1bp  mean=+0.092bp/h  APR  8.03%   89.9% positive
ETH   sum=+193.8bp  mean=+0.090bp/h  APR  7.86%   89.0% positive
SOL   sum=+144.9bp  mean=+0.067bp/h  APR  5.87%   81.3% positive
```

### Step 6 — carry backtest, 90d hourly (funding + basis MTM - all-in cost)
PnL_bps(long spot / short perp) = sum(funding over hold) + (basis_entry - basis_exit) - cost.
Overlapping hourly starts; n = number of start hours. NOTE: only 3 independent 30d windows
in 90 days, so t_no on the 30d rows is meaningless — see Step 7 for the powered version.
```
coin   hold_d     n  fund_bp spread_bp  cost  net_bp      sd   worst  %win   t_no
PURR        7  1992     56.7      -1.2  63.0    -7.5    69.4  -231.7  39.9  -0.99
PURR       14  1824    113.5      -2.5  63.0    47.9    83.6  -213.1  70.6   1.34
PURR       30  1440    240.8      -4.6  63.0   173.2   101.1   -97.4  97.6   0.00
HYPE        7  1992     19.2       0.1  19.0     0.3     9.5   -24.9  44.8   0.18
HYPE       14  1824     39.0       0.3  19.0    20.3    12.1   -12.3  98.8   5.03
HYPE       30  1440     85.3       0.1  19.0    66.4    11.7    22.5 100.0   0.00
BTC         7  1992     15.8       0.4  18.2    -2.0     8.5  -106.5  39.1  -1.04
BTC        14  1824     32.7       1.4  18.2    15.8    10.8   -81.2  96.3   3.31
BTC        30  1440     69.0       3.1  18.2    53.9     9.8   -51.9  99.9   0.00
ETH         7  1992     15.6       0.4  18.8    -2.8     9.9   -47.5  38.9  -1.15
ETH        14  1824     33.1       1.4  18.8    15.7    11.1   -31.0  93.2   2.05
ETH        30  1440     71.0       3.2  18.8    55.4     9.6    18.0 100.0   0.00
SOL         7  1992     12.1       0.4  20.0    -7.5    11.9   -51.4  25.4  -3.27
SOL        14  1824     25.5       1.6  20.0     7.1    15.1   -33.3  65.4   0.89
SOL        30  1440     53.5       2.9  20.0    36.4    17.0   -12.3  99.7   0.00
ZEC         7  1992     25.5       1.0  21.0     5.5    45.7  -612.5  55.1   0.49
ZEC        14  1824     52.3       1.4  21.0    32.7    49.7  -607.4  88.7   2.00
ZEC        30  1440    114.5       5.2  21.0    98.6    48.7  -260.2  99.6   0.00
PUMP        7  1992     25.8       0.6  22.2     4.2    26.8  -272.8  55.9   0.69
PUMP       14  1824     52.9       1.6  22.2    32.2    31.0  -130.5  88.7   2.64
PUMP       30  1440    114.5       2.1  22.2    94.5    41.3   -73.8  99.4   0.00
XPL         7  1992     23.5       0.6  27.7    -3.6    36.3  -285.4  44.7  -0.27
XPL        14  1824     47.4       1.5  27.7    21.2    39.5  -272.8  75.1   1.53
XPL        30  1440     99.9       2.3  27.7    74.5    39.2   -58.1  96.6   0.00```
Basis MTM is a rounding error on every liquid pair (mean +0.1 to +5.2bp over 30d) —
the basis is stationary and tight, so the trade is PURE FUNDING CARRY, not convergence.
7-day holds are net NEGATIVE for BTC/ETH/SOL/XPL/PURR: cost dominates at short horizons.

### Step 7 — 18-month funding regime test (fundingHistory, n=12,960 hours per coin,
2025-03-28 .. 2026-09-19), bucketed by calendar month (19 buckets, ~18 independent)
```
HYPE  0.1545 bp/h  APR 13.54%  92.3% hrs pos   19/19 MONTHS POSITIVE  worst month +36.0bp
BTC   0.0898 bp/h  APR  7.87%  84.4% hrs pos   18/19 months positive  worst month  -7.0bp (2026-04)
ETH   0.0833 bp/h  APR  7.30%  82.3% hrs pos   16/19 months positive  worst month -24.2bp (2025-04)
SOL   0.0307 bp/h  APR  2.69%  68.8% hrs pos   12/19 months positive  worst month -135.2bp (2026-02)
```
SOL carry is not investable (7 negative months, -17.6% APR in 2026-02).
HYPE is the standout: not one negative month in 19, worst month +36bp vs a 19bp all-in
round-trip cost.
