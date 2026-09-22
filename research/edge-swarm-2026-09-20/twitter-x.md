# Source: X / Twitter — threshold-gated incentive programmes & current crypto edges

Run started 2026-09-20. Account ~$565, $10k contingent. Cost floor 9bp HL taker RT, $10 min order.

Status: IN PROGRESS — notes appended as found.

## Method note (important, affects confidence)

Direct X access is unavailable from this box:
- `xcancel.com` (nitter mirror) -> HTTP 451 Unavailable For Legal Reasons
- `x.com/<user>/status/<id>` via WebFetch -> HTTP 402 Payment Required (X's paywalled API gate)

The only working channel is WebSearch, which **does** index x.com and frequently returns the
full tweet text inside the result title. So: primary-source tweets from official accounts
(e.g. @BinanceWallet announcements) are recoverable; free-form practitioner threads and
reply-sections are NOT. That asymmetry matters — it means I can see the PROMOTIONAL and
OFFICIAL layer of X clearly and the "this stopped working" layer only where it has been
re-reported elsewhere. Treat the absence of loss-reports below as a sampling artefact, not
as evidence that losses are rare.

## Candidate 1 — Binance Alpha Points airdrops (THE one true threshold-gated shape found)

This is the only thing I found on X with the exact shape CONSTRAINTS.md asks for:
**a fixed minimum threshold, a flat token payout per wallet, no share-of-pool dilution.**
Primary source is Binance's own X account and Binance's own FAQ, not an influencer.

Primary sources (SOURCED):
- @BinanceWallet, 2026-08-04: "Users with at least 243 Binance Alpha Points can claim an
  airdrop of 550 QUID tokens on a first-come, first-served basis. If the reward pool is
  [not fully distributed the threshold drops]"
  https://x.com/BinanceWallet/status/2084550061598331040
- @BinanceWallet, 2026-05-04: "at least 220 Binance Alpha Points can claim an airdrop of
  2,000 BILL tokens" https://x.com/BinanceWallet/status/2051175064855523401
- Binance FAQ (exact rules):
  https://www.binance.com/en/support/faq/detail/12e7f2e555704f9c8e852d1c1afb032a
  Balance points: $100-1k = 1/day, $1k-10k = 2/day, $10k-100k = 3/day, $100k+ = 4/day
  Volume points: $2 = 1 pt, and +1 point per DOUBLING of buy volume. So volume for n
  points = $2^n. Selling does not remove earned volume points.
  Rolling 15-day window, daily snapshot 23:59:59 UTC, each day's points expire after 15d.
- Claim consumes 15 Alpha Points. Threshold decays 5 points every 5 minutes if the pool
  is not exhausted. FCFS.
- Sept 2026 observed thresholds: 235, 246, 250 points (PANews, multiple).

### The arithmetic — this is where it dies at $600

Need ~246 points in a rolling 15 days = 16.4 points/day.

At $600 equity: balance = 1 pt/day. Volume points needed = 15.4/day.
  Volume for 15 pts = $32,768/day; for 16 pts = $65,536/day.
  Blended requirement ~ **$52,000/day of Alpha-token BUY volume.**
  With $600 of capital that is ~87 buy/sell round trips per day.

At $10,000 equity: balance = 3 pts/day. Volume points needed = 13.4/day.
  Blended requirement ~ **$11,500/day of buy volume** (~1.1 round trips/day... no,
  ~19 round trips/day of $600 clips, or a single $11.5k clip).

Note the perverse shape: because points are logarithmic in volume, going from 1 to 3
balance points (i.e. $600 -> $10,000) cuts the required daily turnover by ~4.5x. The
programme is explicitly ANTI-small-account.

### Reward side (capacity)

The payout is flat per wallet and the wallet is KYC-gated to one Binance account, so
capacity is identical at $600 and at $10,000 — it does not scale with capital at all.
Best practitioner figure I could source: one farmer reported 240 points, 5 airdrops in
one month, ~$48 average per airdrop, ~$240 net for the month (Chinese-language
撸毛 write-ups; UNVERIFIED secondary, and probably a 2025 vintage — thresholds have
since risen from ~190 to ~250, which is a 2x volume increase per the doubling rule).

**Capacity ceiling: ~$240/month gross, i.e. ~$8/day, at ANY account size.**

### Cost side (the term that kills it)

Cost is not fees, it is 磨损 ("wear") — spread + price impact on illiquid Alpha tokens,
paid on both the buy and the recycling sell. Community-quoted wear is ~0.02%-0.1% per
round trip on the most liquid Alpha pairs.

  At $600: $52,000/day turnover x 0.02-0.1% = **$10-$52/day of wear** vs $8/day reward.
           Net -$2 to -$44/day. NEGATIVE, and not marginally.
  At $10k:  $11,500/day x 0.02-0.1% = **$2.3-$11.5/day** vs $8/day reward.
           Net +$5.7/day to -$3.5/day. Coin-flip on the wear assumption alone.

### Verdict
Correct SHAPE, wrong SIZE. Threshold-gated and undiluted, but the threshold is itself
denominated in volume with a logarithmic schedule that punishes small balances ~4.5x.
Reward is hard-capped at ~$240/mo. At $600 it is clearly negative. At $10k it is inside
the error bars of a wear estimate I could not measure.

Additional hard blockers:
- Binance.com is not available to US persons. If this account is US-resident this is
  simply unavailable, and I cannot determine residency from here.
- Requires moving capital off Hyperliquid entirely into a KYC'd CEX.
- Explicitly against Binance policy to run multiple accounts, so the flat-per-wallet
  payout cannot be replicated to scale.

### Correction to the wear estimate (found a measured datapoint)

Chinese practitioner write-ups give a measured wear figure: one full buy+sell cycle on a
liquid Alpha pair costs ~$0.50, i.e. **~0.03-0.05% per round trip**, and one source states
$16,384/day of buy volume costs ~$5/day of wear. Those same sources also report point
tallies inconsistent with the FAQ formula ($8,192/day -> 14 volume points, where
log2(8192)=13), which implies a 2x effective-volume multiplier is still live on some
tokens despite the FAQ saying the BSC rules lapsed. If the 2x is real, required actual
volume at $600 falls from ~$52k/day to ~$23k/day and wear to ~$7-11/day.

Either way the conclusion is unchanged: reward is capped ~$8/day, wear is $7-$50/day,
and the sign of the net depends entirely on a wear parameter I cannot measure from here.
Note also that every source claiming this is profitable is a content-farm guide — one is
literally titled 月入3万 ("30k a month") — which is PROMOTIONAL. The skeptical
Chinese-language community reports are the ones saying rewards barely cover wear.

---

## Candidate 2 — Hyperliquid HYPE staking fee tiers (threshold-gated, and it is real)

SOURCED, primary: https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees
Base perp taker 0.045% (our 9bp round trip). Staking tiers are a pure THRESHOLD on HYPE
staked — no volume gate, no share-of-pool:

  Wood   >10 HYPE      5% off
  Bronze >100 HYPE     10% off
  Silver >1,000 HYPE   15% off
  Gold   >10,000 HYPE  20% off
  Platinum >100k       30% off
  Diamond >500k        40% off

Referral: 4% discount for the referred user, first $25M of volume; referrer earns 10% of
referee fees for their first $1B. (Docs confirm the $25M / $1B limits.)

Capital-efficiency wrinkle worth noting: Pendle enabled **stHYPE YTs to inherit the
Hyperliquid staking tier discount** (27 Aug 2026, via CoinMarketCal/TradingView —
UNVERIFIED, secondary). If true you buy the yield token at a fraction of spot and still
qualify for the tier. That is the correct "placement beats size" shape.

### Why it still dies — and this generalises to the whole fee category

Capacity of ANY fee-side edge = (our traded volume) x (bp saved). Our volume is bounded by
equity x turnover, so:

  At $600, 2x daily turnover = $1,200/day of taker volume.
    A **100% fee waiver** — which does not exist — is worth 9bp x $1,200 = **$1.08/day**.
    The best reachable stack (4% referral + 5% Wood tier ~ 9% off) is worth **$0.10/day**,
    and the Wood tier costs ~$400 of HYPE (70% of the account) converted into directional
    HYPE risk to get it.
  At $10,000, 2x turnover = $20,000/day.
    100% waiver ceiling = **$18/day**. Realistic 10-15% off = **$1.80-$2.70/day**, against
    $4,000-$40,000 of HYPE that must be staked and 7-day-unbonded to qualify.

**This is a hard ceiling on an entire category, not one candidate.** No fee discount,
rebate, cashback or referral scheme on Hyperliquid can pay more than ~$1/day at $600 or
~$18/day at $10k, because the reward is proportional to our own volume and our volume is
proportional to our equity. Any X account claiming otherwise ("30% cashback", "$100
bonus") is an affiliate — and note 30% cashback is arithmetically impossible when the
referrer only receives 10% of fees. That is a lie, not an exaggeration.

### HYPE price correction — the staking ladder is not merely unattractive, it is UNREACHABLE

HYPE is ~$91 (ATH $94.46 set 2026-09-19). So:
  Wood (>10 HYPE, 5% off)    = **$910** — 1.6x our entire account
  Bronze (>100 HYPE, 10%)    = $9,100 — 91% of the $10k tranche
  Silver (>1,000 HYPE, 15%)  = $91,000
The cheapest rung of the fee ladder costs more than the account. Even at $10,000 the only
reachable rung is Wood: $910 (9% of capital) of directional HYPE, 7-day unbonding, to save
5% of 9bp = 0.45bp, worth ~$0.09/day on $20k/day of volume. Dead on arrival.

---

## Candidate 3 — Perp-DEX volume/points farming (Lighter, Aster, edgeX, Backpack, Ondo, Variational)

This is ~80% of what X actually talks about in this space. It is share-of-pool by
construction: "your share of total points usually determines your share of the community
airdrop allocation."

### The measured calibration that kills the category

Lighter's LIT TGE (2025-12-30) distributed **$675M — the 10th-largest airdrop in crypto
history**, 25% of supply. The conversion came out at ~20-28 LIT per point, and the
reporting on it says plainly:

  "for some users with higher trading frequency, this was roughly equivalent to
   the fees they paid, failing to deliver the expected 'big win' return."

Sources: https://coinmarketcap.com/academy/article/lighter-LIT-675m-tenth-largest-crypto-airdrop
         https://www.panewslab.com/en/articles/99875265-3a5a-44be-8d04-90f740146b20
         https://www.coindesk.com/markets/2025/12/31/lighter-trading-platform-sees-usd250-million-withdrawn-24-hours-after-tge

That is the number that matters. The most generous perp-DEX points programme ever run
returned **approximately fees paid** to the people who farmed it hardest. Not a loss, not
a windfall — a wash. And that is the SURVIVOR: $250M was withdrawn within 24 hours of TGE,
LIT is -38% from ATH, ASTER -70% from ATH, EDGE "fell short of expectations post-launch".

Also: Lighter clawed back and reallocated Season 2 points tied to sybil and self-trading.
So the volume must be real volume, i.e. must carry real adverse selection, not just fees.

**Capacity at $600: ~$0/day net (empirically ≈ fees paid, and fees paid at $600 are tiny,
so the gross is tiny too). Capacity at $10,000: ~$0/day net, on a larger gross.**
Share-of-volume is exactly the shape CONSTRAINTS.md says is definitionally diluted, and
the Lighter datapoint is the empirical confirmation at the most favourable venue ever.

---

## Candidate 4 — Hyperliquid "Season 2" HYPE airdrop (the biggest X narrative; adversarial take)

Claim circulating on X and in every guide: 38.888% of HYPE supply is earmarked for
airdrops across seasons, with 238.8M HYPE (23.88%) attributed to "Season 2".
**Hyperliquid has never confirmed a Season 2.** No dates, no criteria, nothing official.
Every one of those numbers traces back to Medium posts and SEO guides. UNVERIFIED.

The arithmetic, taken at face value:
  238.8M HYPE x $91 = **$21.7B**. HL does ~$2.5T/yr of perp volume (Q1 2026 = $633B).
  Over a 2-year accrual window that is $21.7B / $5T = **43 bp of airdrop per dollar of
  volume traded**, against a 3bp maker-maker / 9bp taker round-trip cost.

**That result is too good, and its being too good is the finding.** If the allocation were
actually volume-proportional, this would be a 5-14x return on fees, risk-free, visible to
everyone, and competed away instantly. It has not been competed away. Therefore the
allocation is almost certainly NOT volume-proportional — which is consistent with the one
hard fact about Season 1: the Hyper Foundation **never published a points-to-tokens
formula**, deliberately, to stop it being gamed, and weighted maker liquidity, open
interest, duration and HLP deposits rather than raw volume.

Do not treat the 43bp as an EV. Treat it as proof the model is wrong.

**The only actionable conclusion, and it is a do-nothing:** our bot already generates HL
volume as a by-product of trading. If Season 2 ever happens we accrue whatever we accrue
at **zero marginal cost**. There is no version of this that justifies trading MORE, and it
can never be the "demonstrated edge" that unlocks the $10k, because it is unfalsifiable
until a TGE that may not exist.
Capacity at $600: unknowable, plausibly $0. At $10,000: unknowable, plausibly $0.

---

## Candidate 5 — Exchange sign-up / deposit bonuses (the ONE place $600 is not penalised)

Being adversarial with myself here, because this is the only thing I found where a small
account is structurally EQUAL to a large one: flat payout, gated on a minimum deposit.
Examples circulating Sept 2026: X Money $300 direct-deposit bonus + 6% APY, Crypto.com
referral "up to $2,000", various $15-$100 welcome deposits.

Why I am still reporting it as not-an-edge:
- **One-off and non-recurring.** Capacity is not $/day, it is $N once, bounded by the
  number of distinct venues you are willing to KYC with. There is no rate.
- It does not scale at all: identical at $600 and $10,000. So it cannot demonstrate
  anything that would justify deploying the $10k.
- Most are fiat/US-banking products (direct deposit of a paycheck), not crypto trading.
- It is a customer-acquisition rebate, not an edge. It tells you nothing about markets.

Capacity at $600: one-time, order $15-$300 per venue. At $10,000: identical. Rate: $0/day.

---

## Candidate 6 — Hyperliquid builder codes

SOURCED: https://hyperliquid.gitbook.io/hyperliquid-docs/trading/builder-codes
100 USDC in the perp account makes you a builder; >$40M has flowed to builders since
launch; ~40% of HL DAUs trade through third-party frontends. Threshold entry ($100!), and
the revenue is a share of OTHER people's volume, so it is not capped by our capital.

But it requires users, and we have none. Tagging our own orders with our own builder code
is a wash (we pay ourselves). This is a software business, not a trade. Capacity with zero
users: **$0/day at both $600 and $10,000.** Included only because the $100 threshold makes
it superficially look like the right shape; it is not an edge, it is a customer-acquisition
problem.

---

## Promotional layer — named and dismissed

- "Hyperliquid referral code X: **30% cashback**" (cryptoninjas, castlecrypto, chainplay,
  datawallet, buildix, hyperliquidguide and ~6 others). The referrer receives 10% of the
  referee's fees. You cannot rebate 30% out of 10%. This is **arithmetically impossible**,
  not an exaggeration. Every site making the claim is an affiliate. PROMOTIONAL/FALSE.
- "$100 sign-up bonus on Hyperliquid" — Hyperliquid has no sign-up bonus. Affiliate copy.
- 月入3万 ("30k a month from Binance Alpha") / "Alpha 保姆级教程" — content farms
  monetised by Binance referral links. PROMOTIONAL.
- airdrops.io / airdropalert / alphadrops / dropstab "tier lists" — all affiliate-funded
  lead-gen. Useful only for enumerating which programmes EXIST; their profitability claims
  are worthless.
- Note on selection bias: the loss-reporting layer on X is precisely what I could not
  reach (see method note). Where I could reach it second-hand — Chinese 撸毛 forums, the
  Lighter post-TGE coverage — it is uniformly more negative than the English promotional
  layer. Assume the true distribution is worse than what is written above.

---

## CATEGORY VERDICT

Dead for this account, and for a structural reason worth stating once:

**Every incentive programme currently live is gated on volume, and our volume is bounded
by our equity.** The programmes that call themselves "threshold" (Binance Alpha) denominate
the threshold in volume on a logarithmic schedule that explicitly pays more points for
higher balances — going $600 -> $10,000 cuts the required daily turnover ~4.5x. The
programmes that are honestly share-of-pool (every perp DEX) were empirically measured at
the single most generous instance in history (Lighter, $675M) to return **approximately
fees paid**. And the entire fee-discount/rebate/referral category has a hard arithmetic
ceiling of ~$1/day at $600 and ~$18/day at $10k, because reward is proportional to our own
volume — and that ceiling assumes a 100% fee waiver, which does not exist.

The one shape where a small account is genuinely not penalised — flat per-wallet sign-up
bonuses — is non-recurring and is not an edge.

Nothing here is worth a day of engineering. The only zero-cost actions are: (a) make sure
the account is under a referral code for the free 4% fee discount, worth ~$0.04/day now
and ~$0.7/day if the $10k is ever deployed, and (b) keep trading normally, which already
accrues any Season 2 allocation at zero marginal cost.
