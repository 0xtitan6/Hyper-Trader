# Skeptic pass: costs-vs-effect attack on `scalp-volatility-timing`

Reviewer role: refute. Scripts in `skeptic/`, run with `../../.venv/bin/python`.
All numbers below are mine, recomputed from `data/*_1h_long.json` (36 coins, 5000-bar
aligned contiguous grid 2026-02-22 20:00 -> 2026-09-19 03:00 UTC, zero non-1h gaps) plus
fresh live `l2Book` / `fundingHistory` pulls on 2026-09-19 ~04:00-04:15 UTC.

## What replicates exactly (credit where due)
- XMR hr20 open->close: n=209, mean **+25.51bp**, se 5.39, **t=+4.73**. Identical.
- XMR full hourly profile identical (hr07 +24.92 t=+4.56, hr12 -19.88 t=-3.40).
- 12-coin index drift: hr20 +9.74bp t=+2.25, max|t| over 24 hours = 2.25 < 2.40 expected
  max of 24 iid normals. Drift-profile split-half corr **-0.096** (they said -0.103).
- Vol clock: loudest hr14 81.2bp = 1.29x, quietest hr07 54.7bp = 0.87x, **ratio 1.48x**,
  split-half corr of the 24-point profile **+0.850**, H1-top6 vs H1-bot6 in H2 = 1.33x.
- XMR hr20 gross hit rate 0.622, gross median +15.43bp, 10%-trim +21.38bp.
- Funding: I paginated `fundingHistory` for XMR over the whole window (5000 prints).
  Mean **+0.343 bp/hr**, median +0.125, p90 +0.954, 96.7% positive; the 21:00 print (the
  one a 20:00->21:00 long pays) averages **+0.346bp**. The note assumed 0.40bp — slightly
  conservative. Funding is NOT where this dies.

## Where it dies: the cost number is a single lucky L2 snapshot
`tod_cost.py` took ONE book snapshot and got XMR spread 0.18bp / RT slip $640 = 0.44bp.
0.18bp on a $570 mid is exactly ONE tick (5-sig-fig price grid) — i.e. the tightest book
physically possible. I resampled the same book 12x over ~40s (`skeptic/r4_xmrdepth.py`):

| stat | claim (1 snap) | mine (12 snaps, same hour) |
|---|---|---|
| spread | 0.18bp | median **2.11bp**, range 0.18 - 5.98 |
| RT slip $640 | 0.44bp | median **2.56bp**, mean 2.89, range 1.00 - 7.38 |
| RT slip $10k | 6.96bp | median 6.02bp, **unfillable in the visible 20 levels 5/12 snaps** |
| visible bid book | (top5 $1,799) | $5.8k - $6.9k in 5 snaps; a $10k exit sweeps it out |

All-in at $640 = 9.0 fee + 2.56 slip + 0.35 measured funding = **11.9bp, not 9.84bp**.
At $10k = 9.0 + 6.0 + 0.35 = **15.4bp** (and only when the book is there at all).

## Cost ladder on the survivor (n=209, `skeptic/r11_boot.py`)
Distribution is skew +0.92, kurtosis 6.20 -> the t-stat is the wrong lens; sign/median too.

| all-in cost | net mean | net **median** | net hit | binom p | 7d-block boot 95% CI | P(net<=0) |
|---|---|---|---|---|---|---|
| 9.84 (claimed) | +15.67 | +5.59 | 0.555 | 0.064 | [+3.74,+28.91] | 0.0026 |
| **11.90 (measured, $640)** | **+13.61** | **+3.53** | 0.536 | 0.166 | [+1.68,+26.85] | 0.0102 |
| 15.40 ($10k) | +10.11 | **+0.03** | 0.502 | 0.500 | **[-1.82,+23.35]** | 0.049 |

The note lists "median +15.43bp, hit rate 62.2%" inside its **net** bullet block. Those are
the GROSS median and GROSS hit rate. Net median is +5.6bp at their own cost, +3.5bp at mine,
and **+0.03bp at $10k** — the median trade is exactly break-even at the size they call
executable, and the net hit rate there is 50.2% (binomial p=0.50).

## Concentration is worse than the trimmed mean suggests
Top-10 gross days: +378, +330, +299, +267, +196, +196, +178, +165, +150, +149 bp
(2026-06-15, 06-04, 05-05, 04-09, 09-06, 06-16, 06-11, 09-04, 06-05, 08-30).
- drop top 1 day  -> net@11.9 +11.8bp
- drop top 3 days -> +8.97bp  (below the 9bp bar)
- drop top 5 days -> +6.90bp
- drop top 10 (4.8% of trades, **43.3% of the gross sum**) -> +3.16bp
- drop top 20 (9.6% of trades, 68.7% of the sum) -> **-3.18bp**
Per-trade sd is 78bp against a claimed 13.6bp net.

## After honest cost NO subsample is significant
| cut | gross | net@11.9 | net t |
|---|---|---|---|
| full 209 | +25.51 | +13.61 | +2.52 |
| Q1 (52) | +12.44 | +0.42 | +0.04 |
| Q2 (52) | +34.98 | +22.96 | +2.01 |
| Q3 (52) | +29.95 | +17.93 | +1.49 |
| Q4 (52) | +22.76 | +10.74 | +1.10 |
| last 52d | +23.85 | +11.95 | +1.20 |
| drop best month (Jun) | +18.07 | +6.05 | **+1.19** |
Their "drop the best month, net +8.27bp, still clears" becomes **+6.05bp, t=+1.19** once the
cost is the measured one. Every honest subsample t is ~1.2, not 2.9.

## Their permutation null is structurally broken (and it matters both ways)
`tod_wide.py` does `Ms = np.roll(M, sh, axis=1)` with a single common shift while the
`hours` label vector stays fixed. Because `hours[i] = (i + h0) mod 24` on a contiguous
grid, bucket `h` after the roll contains `old[(i-sh) mod N]` for all `i == h mod 24` —
every one of which came from original hour `(h-sh) mod 24`, except the `sh` wrapped
elements which came from original hour `(h-sh+ N mod 24) mod 24` (N=5000, N mod 24 = 8).
**So each "null" bucket is a two-hour blend of REAL hour buckets.** The null contains the
alternative in diluted form; that is why its max|t| p50 is 4.06 (a diluted +25.5bp effect)
instead of ~3.1. It cannot ever return a small p-value, so the quoted FW p = 0.043-0.140 is
not a measurement of mining inflation at all.

Replacement (`skeptic/r5_nullnet.py`, `r8_oos.py`): stationary block bootstrap, block
L=168h (and 336h), **common block starts across all 36 coins** so within-coin
autocorrelation, fat tails, coin drift and cross-coin correlation are all preserved, while
random non-24-aligned starts scramble the hour labels. 400 reps.

| statistic over the 864-cell grid | null p50 | p90 | p95 | max | observed | FW p |
|---|---|---|---|---|---|---|
| max \|gross t\| | 3.15 | 3.77 | 3.95 | 4.74 | **4.73** | **0.003** |
| \|gross bp\| of the max-\|t\| cell | **20.54** | 31.25 | 33.81 | - | **25.51** | **0.265** |
| net bp of the max-\|t\| cell (per-coin measured cost) | **+9.80** | +20.62 | +24.36 | +39.92 | **+14.12** | **0.265** |
| net t of the max-\|t\| cell | +1.41 | +2.20 | +2.49 | +3.47 | +2.62 | 0.035 |
| max net bp anywhere in the grid | +17.51 | +23.80 | +27.04 | +39.92 | +20.56 (XPL hr20) | 0.278 |
(L=336 gives the same picture: 3.14 / 3.93, net-of-max-t p50 +8.24, FW p 0.215.)

**This is the whole refutation in one line: mining 864 cells of pure noise manufactures a
winner with +20.5bp of in-sample gross drift and +9.8bp of in-sample NET profit, because
the selection bias (~20bp) is more than twice the 9bp fee bar.** The observed winner is
+25.51bp gross / +14.1bp net. Excess over what noise-mining produces by construction:
**+4.97bp gross — 55% of the 9bp bar.** 26.5% of pure-noise reps beat the observed cell on
the quantity that actually pays (bp, not t).

The gross t-stat IS a genuine outlier (FW p=0.003 under the correct null — their own null
was too harsh here). But t is scale-free and you are not paid in t. The null's max-|t| cell
is typically a high-vol coin whose 3.15-sigma is worth ~20bp; XMR's 4.73-sigma is worth
25.5bp only because its se is small (5.39bp). Fees are denominated in bp, so a 4.7-sigma
anomaly on a low-vol-per-bucket coin converts into a payout that mining noise reproduces a
quarter of the time.

## Out-of-sample: the procedure pays negative, and the twin cell already died
`skeptic/r8_oos.py`. Per coin, take the best hour by |t| on the first 104 days, trade it
(with its sign) over the last 104 days, charge per-coin measured cost:
- pooled **n=3748 trades, net -14.61bp/trade, t=-9.85**
- per-coin OOS gross mean -3.11bp; only **39% of the 36 picks are gross-positive OOS**,
  and **6% (2/36) are net-positive**
- grid top-1 pick on H1 was **XMR hr07** (H1 t=+3.99), not hr20 -> H2 net +6.26bp, t=+0.85

**XMR hr07 is the controlled experiment the note needed and skipped.** It is the
statistical twin of hr20 (full-sample +24.92bp, t=+4.56 vs +25.51bp, t=+4.73):

| window | hr07 gross | net@11.9 | net t | | hr20 gross | net@11.9 | net t |
|---|---|---|---|---|---|---|---|
| full 208d | +24.92 | +13.02 | +2.38 | | +25.51 | +13.61 | +2.52 |
| H1 (104) | +32.19 | +20.29 | +2.52 | | +23.37 | +11.47 | +1.53 |
| H2 (104) | +17.65 | +5.75 | +0.78 | | +27.67 | +15.77 | +2.02 |
| **last 52d** | **+11.52** | **-0.38** | **-0.04** | | +23.85 | +11.95 | +1.20 |

A cell with an in-sample t of +4.56 on this exact grid is at **exactly zero net** over the
most recent 52 days. That is what "one of 864 cells with t>4.5" is worth forward.

Their own walk-forward, re-costed: top-1 gross was +18.28bp/trade (n=141, weighting their
monthly table). Their net +8.00bp assumed ~10.3bp cost; with measured costs (XMR 11.90,
ETHFI 16.39) it is **+5.4bp, t~0.72**. Top-5 was -3.31bp -> ~-5.4bp.

## Vol clock: real, but the "1.48x more gross per fixed 9bp fee" framing is wrong
I reproduce 1.48x and split-half +0.850 exactly. The inferential step to "any scalp is 48%
less marginal at 14:00" assumes cost is a constant 9bp. It is not: only the fee is fixed.
Cross-sectionally over the 36 coins, corr(mean |1h move|, live spread) = **+0.467** and
corr(mean |1h move|, RT slip at $640) = **+0.553** — and within XMR alone the spread moved
0.18 -> 5.98bp inside a 40-second window. Spread/impact is ~25% of the $640 all-in cost and
~40% at $10k, and it co-moves with vol, so the true loud-hour advantage is on the fee
component only and is materially less than 1.48x. The scheduling conclusion (don't scalp
03:00-11:00 / 23:00 UTC) survives; the magnitude does not.
