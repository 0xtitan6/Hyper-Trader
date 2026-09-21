# MEASURED.md — what we have actually measured, with the numbers

Append-only ledger of **market** findings. `INVARIANTS.md` is the sibling for
**code** rules. Both exist for the same reason: something cost us money, and
without writing the number down we paid for it again.

**Read this before proposing a strategy.** Most ideas that sound new have
already been measured here and killed. A measured negative is a result — it is
cheaper than rediscovering it with capital.

**Rules for entries.** Every claim carries a date, a sample size, and a verdict.
No entry without a number. If a later measurement contradicts an entry, do not
delete it — append the correction underneath, because the fact that we believed
the old number is itself a finding.

---

## THE RECURRING TRAP — read this one twice

> **A wide spread, or deep resting size, on something nobody is trading (or that
> we cannot observe) is danger money, not opportunity.**

This has now presented four times in four different costumes. Each time it
looked like a fresh discovery. Each time the book was wide or deep *because*
nothing was happening, or because whoever was there knew more than us.

| date | costume | what it looked like | what it was |
|---|---|---|---|
| 2026-09-19 | in-play football | 6.68% paired edge | someone watching the match; **−$47** |
| 2026-09-19 | empty outcome books | infinite `pool/depth` reward score | 0.00x multiplier on $180 deployed |
| 2026-09-20 | weekend index binaries | uniform 9.80% across every strike | US markets shut; a Monday gap being priced |
| 2026-09-20 | deep zero-flow books | $330–358 depth at a clean 1.15% | **$0 volume, 0 fills, ever** |

**The test that catches all four:** never rank a surface by spread or depth.
Rank by *realised flow* — did anyone actually trade this, in the last 24h, at
all? Then confirm we can observe the underlying faster than the book moves.

Encoded in `scripts/run_pair_maker.py::scan` (`traded_24h`, `--min-vol`,
`--min-trades`) with regression tests. It is not a tuning knob.

---

## HIP-4 outcome markets

### Fees (2026-09-20, n=17 fills, $394 notional)
| role | n | notional | fee |
|---|---|---|---|
| maker (post-only) | 7 | $137 | **0.00 bps** |
| taker | 10 | $257 | **8.97 bps** |
| settlement | — | $265 | **13.4 bps** |

Maker fills are genuinely free. **Takers and settlement are not** — an earlier
claim of "zero HIP-4 fees" was true only for makers and wrong in general. This
matters: the minder hedges one-sided fills with IOC (taker), so every hedge
costs ~9bps and every completed basket ~13bps to settle. On a 1.15% edge that
is roughly a fifth of it.

### The paired trade is queue priority, not inefficiency (2026-09-20)
Seven soccer surfaces quoted **identically**: 1000 shares a side, exactly
0.0115 wide, from market creation. One market maker running a fixed policy.

Our "1.15% edge" **is that maker's spread**. We rest one tick inside on both
legs and win the fill only because we have price priority. There is no
mispricing being captured. Size the expectation accordingly.

### Profit requires equal SHARES at prices summing below 1.00
Equal *dollars* on both sides is not a hedge — it overweights the cheap leg and
is a directional bet. At 60/40 with $20 a side: 33 YES + 50 NO, which loses $7
if YES wins and makes $10 if NO wins.

```
profit = shares x (1 - YES_price - NO_price)
```
Buying a complete set at 1.00 earns exactly zero, whoever wins.

### Deep symmetric bids do not work (2026-09-20, n=70 markets, rolling windows)
| window | bid | edge | both fill | one-sided | EV/cycle |
|---|---|---|---|---|---|
| 24h | 0.45 | 10% | 3% | 95% | **−0.87%** |
| 48h | 0.45 | 10% | 5% | 94% | **−0.66%** |
| 120h | 0.40 | 20% | 5% | 91% | **−0.03%** |

YES and NO sum to ~1.00, so when YES falls to your bid, NO rises *away* from
it. Both legs only fill if price round-trips the whole band, which inside a day
essentially never happens. At 0.50/0.50 it is worst of all: you pay 1.00 for a
1.00 basket — all of the one-sided risk, **zero** edge.

Naive 14-day windows showed 27% both-fill and looked promising. That was the
window flattering it. Always bound a fill-rate measurement to the actual
holding period.

### Where the flow is (2026-09-20, NFL, n=28 surfaces)
| | median depth | median 24h vol | trades |
|---|---|---|---|
| in play (we refuse) | $382 | $2,155 | 15 |
| pre-game (quotable) | $40 | $72 | 3 |

**89% of all NFL flow is in-play.** The liquidity and the adverse selection are
the same place. Making money there needs a sub-second scoreboard edge against
people who do it professionally. We do not have one.

Soccer internationals are the opposite — pre-match, real flow, nothing
happening yet: England $13.0k/314 trades, Croatia $13.1k/316, Spain $12.9k/322.
Kosovo, Greece, Serbia, Ireland: **$0 / 0 trades** despite the deepest books.

### LP rewards — attribution UNPROVEN (2026-09-18 .. 09-20)
$200k/month pool, daily UTC epochs, merkle root ~00:15Z, claim-based, route
expires ~7d (unclaimed rewards are lost). Two full epochs qualified on every
documented dimension and paid **$0**.

Cause unresolved. Leading hypothesis is size, not breakage: our maker footprint
was **$137 for part of one day** against ~$4,169/leg of competing depth, which
rounds to nothing. Open test: three surfaces resting six days from kickoff so
quotes survive a complete scoring window. Read at 00:22Z.

Builder code `0xab5dbc…b704` is attached and accepted; `maxBuilderFee` returns
1000. No `approveBuilderFee` needed at fee 0.

### Measured dead ends — do not re-research
- **YES+NO complement arb**: closed. Min sum 1.00001 across 213 outcomes.
- **Favourite-longshot bias**: absent. Slope 1.034, p=0.74.
- **Early entry**: no window exists. The MM quotes from creation; $1.24 total
  pool in a market's first hour.
- **Barrier/digital arb at realised vol**: breakeven 38.0% vs realised
  32.9–39.7%. Not executable.

---

## Crypto one-touch barriers (HIP-4 `template:priceTouch`)

2026-09-20. Liquid and 24/7, unlike sports: HYPE 1,871 trades/24h, BTC up to
846. Underlying fully observable to us, so adverse selection is structurally
lower than any sports market.

| | implied vol | realised (14d) | read |
|---|---|---|---|
| BTC, all strikes | 36–61% | 33–35% | consistently **rich** |
| HYPE $100 touch | 59–64% | 67–74% | **cheap** |

The premium is real and persistent. **But we cannot short an outcome leg**, so
selling it means buying NO — risking 0.971 to make 0.029 at the 95k strike.
33:1 against. That is selling insurance without reserves. The one strike with
survivable odds (85k) trades at 36% implied, *below* our 38% breakeven.

HYPE is the correctly-shaped one: buy the touch at 0.503 against 0.538 fair,
+7%, loss capped at stake. Caveats: the edge is entirely a vol model, and we
already hold 2.88 HYPE perp — it stacks exposure.

### Market census — where the flow actually is (2026-09-21, n=201 markets)
| category | mkts | traded | 24h vol | trades | vol/mkt |
|---|---|---|---|---|---|
| **crypto barrier** | 8 | 8 | **$888,708** | 10,808 | **$111,088** |
| other sport | 46 | 37 | $815,746 | 11,620 | $17,734 |
| NFL | 28 | 27 | $600,569 | 8,220 | $21,449 |
| misc | 38 | 17 | $307,736 | 6,570 | $8,098 |
| index binary (xyz) | 39 | 26 | $262,494 | 2,488 | $6,731 |
| price binary | 38 | 13 | $23,470 | 232 | $618 |
| MLB | 4 | 1 | $36 | 4 | $9 |

$2.9M / 39,942 trades in 24h; only **129/201** markets have any flow at all.

**Eight crypto barriers out-trade all 28 NFL markets combined**, at 5-6x the
volume per market, 24/7, with the underlying fully observable to us.

### …and why we cannot yet trade them (2026-09-21)
The inverse of the soccer problem — huge flow, no depth:

| oid | target | spread | top-of-book depth | 24h vol | trades |
|---|---|---|---|---|---|
| 1209 | HYPE $100 | 7.1% | **$5** | $202,434 | 3,562 |
| 1213 | BTC $90k | 38.5% | $100 | $176,968 | 1,554 |
| 1214 | BTC $85k | 4.4% | **$3** | $176,966 | 3,234 |

3,562 trades against $5 of resting size. Nobody stands there because a barrier's
fair value **moves continuously with the underlying** — unlike a sports line,
which is static for days. Our requote loop runs every **20 minutes**; against a
book repricing on every BTC tick that is a standing offer to be picked off, and
the only fills we would get are the ones where BTC already moved against us.

**Verdict: best surface on the venue, and we are not equipped for it.** Not a
capital problem — a speed problem. Needs sub-minute repricing off the live mark
plus perp delta hedging. That is a build, not a config change, and it is the
most concrete thing on the roadmap.

---

## The copy engine

n=964 bot-only closes over 4.5 months. Mean **+$0.0416**/trade, sd $5.23,
**t = +0.25**. 95% CI on total **−$278 … +$358**. Proving the edge at 95% needs
60,720 trades ≈ 23.6 years.

Lifetime: −$225 gross / −$263 after fees on $107k notional. Fees are 0.035% of
notional, so **it loses before fees** — cost reduction cannot save it. Of
+$117.64 perps-only, **+$96 was placed manually**, leaving +$21.56 attributable
to the bot in four months.

It holds ~$179 of collateral. Scaling it multiplies a coin flip: at $10k the
same series gives +$627 with a CI of −$4,342 … +$5,597.

---

## Structural constraints — proposals violating these are dead on arrival

1. **No HL fee tier pays a maker rebate at any volume.** The MM programme is
   gated at ~0.5% of total exchange maker flow. Unreachable at any size we will
   have. The 9bp taker round-trip is a permanent floor.
2. **Minimum order value $10**; HIP-4 legs are **whole shares only** (a
   fractional size returns `Order has invalid size`).
3. **HIP-3 dexes hold separate collateral.** Never sum across them; cap per dex.
4. **Spot is not perp collateral for hedging.** A delta-neutral spot/perp pair
   costs ~1.5x notional.
5. **Outcome legs are spot-like** — bid only, no shorting. Being "two-sided"
   means holding both legs, or owning inventory before posting an ask.
6. **Agent wallets cannot** approve builders, approve agents, or withdraw.
7. **Portfolio margin needs >$10k** account value.

## Passive benchmarks — anything active must beat these
| | rate | note |
|---|---|---|
| HLP vault | 3.55% APR | 4-day lockup, $186M TVL |
| BTC/ETH funding carry | 10.2–10.3% APR mean, 95% hours positive | n=500 hourly; needs active margin management |
| HYPE funding carry | 13.63% APR | n=13,080 hourly, 92.2% positive, 18/18 30d windows |

Carry is a real edge at the wrong size: constraint 4 caps deployable notional
so ~$421 free earns ~$25/yr, which does not justify the liquidation risk of a
short perp leg on a box with this uptime history.

---

## Open questions
1. **Fill rate on paired quotes.** n=1 completed pair. Unknown, and it is the
   entire strategy. Measuring now on England + Croatia.
2. **Reward attribution** — size or breakage? Test resting, reads 00:22Z.
3. Does the copy engine have a profitable *subset* (by surface/coin/hour)
   dragged down by a removable one? Never run; the agent died first.
