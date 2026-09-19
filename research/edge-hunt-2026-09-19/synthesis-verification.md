# Synthesis + verification pass (final reporter)
Date 2026-09-19. Slug: synthesis-verification.

## Situation found on arrival
Two workflows had been launched:
 - wf_bf1bea54-376 `hyper-edge-hunt`  : 8 hypotheses
 - wf_44bd5aca-b7f `hyper-scalp-hunt` : 6 hypotheses
Both were INTERRUPTED. The RESULTS JSON handed to me was `{"survivors":[],"killed":[],"negatives":[]}`
— i.e. not "everything was refuted", but "the pipeline returned nothing". No agent's structured
finding survived, and NO adversarial-verification (skeptic) agent ever ran.

Notes actually on disk (5 of 14):
  basis-spot-perp.md        COMPLETE through Step 7  <- the only substantive result
  hip3-dislocation.md       Step 1 only (but Step 1 is a kill shot)
  new-listing.md            Step 1 only (cohort enumeration)
  scalp-book-imbalance.md   design + data collected, "## Results (filled in below)" EMPTY
  scalp-funding-clock.md    data constraints + data collected, no results
Missing entirely: funding-harvest, liquidation-cascade, outcome-arb, fee-tier-reachability,
our-own-losses, scalp-whale-followthrough, scalp-lead-lag, scalp-hip3-thin, scalp-volatility-timing.

## What I am doing about it
1. Run the two abandoned scalp analyses — their data is already on disk, so the result is recoverable.
2. Do fee-tier-reachability myself (pure arithmetic, decisive, closes a whole strategy class).
3. Act as the missing SKEPTIC against the one claim that looks alive: HYPE spot-perp funding carry.

---
## RECOVERED RESULT 1 — scalp-book-imbalance (analysis the original agent never ran)
Command: `.venv/bin/python research/edge-hunt-2026-09-19/analyze_imb.py`
Data already on disk: data/l2_snaps.jsonl, 825 snapshot lines, 8 coins, ~760s span each,
median poll dt 4.38s. Per-coin n per horizon ~90-125; POOLED n = 778-893 obs.

Book quality (median): spread BTC 0.12bp, HYPE 0.11bp, DOGE 0.34bp, ETH 0.38bp,
LTC 0.51bp, XRP 0.70bp, SUI 0.84bp, SOL 0.88bp. Top-20 notional BTC $8.6M, ETH $13.9M,
SOL $7.6M, XRP $2.9M, DOGE $310k, HYPE $191k, LTC $106k, SUI $72k.

POOLED decile-conditional mean forward MID return, best cell per feature (bps):
  feature   horizon   D10-D1   directional mean   NW t   boot95        net after 9bp
  imb1        5s       2.13        1.07           5.73   [0.73,1.45]      -7.93
  imb1       30s       3.20        1.60           3.01   [0.59,2.84]      -7.40
  imb5        5s       1.90        0.95           5.45   [0.64,1.32]      -8.05
  imb5       30s       3.86        1.93           3.95   [1.11,3.18]      -7.07
  imb20      60s       2.03        1.02           1.20   [-0.28,1.95]     -7.98
  micro_bp   60s       2.31        1.16           0.77   [-0.82,4.11]     -7.84
VERDICT: the signal is REAL and statistically significant (imb5@30s: 1.93bp, NWt=3.95,
bootstrap 95% CI [1.11, 3.18] excludes zero) and it is 4.7x TOO SMALL. Best case 1.93bp
vs a 9.0bp bar => -7.07bp per round trip. Note the spread is NOT the problem (0.1-0.9bp);
the FEE is. This does not become tradeable with more data — more data would only pin the
effect down more precisely at ~2bp. NO EDGE, and decisively so.

## RECOVERED RESULT 2 — scalp-funding-clock (analysis the original agent never ran)
Command: `.venv/bin/python research/edge-hunt-2026-09-19/analyze.py 5m`
Sample: 40 coins x 418 funding hours = 16,656 coin-hour observations, +-60min around each
hourly funding stamp at 5m resolution.

A. Equal-weight portfolio return by minute-of-hour bucket (n=418 hours):
   every bucket |mean| <= 1.36bp, every |t| <= 1.53, cumulative drift over the whole
   +-60min window = +10.5bp of which none is concentrated at settlement.
   Largest single bucket = +1.357bp [-45,-40) t=1.52. Bar is 9bp. DEAD.

B. Cross-sectional long-low-funding / short-high-funding spread, and THE ARTIFACT:
   sorting on f(h) -- the funding rate stamped AT hour h -- shows a strong pre-settlement
   effect: [-60,-55) -3.54bp t=-3.93, [-45,-40) -3.51bp t=-3.68, cumulative -24.6bp over
   the hour BEFORE settlement.
   THIS IS LOOK-AHEAD BIAS. f(h) is computed from the premium observed DURING [h-60, h);
   you cannot know it while trading that hour. Re-sorting on f(h-1), which IS known at
   decision time (the `lagged-f` column), the effect vanishes entirely: no bucket exceeds
   |1.94|bp, cumulative +0.7bp at settlement, and the signs alternate randomly.
   VERDICT: NO EDGE. The apparent squeeze effect is the funding rate being a summary of
   the same hour's returns. Self-refuting; good that the script computed the lagged control.

---
## RECOVERED RESULT 3 — fee-tier-reachability (no agent ever ran this; it is decisive)
Command: POST /info {"type":"userFees","user":0xE503...4A1a}. This returns OUR account's
actual rates AND the full live tier table — no docs guesswork needed.

OUR RATES TODAY:
  perp taker (cross) 0.00045 = 4.5bp     perp maker (add) 0.00015 = 1.5bp
  SPOT taker         0.00070 = 7.0bp     SPOT maker       0.00040 = 4.0bp
  active referral discount 4%  -> effective perp taker 4.32bp, spot taker 6.72bp
  active staking discount 0%

>>> IMPORTANT CORRECTION TO basis-spot-perp.md: it assumed 4.5bp on the SPOT leg.
    Spot taker is 7.0bp. A cash-and-carry round trip is
    7.0 + 7.0 (spot in/out) + 4.5 + 4.5 (perp in/out) = 23.0bp, NOT 18bp.

OUR 14-DAY VOLUME (dailyUserVlm, 15 rows returned, 2026-09-05..09-19):
  userCross per day: 162.17 413.54 214.96 399.32 1417.89 40.59 0 29.14 46.58 66.37
                     22.59 72.43 0 0 370.47   => SUM = $3,256.05
  userAdd per day:   0.0 on EVERY SINGLE DAY. We have never posted maker volume.

VIP TIER LADDER (14-day notional cutoff -> maker rate):
  (base)        $0          maker 0.00015  (1.5bp FEE)
  tier1         $5,000,000  maker 0.00012
  tier2        $25,000,000  maker 0.00008
  tier3       $100,000,000  maker 0.00004
  tier4       $500,000,000  maker 0.0      <- first tier where maker is even FREE
  tier5     $2,000,000,000  maker 0.0
  tier6     $7,000,000,000  maker 0.0
=> NO VIP TIER AT ANY VOLUME EVER PAYS A REBATE. The best VIP outcome is maker = zero.

ACTUAL REBATES come only from the separate `mm` (market-maker) program, gated on
makerFractionCutoff = YOUR SHARE OF EXCHANGE MAKER VOLUME:
  0.005 (0.5% of exchange maker volume) -> add = -0.00001  (rebate 0.1bp)
  0.015 (1.5%)                          -> add = -0.00002  (rebate 0.2bp)
  0.030 (3.0%)                          -> add = -0.00003  (rebate 0.3bp)
Exchange volume from the same payload: $6-10.7B/DAY (e.g. 2026-09-18 $10.09B).
14-day exchange volume ~ $89B. 0.5% of that scale of maker flow is on the order of
$200M+ of our own maker fills in 14 days.

THE ARITHMETIC, stated plainly:
  Our 14d volume                    $3,256
  First VIP tier                    $5,000,000       = 1,536x our current volume
    implied turnover at $641 equity: $357k/day = 557x the account PER DAY
    implied turnover at $10,000:     $357k/day = 35.7x the account PER DAY
  First tier where maker is FREE    $500,000,000     = 153,000x our current volume
    at $10,000 equity: $35.7M/day = 3,571x the account PER DAY
  First tier that pays a REBATE     ~0.5% of all HL maker flow, and it pays 0.1bp.
VERDICT: BLOCKED_BY_CONSTRAINT, confidence HIGH, and permanently.
Maker-rebate edge is NOT reachable at $641 and NOT reachable at $10,000. It is not
reachable at $1,000,000. This closes the entire "be a market maker" strategy class,
which is where every profitable HL account we have examined makes its money.
Corollary: the 9bp taker round trip is a HARD FLOOR for us. It does not improve with
size, effort, or time. Any edge must clear 9bp gross.

FOOTNOTE (small, real, cheap): stakingDiscountTiers. Staking HYPE worth 0.0001 bps of
max supply gives a 5% fee discount; 0.001 bps gives 10%. Worth pricing separately, but
5% off 4.5bp is 0.22bp and cannot rescue any hypothesis here.

---
## SKEPTIC PASS on the only live claim: HYPE spot-perp funding carry
(No skeptic agent ever ran. I am running the three lenses myself.)

### Independent re-pull of the load-bearing number (/tmp/vh2.py, paginated fundingHistory)
HYPE, 13,080 hourly funding prints, 2025-03-23 -> 2026-09-19 (18 months):
  mean 0.1556 bp/h | APR 13.63% | 92.2% of hours positive
  monthly sums (bp): 2025-03 69.1, -04 95.5, -05 279.2, -06 162.9, -07 227.3, -08 119.4,
    -09 141.9, -10 86.9, -11 100.9, -12 102.4, 2026-01 99.5, -02 53.9, -03 58.3,
    -04 41.8, -05 63.1, -06 114.6, -07 79.8, -08 99.8, -09 39.3 (partial)
  NEGATIVE MONTHS: NONE (0 of 19). Worst full month +41.8bp (2026-04).
  18 NON-OVERLAPPING 30-day windows: min +28.9bp, median +97.4, max +269.9. 18/18 > cost.
=> The original agent's Step-7 claim REPRODUCES (it said 0.1545 bp/h / 13.54% APR; I get
   0.1556 / 13.63%). This number is real and is not an artifact of overlapping windows.

### Lens 1 — costs. The agent UNDERCOUNTED. Corrected, it still clears.
Agent assumed 18bp all-in. True (from userFees): spot taker 7bp x2 + perp taker 4.5bp x2
= 23bp, plus live spreads (spot 0.91bp + perp 0.11bp, measured below) = ~24bp all-in.
BUT this is a BUY-AND-HOLD carry: the 24bp is paid ONCE, not monthly. Annual accrual
1363bp vs 24bp one-time entry/exit. Even the WORST 30-day window (+28.9bp) beats it.
Basis MTM is noise not drift: HYPE |basis| p90 = 7.2bp and stationary; mean contribution
+0.1bp per 30d. Cost attack FAILS to kill it.

### Lens 2 — executability and capacity (live, /tmp/vh3.py, 6 snapshot rounds each)
HYPE spot pair = @107 (tokens HYPE/USDC, szDecimals 2). HYPE perp maxLeverage 10.
  HYPE SPOT @107: mid 93.8137  spread 0.91bp  bid$ within 25bp $246,975  ask$ $161,209
  HYPE PERP     : mid 93.8830  spread 0.11bp  bid$ within 25bp  $54,401  ask$  $83,837
  live basis (perp - spot) = +7.38 bp
CAPACITY = min side within 25bp of mid = ~$54,000. Two orders of magnitude above anything
this account can deploy. Capacity attack FAILS. (Note: this is the rare hypothesis that
works BETTER with size — which is precisely why it does not solve THIS account's problem.)

### Lens 3 — CAPITAL EFFICIENCY. This is what actually bites.
Measured account state (2026-09-19):
  perp clearinghouseState: accountValue $207.43, withdrawable $0.00  <- fully committed as
      margin to the existing copy-trade positions
  spotClearinghouseState : USDC $639.00 and nothing else
  (GROUND_TRUTH says total ~$641; measured total is ~$846. Flagging, not silently resolving.)
Deployable free capital = the $639 spot USDC.

Spot HYPE is NOT perp collateral on HL (only USDC is). So a delta-neutral position needs
capital = N (spot leg, fully funded) + M (USDC margin for the short perp leg).
HYPE maxLeverage 10 => initial margin 10%, maintenance 5%.
Liquidation distance for a short at leverage L: x = (1/L - 0.05)/1.05
  L=10 -> cap 1.1N  -> N=$581, liq at +4.8%   (dies within days; HYPE moves 5% routinely)
  L=5  -> cap 1.2N  -> N=$533, liq at +14.3%
  L=3  -> cap 1.33N -> N=$479, liq at +27.0%
  L=2  -> cap 1.5N  -> N=$426, liq at +42.9%  <- the only prudent one
At L=2, N = $639/1.5 = $426 of notional per leg.
  gross annual carry 13.63% x $426       = $58.06
  one-time entry+exit 24bp x $426        = -$1.02
  ~4 margin top-ups/yr (sell+rebuy spot) = -$0.30
  NET YEAR ONE                           ~ $57
  = 8.9% APR on the $639 deployed, or 6.7% APR on ~$846 total equity.

### The honest verdict
This SURVIVES on the numbers: effect 1363bp/yr vs 24bp cost, n=13,080 prints, 18/18
non-overlapping windows positive, capacity $54k, all measured. It is the only thing in
this entire hunt with a positive measured expectation.
But three caveats that must be in the report:
 1. It is a RISK PREMIUM, not an inefficiency. HYPE funding is positive because HYPE is a
    persistently crowded long; you are paid to be the other side of leveraged HYPE longs.
    The 19/19 win record IS the pennies; the liquidation tail IS the steamroller. A HYPE
    regime flip turns funding negative and it stops working — that is the falsifier.
 2. DOLLARS: $57/year. The standing mission is $200 -> $1,000 by 2026-08-31; from here that
    needs +$359 in 11.4 months. This contributes ~$54, i.e. 15% of the goal. It does not
    get us there and nothing about it can be sized up to get us there on this capital.
 3. OPERATIONAL CONFLICT: converting $426 of spot USDC into spot HYPE removes it from the
    unified USDC collateral pool that the existing copy-trade bot draws on (perp
    withdrawable is already $0.00). Deploying this means shrinking or stopping copy
    trading. Given copy trading measures at zero edge that is defensible, but it is a
    decision, not free money.
