# Hard constraints — read before proposing anything

Account: 0xE503186067b1B0Fb973c063054B14c4625434A1a, ~$565 equity, $10k available
if and only if an edge is demonstrated first. Venue access: Hyperliquid (perps,
HIP-3 builder dexes, HIP-4 prediction markets), Polymarket read-only.

## We are not short of ideas. We are short of CAPACITY.

Two rounds of research and one live deployment found many real, statistically
significant effects. Every one of them died on the same thing: no room to make
money at our size. Your job is not to find an interesting effect. It is to find
one where a $600-$10,000 account can actually collect.

Proposals that do not state capacity in dollars will be discarded.

## Measured dead — do not re-propose

| candidate | why it died |
|---|---|
| Copy-trading HL leaders | n=964 closes, t=+0.25. Coin flip. Needs 60,720 trades to prove |
| HL LP rewards (HIP-4) | ran it live 2026-09-19: -$47 adverse selection, $0 rewards paid |
| Maker rebates on HL | NO tier pays a rebate at any volume; needs ~0.5% of exchange maker flow |
| HYPE funding carry | REAL (13.63% APR, n=13,080) but capacity-capped ~$613/mo, and needs $10k |
| Order-book imbalance | measured NO_EDGE |
| Funding-settlement timing | z=0.59, NO_EDGE |
| Cross-coin lead-lag | NO_EDGE |
| HIP-3 thin-book scalping | NO_EDGE |
| Favourite-longshot on HIP-4 | slope 1.034, CI 0.829-1.239, p=0.74. Clean negative |
| YES+NO complement arb | closed, min sum 1.00001 across 213 outcomes |
| Inception mispricing | REAL (+821bp, p=9.5e-49) but $6.20/day at 100% queue share |
| Early entry at programme launch | $1.24 total pool in a market's first hour |
| Barrier/digital structure | relative gap real, absolute EV negative at realised vol |

## Cost floors any proposal must beat

- Hyperliquid perp taker round trip: **9 bp**. Permanent — no rebate tier is reachable.
- HIP-4 outcome fills: measured **0 fee** on buys and on settlement (n=7).
- Polymarket: a day pays only if earnings >= $1; sub-$1 days pay nothing, no rollover.
- Min order value on HL: $10.

## The one shape that has ever looked right for small size

Threshold-gated subsidies — paid for *presence* rather than for *predicting*, with a
fixed minimum rather than a share-of-volume gate. That is why Outcome LP looked
promising. It still failed, on attribution and adverse selection. But the SHAPE is
the only one where small capital is not definitionally diluted, so prioritise:

- incentive programmes with a **threshold** entry, not share-of-pool or share-of-volume
- anything where **placement or timing beats size**
- anything paid in a currency other than trading profit (points, tokens, rebates)

## What makes a proposal credible here

1. **Capacity in dollars at $600 and at $10,000.** The single most important number.
2. **The cost term**, not just the reward term. Our $47 loss was a reward we measured
   precisely and a cost we never priced.
3. **Whether the evidence survives the source being wrong.** Twitter/Reddit claims are
   usually promotional or survivorship-biased. Hyperliquid's own leaderboard excludes
   accounts under $100k, so small-account failures are structurally invisible.
4. **A falsification test** we could run in under a day with public APIs.

## Source-quality rules

- Label everything: MEASURED / SOURCED (doc + URL) / UNVERIFIED (secondary) / PROMOTIONAL.
- Anyone selling a course, VPS, bot, or "DM me" is PROMOTIONAL — report it as such.
- A self-reported P&L screenshot is not evidence.
- Academic results are usually measured on equities with institutional costs; state
  whether the effect survives a 9bp retail floor and a $600 account.

## Write as you go

Write findings to `research/edge-swarm-2026-09-20/<your-slug>.md` CONTINUOUSLY.
If the run is interrupted that file is all that survives.
