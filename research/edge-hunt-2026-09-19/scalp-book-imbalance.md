# Scalp hypothesis: L2 order-book imbalance -> short-horizon price move

Slug: `scalp-book-imbalance`   Date: 2026-09-19   **VERDICT: NO_EDGE (confidently, not underpowered)**

Bar: **9 bp** round trip (0.045% taker each way). Conditional mean forward return must beat
9 bp PER TRADE net.

**Headline: the signal is real and extremely significant, and it is ~1/11th the size of the fee.**
Best number found anywhere in the search space: **+1.57 bp** (|imb5|>0.9, 30 s horizon, n=138,
NW t=4.39). Against the 9 bp bar that is **-7.4 bp per round trip**. Pooled headline case
(imb5 decile, 5 s, n=3,682): **+0.64 bp, NW t=9.35, block-boot 95% CI [0.51, 0.78] bp** — the
*upper* end of the confidence interval is 11.5x below the bar.

---

## What was actually run (not simulated)

Collector: `/home/ec2-user/.openclaw/workspace/hyper-trader/research/edge-hunt-2026-09-19/collect_l2.py`
```
POST https://api.hyperliquid.xyz/info   {"type":"l2Book","coin":C}
COINS = BTC ETH SOL HYPE DOGE XRP SUI LTC
sleep 0.33 s between calls -> 4.38 s median per-coin cadence
duration 2520 s (42 min), 2026-09-19 02:28 -> 03:11 UTC
3950 snapshots written (9 transient null-levels errors, dropped)  ~490 snapshots per coin
raw: research/edge-hunt-2026-09-19/data/l2_snaps.jsonl  (top 20 levels/side, px/sz/n, exch ts + local ts)
```
Analysis: `analyze_imb.py` (main), `analyze_extra.py` (tails / flow / horizon sweep).
Full raw output: `data/final_main.txt`, `data/final_extra.txt`.
NOTE: no numpy in the venv (`.venv/bin/python -m pip` is also absent) — both scripts are pure-Python.

Features per snapshot: `imb_N = (sum bpx*bsz - sum apx*asz)/(sum both)` over top N levels,
N in {1,5,20}, notional-weighted; plus microprice deviation in bps.
Forward returns at h in {5,30,60}s (nearest snapshot, tolerance max(2.5 s, 0.4h)):
`ret_mid`, and the honest executable `ret_long_exec = 1e4*(bid_{t+h} - ask_t)/mid_t`.
Overlapping windows -> **Newey-West** t-stats (lag = h/dt + 1) and a moving-block bootstrap.

## Book inventory (43 min medians)

| coin | n | spread (bp) | top-1 notional | top-20 notional |
|---|---|---|---|---|
| BTC  | 492 | 0.12 | $803,045 | $8,930,454 |
| ETH  | 491 | 0.38 | $692,046 | $13,338,400 |
| HYPE | 489 | 0.11 | $16,299  | $184,061 |
| SOL  | 494 | 0.88 | $123,956 | $7,521,957 |
| XRP  | 488 | 0.71 | $73,869  | $2,894,596 |
| DOGE | 498 | 0.45 | $2,368   | $286,558 |
| LTC  | 495 | 0.68 | $1,412   | $103,240 |
| SUI  | 503 | 0.84 | $1,400   | $70,489 |

Spreads are 0.11-0.88 bp. **The spread is not the problem — the 9 bp fee is 10-80x the spread.**

## Result 1 (the killer): ORACLE BOUND — E|forward mid move|

A *perfect* sign predictor earns E|ret| gross per round trip. If E|ret| < 9 bp, no signal of any
kind can pay fees at that horizon.

```
coin   h=5s    h=30s   h=60s      (mean |mid return|, bps)
BTC    0.29    1.37    2.16
ETH    0.48    2.30    3.70
SOL    0.64    2.64    3.95
DOGE   1.06    3.51    5.45
XRP    1.23    4.80    7.49
LTC    1.24    4.25    6.17
SUI    1.72    5.83    9.31
HYPE   1.50    5.25    7.47
n = 453-494 per cell
```
At 5 s, perfect foresight grosses 0.29-1.72 bp -> **loses 7.3-8.7 bp per round trip.** Seconds-scale
taker scalping on HL majors is arithmetically impossible regardless of signal quality. Only SUI at
60 s (9.31 bp) even reaches the fee, and that requires 100% directional accuracy.

## Result 2: imbalance decile-conditional forward mid return (pooled, all 8 coins)

Directional signal = (top-decile return) and (-bottom-decile return) pooled.

| feature | h | n | corr | D10-D1 (bp) | mean signal (bp) | NW t | boot 95% CI | **net after 9 bp** |
|---|---|---|---|---|---|---|---|---|
| imb5  | 5s  | 3682 | 0.166 | 1.28 | **+0.64** | 9.35 | [0.51, 0.78] | **-8.80** |
| imb5  | 30s | 3811 | 0.096 | 1.96 | +0.98 | 4.40 | [0.53, 1.44] | -8.45 |
| imb5  | 60s | 3878 | 0.057 | 1.82 | +0.91 | 2.44 | [0.15, 1.64] | -8.54 |
| imb1  | 5s  | 3682 | 0.163 | 1.34 | +0.67 | 9.35 | [0.54, 0.81] | -8.80 |
| imb1  | 30s | 3811 | 0.092 | 2.54 | +1.27 | 4.90 | [0.77, 1.83] | -8.21 |
| imb20 | 5s  | 3682 | 0.075 | 0.49 | +0.24 | 3.20 | [0.09, 0.40] | -9.23 |
| imb20 | 30s | 3811 | 0.040 | 0.46 | +0.23 | 0.77 | [-0.41, 0.82] | -9.24 |
| micro | 5s  | 3682 | 0.116 | 0.78 | +0.39 | 4.47 | [0.22, 0.56] | -9.57 |

Per-coin 5 s corr: ETH 0.388, SOL 0.342, BTC 0.316, XRP 0.283, HYPE 0.159, DOGE 0.129,
SUI 0.109, LTC 0.043. Sign is consistent (7/8 positive) — this is a genuine microstructure effect,
just a 1 bp one. Shallow books (N=1, N=5) beat deep (N=20); deep-book imbalance is basically noise.

## Result 3: extreme tails don't rescue it

| \|imb5\| > | h | n | mean (bp) | NW t | net vs 9 bp taker | net vs hypothetical 3 bp maker RT |
|---|---|---|---|---|---|---|
| 0.5 | 5s  | 1181 | 0.48 | 8.97 | -9.02 | -2.52 |
| 0.8 | 5s  | 340  | 0.79 | 8.69 | -8.56 | -2.21 |
| 0.8 | 30s | 356  | 1.14 | 4.69 | -8.20 | -1.86 |
| **0.9** | **30s** | **138** | **1.57** | **4.39** | **-7.71** | **-1.43** |
| 0.9 | 60s | 141  | 1.19 | 2.54 | -8.08 | -1.81 |
| 0.9 | 180s| 137  | -1.17| -1.31| -10.47 | -4.17 |

Conditioning harder monotonically raises the effect from 0.48 -> 1.57 bp and it plateaus there.
Extrapolating: you would need |imb| conditioning to produce a ~6x further gain to reach 9 bp; the
curve is flat, so no.

**Even at a 3 bp maker-in/maker-out round trip (0.015% x2 — the base HL maker tier, no rebate
dependence) the best cell is still -1.43 bp.** So this fails even the generous maker version, before
any adverse-selection cost. Which is the real point: at |imb5|>0.9 your passive bid is the side
about to be run over.

## Result 4: horizon sweep — nothing out to 10 min clears the bar

```
  h(s)       n   mean bp   NW t   E|ret| bp   net-9bp
     5     738      0.64    9.36       1.02     -8.80
    10     754      0.81    8.01       1.73     -8.64
    20     764      0.99    5.96       2.89     -8.45
    30     764      0.98    4.32       3.75     -8.45
    60     776      0.91    2.39       5.72     -8.54
   120     764      0.05    0.09       8.47     -9.39
   240     738     -1.06   -0.87      11.28    -10.49
   480     686     -1.93   -0.83      17.35    -11.36
   600     660     -1.86   -0.62      19.04    -11.28
```
Signal peaks at ~1 bp around 20-30 s, is fully dead by 120 s, and flips mildly negative
(mean-reverting) past 240 s. Classic already-arbitraged microstructure: information decays inside
the time it takes to become worth the fee. Meanwhile E|ret| grows as sqrt(h) — at 600 s there is
19 bp of movement available, but imbalance predicts none of its sign (t = -0.62).

## Result 5: flow (delta imbalance) is worse than level

d(imb5) decile, pooled: 5 s +0.34 bp (t=4.92), 30 s +0.76 bp (t=3.45), 60 s +0.65 bp (t=1.56).
All well under the level-based signal and all -8.8 bp or worse net.

## Power: are 42 min enough?

Yes, for the question asked, and this needs stating precisely because the instruction was to say
UNDERPOWERED rather than dress a weak correlation as a finding:
- We are decisively powered to **reject the 9 bp hypothesis**. The 5 s pooled bootstrap 95% CI is
  [0.51, 0.78] bp; 9 bp is ~50 bootstrap SDs away. No plausible sampling error closes an 8.4 bp gap.
- We are also powered to **confirm the effect is nonzero** (NW t = 9.35 with overlap-corrected SE).
  So this is not "noise" — it is a real, tiny, fully-priced effect.
- What 42 min does NOT establish: regime dependence. This window was quiet (BTC 5 s |move| = 0.29 bp).
  In a high-vol regime E|ret| scales up and the oracle bound could clear 9 bp at 30-60 s. The
  *correlation* would have to survive too, and Result 4 shows corr decays exactly where E|ret| grows.
  Retesting during a genuine vol event is the only remaining question, and it is a low-prior one.
- Single 42-min window = one draw of market conditions. Treat "1 bp, not 9 bp" as robust (8 coins,
  4 features, 9 horizons, 3 tail thresholds all agree); treat the exact 0.64 bp as window-specific.

## Conclusion

**NO_EDGE.** L2 book imbalance on HL majors carries a genuine, highly significant 0.5-1.6 bp of
forward-mid predictability at 5-30 s. We pay 9 bp. It is short by a factor of ~6-14x, and it fails
even against a 3 bp maker round trip. Two independent reasons it cannot be fixed:
1. Oracle bound: at 5 s there is only 0.3-1.7 bp of total movement to capture. Perfect prediction loses.
2. Decay profile: signal dies by 120 s, exactly when enough movement (8.5 bp) accumulates to matter.

Do not build an imbalance scalper. Do not "improve the signal" — the ceiling is the oracle bound,
not the model. Any future HL scalping idea should be pre-screened with the 5-line oracle bound test
(E|forward move| at the intended holding period vs 9 bp) BEFORE any signal work; it kills most
seconds-to-minutes ideas in one query.

### What would falsify this
A repeat of the identical collection during a high-volatility window (BTC 30 s E|ret| >= 15 bp, i.e.
~7x this window) showing |imb5|>0.9 decile mean forward return >= 12 bp at 30-60 s with NW t > 3 and
n > 300. Absent that, the oracle bound forecloses it.
