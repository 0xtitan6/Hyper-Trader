# Mechanics probe — HL rulebook asymmetries at small size

Agent: Fable mechanics scout. Started 2026-09-20.
Method: read the rules (docs + API), ask "what does this rule accidentally permit
for a $565 account?" Everything labeled MEASURED / SOURCED+URL / UNVERIFIED.

Areas: HIP-3 builder dexes (collateral, deployer fees, oracles), HIP-4 outcome
mechanics + outcomeTemplates + short TWAP windows, funding (hourly, clamps,
premium/interest, per-dex), liquidations (partial/full, backstop, HLP), spot/perp
collateral + transfer timing, order-type asymmetries (ALO/IOC/TWAP/scale).

Excluded (CONSTRAINTS.md): complement arb, dutch books, ladder monotonicity,
barrier/digital EV, funding-settlement timing z=0.59, HIP-3 thin-book scalping,
maker rebates, LP rewards, copy-trading, HYPE carry, inception mispricing.

## Findings log (append-only)

### 1. HIP-3 builder dexes — oracle divergence (MEASURED, DEAD)
11 dexes live (xyz, flx, vntl, hyna, km, abcd, cash, para, mkts, io). 30 underlyings
listed on >1 dex. The DEAD dexes (hyna, cash) carry wildly stale oracles vs base
(hyna:ZEC oracle 813 vs base 1449; cash:BTC 70000 vs 80538; hyna:BTC 76888) — a 4-40%
"gap". But every one has openInterest=0 and no order book. You cannot arb a mark that
no one will trade against. The ACTIVE HIP-3 dexes (para/mkts/io = tokenized stocks &
private-co perps: ANTH, OAI, NVDA, IREN, US500...) hold oracles TIGHT: |mark-oracle|
< 0.6% on every live market. No cross-venue arb because the liquid HIP-3 assets are
NOT listed on the base dex (no hedge leg). VERDICT: oracle-gap arb dead. Capacity $0.

### 2. Funding baseline asymmetry (MEASURED / SOURCED)
Base dex: essentially EVERY normal coin shows funding = exactly 0.0000125/hr
(=1.25bp/hr = 10.95% APR). This is HL's interest-rate floor (0.01%/8h) that longs pay
shorts whenever premium≈0 — a structural long-pays-short bias. This is the known
"HYPE carry" generalized; it is a RATE (scales with capital) and mean-reverts to ~0
net on coins without persistent one-sided demand, so only HYPE (persistent) carried,
already measured capacity-capped ($613/mo, needs $10k). The mkts dex uses a DIFFERENT
deployer-set interest rate (0.0000057078/hr) — proof deployers can set funding params.
But no same-asset pair is liquid on both a low-rate and high-rate dex, so the
differential is not harvestable delta-neutral. VERDICT: no new carry. Capacity $0 new.

### 3. HIP-4 outcomeTemplates registry (MEASURED)
18 templates (binaryPrice, priceTouch, scalarPrice, aiModelHeadToHead, policyRate*,
sports*, companyIpoConfirmed). 223 live outcomes, 21 questions. feeScale=1.0 uniform,
deployerFeeScale=1.0 or null — NO fee/rebate asymmetry hidden anywhere. binaryPrice
settles on an N-second TWAP of the HL perp price (windows seen: 60/90/300s; priceTouch
uses seconds:1). Fills measured 0-fee (constraints). No fee lever.

### 4. HIP-4 binary settlement-convergence (MEASURED — TIGHT for a taker)
Hypothesis: near expiry, if the perp is decisively past threshold, the winning leg must
settle to 1.0; buy it below 1.0 = riskless convergence. This is the "timing beats size"
shape. Tested on the BTC 16:00 batch (2.6h out, thresholds +0.6% to +2.2% OTM):
 - Book depth is DEEP: $44k-$144k per leg. Capacity is NOT the binding constraint here.
 - But the MM caps the near-certain leg's ASK at exactly 1.00 and floors the dead leg's
   BID at 0.00. So a TAKER can never buy a winning leg below fair value:
     id=4286 P(NO)=0.9955, NO ask=1.00 -> buy-NO edge -0.004
     id=4285 P(NO)=0.9586, NO ask=1.00 -> -0.041
     id=4436 P(NO)=0.9811, NO ask=1.00 -> -0.019
 - The wide spread (dead-leg ask floored ~0.07-0.18 vs fair ~0.005; certain-leg bid
   ~0.84-0.93) is a pure adverse-selection premium, harvestable only by being the MAKER
   — which is exactly the play that ran live 09-19 and lost $47 to adverse selection.
VERDICT: convergence closed for takers; making it is the already-dead LP play.

### 5. Order types / liquidations / spot-perp (SOURCED, not separately exploitable at size)
ALO = post-only (no rebate reachable, per constraints). Liquidations route to HLP /
backstop — being the liquidator needs infra+capital, not a $565 edge. Spot<->perp
transfers are instant unified collateral (no float to exploit). No asymmetry found.

### 6. Live decisive-binary scan (MEASURED — confirms tight)
Scanned all 73 live binaryPrice markets for cases where the perp is already decisively
past threshold (P(win)>0.97) with time left. Found 5 (BTC, HYPE, ZEC). In EVERY case
the winning leg's ask = exactly 1.00 (edge -0.002 to -0.021). The MM's 1.00 ask-cap on
the certain leg is universal and holds even for near-deterministic outcomes 30h out.
There is no taker convergence edge live anywhere.

## VERDICT
Mechanics are TIGHT. Nothing here beats the 9bp floor / $10-min / adverse-selection
walls at $565. Ranked by "least dead":

BEST RESIDUAL QUIRK: HIP-4 binary MM quote structure. Books are DEEP ($44k-$144k/leg,
so unlike the rest of the account's history CAPACITY is not the wall) and the MM runs a
mechanical quote: certain-leg ask hard-capped at 1.00, dead-leg bid floored at 0.00,
dead-leg ask floored ~0.07-0.18 (vs fair ~0.005). A TAKER cannot touch it (can only buy,
never below fair). The only harvest is MAKING the far-OTM/ITM legs — bidding a certain
leg at ~0.985 to buy from forced/panic sellers, or offering a dead leg at ~0.02. This
differs from the 09-19 LP loss ONLY in that you quote DEEP legs (low adverse selection
by construction) rather than near-money legs (max adverse selection). UNVERIFIED whether
deep-leg making actually has positive net after adverse selection — that is the open
question, not a demonstrated edge.

Capacity if it worked: book depth says $10k+ per settlement is absorbable; but fill rate
(how often a panic seller crosses your 0.985 bid) is the true cap and is unmeasured —
likely a few $10-100 fills/day => $50-300/day order of magnitude, NOT proven.

FALSIFICATION (runnable in <1 day, public API): stream l2Book + trades on the certain
leg of the next ~20 binaries in their final 2h. Log every fill that crosses a resting
bid at >=0.97. If those fills are systematically followed by the leg settling to 1.0
(seller was not informed), deep-leg making is positive. If the crossing sells cluster
right before the perp breaches threshold (seller WAS informed), it is the same adverse
selection that lost $47 — dead. Null result kills it.

Everything else (oracle arb, funding carry, fee/rebate lever, taker convergence,
liquidation, spot-perp float) is measured/reasoned DEAD at this size. A clean "the
rulebook is tight" answer.
