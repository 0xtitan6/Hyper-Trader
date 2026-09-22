# outcome-arb — HIP-4 prediction market internal arbitrage

**VERDICT: NO_EDGE** (measured 2026-09-19 13:45 UTC, n=13 live 3-way markets)

Tested two related hypotheses on Outcome/HIP-4 sports books, prompted by a
Polymarket favourite-longshot finding (justinli500 on X: political exit markets
price ~5x above a hazard model, persistently).

## 1. Favourite-longshot bias — NOT PRESENT

In a 3-way market the YES legs must sum to 1.00; excess is overround, and the
bias shows up as that excess sitting on the longshot.

    mean overround                    +0.56%   (entirely Q305, see below)
    mean price inflation, FAVOURITE   +0.501 pts
    mean price inflation, LONGSHOT    -0.007 pts

The inflation is on the FAVOURITE — the opposite sign to the Polymarket result.
Excluding Q305 (+7.01%, a market already effectively settled: Aston Villa 0.991,
Draw 0.004) every book sits within +/-1.3% of fair.

Interpretation: football odds are continuously arbitraged against global
bookmakers, so there is no narrative premium to harvest. Political exit markets
have no such anchor, which is plausibly why the premium survives THERE and not
here. Do not assume a prediction-market bias transfers across market types.

## 2. Model-free arbitrage (buy all legs below $1.00) — NOT EXECUTABLE

Mids tempt: several markets show sum-of-mids BELOW 1.00 (Q303 0.9937, Q301
0.9956, Q311 0.9975). That is an illusion — you cross the spread, so the real
test is sum-of-ASKS.

    0 of 13 markets buyable below $1.00 at the ask
    best case Q309 at 1.0012 (-0.12%), worst Q305 at 1.1571

Every book sums above 1.00 once you pay the offer. The apparent edge is exactly
the spread.

## The useful corollary

We cannot TAKE this arb, but we can MAKE it, and we already do. The farm rests
bids on both legs; when our bids sum below 1.00 and both fill, we collect exactly
$1.00 at settlement. Measured live on Q311 Draw: bids 0.246 + 0.750 = 0.996, so a
both-sides fill is +0.4% risk-free ON TOP of the LP reward.

That reframes fills: a hedged (two-sided) fill is not a cost of farming, it is a
small positive. Only ONE-SIDED fills are the risk — which is what
[[JEV_TOXICITY_GATE]] is meant to predict.
