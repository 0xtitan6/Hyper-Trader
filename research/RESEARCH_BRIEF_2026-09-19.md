# Research brief — finding a real edge for a small Hyperliquid account

**Date:** 2026-09-19 · **Account:** `0xE503186067b1B0Fb973c063054B14c4625434A1a` · **Equity:** ~$641
**Goal:** grow $200 → $1,000. Target date 2026-08-31 has passed; account is at $641.

This brief is for an external research agent. Everything below the line marked MEASURED was
computed from live Hyperliquid/Monarch API data on 2026-09-19, not assumed. Please
challenge it — several of these numbers killed strategies we had already built.

---

## 1. What we run today, and why it does not work

A copy-trading ("mirror") engine that follows selected Hyperliquid traders' fills and
reproduces them at fixed clip sizes.

**MEASURED — the engine has no detectable edge:**

| metric | value |
|---|---|
| bot-only closing trades | 964 (4.5 months) |
| mean PnL/trade | **+$0.0416** |
| std dev | $5.23 (126× the mean) |
| t-statistic | **+0.25** (need 1.96) |
| 95% CI on total | **−$278 … +$358** |
| trades needed to prove the edge at 95% | **60,720 (~23.6 years)** |

Lifetime realised across 2,699 fills / $107,296 notional: **−$225 gross, −$263 after $37.66
of fees**. Fees are only 0.035% of notional — i.e. **the strategy loses before fees**, so
cost reduction cannot save it. Two June prediction-market fills account for −$370 of that;
excluding them, perps-only is +$117.64, of which **+$96 was placed manually by an operator**,
leaving **+$21.56 attributable to the bot in four months**.

**Conclusion we have drawn (please challenge):** scaling capital into this multiplies a coin
flip. At $10k the same trade series gives a point estimate of +$627 over 4.5 months with a
95% CI of **−$4,342 … +$5,597**.

## 2. Structural constraints — these killed whole strategy classes

**MEASURED. Any proposal that violates these is dead on arrival.**

1. **No Hyperliquid fee tier pays a maker rebate at any volume.** Best VIP outcome is
   maker = 0. Actual rebates come only from a separate market-maker programme gated at
   **~0.5% of total exchange maker flow** (14-day exchange volume ≈ $89B), paying 0.1bp.
   Unreachable at $641, at $10k, or at $1M. **The 9bp taker round-trip is a permanent floor.**
   This closes rebate-based market-making — the strategy every profitable HL account we
   examined relies on.
2. **Minimum order value is $10**, which quantises sizing badly on a $641 account.
3. **HIP-3 builder dexes (`xyz:`, `para:`, `io:`) hold separate collateral** — margin cannot
   be netted across them, and caps must be per-dex. Most `xyz:` perps are unexecutable at
   our clip size.
4. **Spot is not perp collateral for hedging pairs.** A delta-neutral spot/perp position
   costs ~1.5× notional in capital at prudent leverage.
5. **Leader pool is exhausted.** Two full sweeps of the Liquidiction top-50 (2026-08-16 and
   2026-09-19) rejected 48/50 and 27/27 non-pinned candidates on equity, turnover or
   maker-share grounds. We also screened **9,474 HL vaults** → 3,102 open → 66 with
   TVL ≥ $100k and age ≥ 180d → 4 non-maker → **2 survivors**, both ~66+ fills/day where
   fee drag at our clip size exceeds plausible edge.

## 3. Things we measured that ARE real but do not solve it

- **HYPE spot-perp funding carry:** +0.1556 bp/hour = **13.63% APR**, n=13,080 hourly prints
  over 18 months, 92.2% of hours positive, 18/18 non-overlapping 30-day windows clear the
  ~24bp all-in cost. Capacity ~$54k. **But** constraint 4 caps us at ~$426 of notional →
  **~$57/year**. Real edge, wrong size.
- **Outcome (HIP-4) LP rewards — currently live, see §4.**

Measured negatives, so they are not re-researched: order-book imbalance, funding-settlement
timing (z=0.59), cross-coin lead-lag, HIP-3 thin-book scalping — all NO_EDGE. New-listing
patterns and liquidation-cascade prediction were underpowered/untested.

## 4. What we are running now: Outcome LP rewards

[outcome.xyz](https://outcome.xyz) / [Monarch](https://monarch.fast) pay liquidity rewards on
HIP-4 prediction markets. **$200k/month budget; $153,679 USDC distributed to date.**

Scoring (from `docs.outcome.xyz/outcome-liquidity-rewards`):
```
side_score           = Σ( order_notional × distance_multiplier × seconds_resting )
distance_multiplier  = 5.00 × max(0, 1 − normalised_distance)²    # 5× at mid → 0× at band edge
two_sided_multiplier = 1 + 2 × balance_ratio                       # 1× → 3×
your_reward          = pool × your_score ÷ total_score
pools                = 40% quoting / 50% maker-fill / 10% taker-fill
```
Multipliers stack: volatility ≤5×, live-event 3×, combined cap 8×. Minimum to score:
**$50 of in-band bid+ask notional** — a threshold, not a volume tier, which is why it is
reachable at our size.

**Why it is attractive:** it pays for *placement and balance*, not size. It is an external
subsidy rather than a fee tier, so constraint 1 does not apply. Spread P&L can be mildly
negative and we still net positive.

**MEASURED economics:** competing in-band depth averages **$4,169/leg** (range $1.9k–$9.2k).
Quote pool is ~$33/outcome per ~40h window. Greedy allocation of $350 across the best
surfaces yields **~$5.30/window ≈ $3.14/day ≈ $94/month**. Concentration beats spreading
because reward-per-dollar ≈ `pool ÷ depth` varies ~3× across markets.

**Implementation notes:** outcome legs are spot-like (no shorting), so a maker can only BID —
a YES+NO pair is what makes us two-sided on the scored surface. Orders must carry builder
code `0xab5dbc057628bc18523c4cdfc0e1e2ebdbecb704` with `fee=0`; **no `approveBuilderFee` is
needed at fee 0** (verified: identical post-only orders accepted with and without it).
Rewards are **claim-based**, daily UTC epochs, merkle root ~00:15 UTC next day, route
expires ~7 days — unclaimed rewards are lost.

**Unproven:** attribution. Order acceptance is confirmed; that Monarch credits our address is
not. First check 2026-09-20 00:22 UTC.

**Risk:** one-sided fills. Both legs filling is hedged (YES+NO settles to $1.00 for ~$0.996);
a single fill on the losing side loses the stake, and adverse selection means the filling side
tends to be the wrong one.

---

## 5. What we want researched

Ranked by how much it would change our decisions.

1. **Is there a venue/instrument where a $600–$10k account has structural edge?** Our
   conclusion is that Hyperliquid at this size offers one modest risk premium (funding carry)
   and no inefficiencies. Is that correct, or are we looking in the wrong place? Consider
   other perp DEXs, other prediction markets (Polymarket, Kalshi), and incentive/points
   programmes analogous to §4.
2. **Are there other live LP-reward or incentive programmes with the same shape as §4** —
   i.e. paying for presence/placement rather than requiring predictive skill, with a
   *threshold* rather than a volume-tier entry? This is the only mechanism we have found that
   is genuinely size-agnostic. Include expected $/day for ~$500 deployed and the claim mechanics.
3. **Optimal quoting policy under the §4 scoring formula.** Given `distance_multiplier` is
   quadratic in distance-from-mid and `two_sided_multiplier` rewards balance, what is the
   optimal placement and rebalancing cadence to maximise score per dollar-hour while
   minimising one-sided fill risk? Is there a provably better policy than "sit at mid on both
   legs"? How should quotes be skewed as the event approaches settlement (band widens
   cubically: `1 + (max_mult − 1) × progress³`)?
4. **Adverse selection in prediction-market making.** Quantify expected loss from one-sided
   fills on sports binaries as a function of time-to-event and quote distance. Is the reward
   subsidy large enough to dominate it at our size? This is the number that decides whether
   §4 scales or is a trap.
5. **Does the copy-trading conclusion in §1 survive scrutiny?** Specifically: is there a
   *subset* decomposition (by surface, coin, hour, holding period, or leader) where a
   profitable core is being dragged down by an identifiable removable subset? We intended to
   test this and the agent failed before running. If base-dex perps are net positive while
   `xyz:` bleeds, the fix is to stop trading one surface — the cheapest possible win, and it
   requires no new strategy.

## 6. Constraints on any recommendation

- Capital ~$641 now; $10k is available **if** an edge is demonstrated first.
- Non-custodial: an agent/API wallet on a server can place and cancel orders but cannot
  withdraw, approve builders, or move funds. Anything requiring a master-key signature needs
  a human and cannot be automated.
- We prefer a **measured negative** over an unverified positive. A clean "no edge here, here
  is the number" is a useful deliverable; a plausible-sounding strategy we then fund is not.
- State every claim with its sample size, and compare every effect against the real cost
  floor (9bp taker round-trip; ~0.75bp for HIP-4 maker round-trips, which is 12× lower and
  the reason §4 is viable at all).
