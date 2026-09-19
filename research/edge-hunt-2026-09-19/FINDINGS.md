# Edge hunt 2026-09-19 — FINDINGS

Account 0xE503186067b1B0Fb973c063054B14c4625434A1a. Measured state on 2026-09-19:
perp accountValue $207.43 (withdrawable $0.00, fully committed as copy-trade margin),
spot USDC $639.00. All numbers below are from the live Hyperliquid API.

> **Run integrity note, stated up front.** Two workflows were launched — `hyper-edge-hunt`
> (8 hypotheses) and `hyper-scalp-hunt` (6 hypotheses) — and **both were interrupted**. The
> RESULTS JSON handed to this report was `{"survivors":[],"killed":[],"negatives":[]}`, which
> means *the pipeline returned nothing*, not *everything was refuted*. Only 5 of 14 agents
> wrote notes, and **no adversarial-verification agent ever ran**. Before writing this report I
> (a) ran the two abandoned scalp analyses whose data was already on disk, (b) ran the
> fee-tier hypothesis myself, and (c) personally ran the three missing skeptic lenses against
> the one surviving claim. Everything below is either measured by an agent and independently
> re-checked by me, or measured by me. Eight hypotheses were never executed at all and are
> marked NOT RUN — they are open ground, not negative results.

---

## 1. Bottom line

**One thing survived, and it is not enough.** The HYPE spot-perp funding carry is real and
holds up under adversarial checking: 13,080 hourly funding prints over 18 months give
+0.1556 bp/hour (13.63% APR), 92.2% of hours positive, **zero negative months in 19**, and
18 of 18 non-overlapping 30-day windows clear the true all-in cost of ~24bp. Capacity is
~$54,000 — two orders of magnitude more than we can deploy. But on this account the binding
constraint is not the edge, it is the capital: spot HYPE is not accepted as perp collateral,
so a delta-neutral pair costs 1.5x its notional in capital at prudent leverage, capping us at
~$426 of notional and **~$57 of profit per year**. Everything else died, and two deaths are
structural rather than incidental: (i) **no fee tier on Hyperliquid pays a maker rebate at any
volume** — rebates come only from a market-maker program requiring ~0.5% of total exchange
maker flow, so the 9bp taker round trip is a permanent floor for us, which closes the entire
market-making strategy class that every profitable HL account we have studied relies on; and
(ii) the microstructure signals we could measure are real but roughly 5x too small to pay for
themselves. The honest summary is that a $641 account on this venue has access to one modest
risk premium and no inefficiencies, and the carry trade cannot reach the $1,000 target.

---

## 2. All hypotheses — verdict, effect vs cost, capacity, confidence

### Wave 1 — `hyper-edge-hunt` (the 8)

| # | Hypothesis | Verdict | Effect vs cost (bps of notional) | Capacity | Confidence |
|---|---|---|---|---|---|
| 1 | **funding-harvest** (HYPE spot-perp carry) | **SURVIVED** | **+1363 bp/yr vs 24 bp one-time cost** | ~$54,000 | high |
| 2 | basis-spot-perp (convergence) | KILLED | +3.5 bp at lag-1 vs 23 bp cost → **-19.5** | ~$0 tradeable | high |
| 3 | hip3-dislocation | KILLED | apparent 23% "basis" vs $0 of book → **untradeable** | $0 | high |
| 4 | liquidation-cascade | NOT RUN | — | — | — |
| 5 | new-listing | UNDERPOWERED | n=5 listings in 6 months | — | high (on the power failure) |
| 6 | outcome-arb | NOT RUN | — | — | — |
| 7 | **fee-tier-reachability** | **BLOCKED (decisive NO)** | best achievable maker = **0.0 bp, never a rebate** | n/a | high |
| 8 | our-own-losses (forensic) | NOT RUN | — | — | — |

### Wave 2 — `hyper-scalp-hunt` (the 6), bar = 9 bp

| # | Hypothesis | Verdict | Effect vs 9 bp bar | Capacity | Confidence |
|---|---|---|---|---|---|
| 1 | scalp-book-imbalance | NO EDGE | **+1.93 bp** (NWt 3.95) → net **-7.07** | n/a | high |
| 2 | scalp-funding-clock | NO EDGE | +1.36 bp (t 1.53) → net **-7.64** | n/a | high |
| 3 | scalp-whale-followthrough | NOT RUN | — | — | — |
| 4 | scalp-lead-lag | NOT RUN (data collected) | — | — | — |
| 5 | scalp-hip3-thin | NOT RUN | — | — | — |
| 6 | scalp-volatility-timing | NOT RUN | — | — | — |

---

## 3. What survived: HYPE spot-perp funding carry

**What it is.** Buy $N of HYPE spot (pair `@107`), short $N of HYPE perp. Delta-neutral.
Funding on HL is hourly and has been persistently positive on HYPE — crowded longs pay, and
as the short you collect.

**The numbers** (all re-pulled independently by me, `/tmp/vh2.py`, `/tmp/vh3.py`):

| Measurement | Value | Sample |
|---|---|---|
| Mean funding | **+0.1556 bp/hour = 13.63% APR** | 13,080 hourly prints, 2025-03-23 → 2026-09-19 |
| Hours positive | 92.2% | same |
| Negative months | **0 of 19** | worst full month **+41.8 bp** (2026-04) |
| Non-overlapping 30d windows | **18/18 positive**, min +28.9 bp, median +97.4 | 18 independent windows |
| All-in cost | **24.0 bp, paid once** (spot taker 7+7, perp taker 4.5+4.5, spreads 1.0) | from `userFees` |
| Live spot book (@107) | spread 0.91 bp, $161k ask-side within 25 bp | 6 snapshot rounds |
| Live perp book | spread 0.11 bp, $54k bid-side within 25 bp | 6 snapshot rounds |
| Live basis | +7.38 bp | 6 rounds |

Note this corrects the original agent, which assumed the spot leg cost 4.5 bp. **Spot taker
on HL is 7.0 bp**, so the true round trip is 23 bp not 18 bp. It clears anyway, because a
buy-and-hold carry pays that cost once against a 1363 bp/year accrual.

**Capacity: ~$54,000** (min-side depth within 25 bp of mid). Capacity is not the constraint.

**Capital is the constraint.** Spot HYPE is *not* accepted as perp collateral on HL — only
USDC is — so the pair costs N (spot) + M (USDC margin). HYPE perp maxLeverage is 10
(maintenance 5%), and liquidation distance for a short at leverage L is (1/L − 0.05)/1.05:

| Leverage | Capital needed | Max notional on $639 | Liquidation at |
|---|---|---|---|
| 10x | 1.1 N | $581 | **+4.8%** — dies in days |
| 5x | 1.2 N | $533 | +14.3% |
| 3x | 1.33 N | $479 | +27.0% |
| **2x** | **1.5 N** | **$426** | **+42.9%** |

At the only prudent setting: $426 notional → $58.06 gross carry − $1.02 entry/exit − ~$0.30
margin-management = **~$57/year, i.e. 8.9% APR on deployed capital, 6.7% on total equity.**

**What to build — concrete next step.** Do *not* build a new engine. This is a single
position, held, with a margin watchdog:
1. Move $426 of spot USDC → $284 buy HYPE spot @107, $142 stays as perp margin.
2. Short 3.03 HYPE perp (szDecimals 2) at ~2x, isolated margin so it cannot touch the
   copy-trade book.
3. Add one check to the existing operator cron: if the short's margin ratio degrades past a
   threshold, sell spot HYPE and top up. This is the only ongoing work.
4. Accept the operational conflict: perp withdrawable is already $0.00, so this capital comes
   out of the pool the copy-trade bot uses. Copy trading measures at zero edge, so shrinking
   it to fund this is defensible — but it is a decision, not free money.

**What would kill it.** (a) HYPE funding turning persistently negative — it is positive
*because* HYPE is a crowded long, and a sentiment regime flip ends it; monitor the 30-day
funding sum and exit below +20 bp. (b) A sharp HYPE rally liquidating the short before a
top-up lands. (c) HL beginning to accept spot assets as perp collateral would *improve* it
materially — worth re-checking, since it would roughly halve the capital required.

**And the caveat that matters most:** this is a **risk premium, not an inefficiency**. You are
being paid to take the other side of leveraged HYPE longs. The 19/19 win record is the
pennies; the liquidation tail is the steamroller. $57/year against a mission needing +$359 by
2026-08-31 is ~15% of the goal. It is real. It is not a solution.

---

## 4. Killed by verification — the fatal flaw in one line each

- **basis-spot-perp (convergence):** *one bar of execution delay removes 85–95% of the measured
  reversion* — it is bid-ask bounce on thin spot books, not convergence. (PURR thr30 lag0
  +39.9 bp → lag1 +8.2 bp, t 13.0 → 1.5; XPL +46.8 → +3.5, t 15.7 → 1.5; PUMP +44.4 → +2.5,
  t 9.5 → −0.06.) Live executable basis on every liquid pair is 2.6–11.9 bp against a 23 bp
  cost floor. **Do not re-test close-to-close basis on illiquid HL spot pairs.**
- **hip3-dislocation:** *6 of the 10 HIP-3 dexes have $0 24h volume AND $0 open interest, so
  their quotes are phantom prints with nothing behind them* — and `hyna`, the only dex that
  mirrors base-dex crypto, is one of the dead ones. The eye-catching `cash:BTC = 70000` vs
  `flx:BTC = 91470` "23% dislocation" is a stale empty book. There is no live venue duplicating
  a base-dex crypto perp. **Cross-dex arb on HL does not exist to be traded.**
- **fee-tier-reachability:** *no VIP tier at any volume pays a maker rebate — the best outcome
  in the entire ladder is maker = 0.0 bp at $500M/14d* — and actual rebates come only from a
  separate market-maker program gated on 0.5–3% of **exchange-wide maker flow** (HL does
  $6–10.7B/day), paying just 0.1–0.3 bp. Our 14-day volume is **$3,256** with **$0 maker volume
  on every single day**; tier 1 alone is 1,536x that, implying 557x daily account turnover at
  $641 or 35.7x at $10,000. **Unreachable at $641, at $10,000, and at $1,000,000. The 9 bp
  taker round trip is permanent. The market-making strategy class is closed forever — stop
  studying profitable HL accounts that win on rebates.**
- **scalp-book-imbalance:** *the signal is genuinely there and is 4.7x too small* — best cell
  imb5 @30s = +1.93 bp with NW t 3.95 and bootstrap 95% CI [1.11, 3.18] excluding zero, against
  a 9 bp bar, net −7.07 bp. Notably the **spread is not the problem** (0.11–0.88 bp on these
  books); the fee is. More data would only pin the effect more precisely at ~2 bp. n = 778–893
  pooled observations, 8 coins, 825 L2 snapshots at 4.4 s.
- **scalp-funding-clock:** *the apparent −24.6 bp pre-settlement squeeze is pure look-ahead
  bias* — it only appears when you sort on f(h), the funding rate stamped **at** hour h, which
  is computed from that same hour's premium and is unknowable while you trade it. Re-sorting on
  f(h−1), which *is* known at decision time, the effect vanishes entirely (no bucket beyond
  ±1.94 bp, signs alternating, cumulative +0.7 bp). Unconditionally, no minute-of-hour bucket
  exceeds 1.36 bp (max t 1.53). n = 16,656 coin-hours, 40 coins, 418 funding hours.

---

## 5. Negative results — ground covered

- HL perp funding is positive-carry on far more than HYPE, but only HYPE is investable: over
  19 months BTC 7.87% APR (18/19 months positive), ETH 7.30% (16/19), **SOL 2.69% with 7
  negative months and −17.6% APR in 2026-02 — not investable**.
- 7-day carry holds are **net negative** for BTC, ETH, SOL, XPL and PURR: at short horizons
  the fixed round-trip cost dominates the accrual. Carry must be held ~30 days+ or not at all.
- Basis MTM is a rounding error on every liquid pair (+0.1 to +5.2 bp over 30 days) — the
  spot-perp basis is stationary and tight, so the trade is **pure funding carry, with no
  convergence component**. Do not model it as convergence.
- PURR has the widest basis on HL (p90 = 75 bp, 65.5% of hours over 18 bp) and **$150 of book
  depth with a 29 bp spread**. The basis is wide *because* it is untradeable. Wide basis on HL
  is a liquidity signal, not an opportunity signal.
- 8 of 19 spot/perp "overlap" pairs (@9 TRUMP, @20 PUMP, @117 BERA, @129 MON, @285 AZTEC,
  @258 STABLE, @306 AVAX, @206 ENA) are **dead ghost listings with $0–84/hour of spot volume**,
  superseded by Unit-bridged tokens. Their basis readings of 10,000–6,700,000 bp are stale
  prints. Screen on median spot $volume/hour before trusting any basis number.
- Unit-bridged spot tokens (UBTC, UETH, USOL…) are **bridged, not fungible** — you cannot
  deliver UBTC into a BTC perp, so deviation there is bridge friction, not arbitrage.
- HL `candleSnapshot` retains only **~5,000 candles per interval** regardless of startTime
  (1m = 3.6 days, 5m = 17.5 days, 15m = 52 days, 1h = 209 days), and requests with a past
  endTime return `[]`. Any plan needing 1m data over 30+ days is impossible from this API —
  recover power by widening the cross-section instead.
- HL's listing cadence **collapsed in 2026** to ~1 new perp/month (2025 ran 3–5/month). Only 5
  perps have listed in the last 6 months. New-listing effects are permanently underpowered on
  this venue unless cadence recovers.
- HL backfills majors from pre-launch CEX data (BTC/ETH first candle = 2020-09-13), so first-
  candle dating is only reliable for post-2024 listings.
- `km` and `mkts` are the same 23-asset universe deployed twice by one operator; both are
  effectively dead ($11.7M and $0 of 24h volume respectively against base-dex $9.1B).
- Our account carries an **active 4% referral discount** (effective perp taker 4.32 bp) and
  **0% staking discount**. Staking HYPE worth 0.0001 bps of max supply would buy a 5% fee
  discount — that is 0.22 bp off 4.5 bp and cannot rescue any hypothesis here.

---

## 6. Closing assessment

Nothing here changes the strategic picture, and I want to be exact about that rather than
generous. Of 14 hypotheses, 8 were never executed because the run was interrupted; of the 6
that produced measurements, 3 died, 2 were measured as real-but-far-too-small, and 1 survived
as a modest risk premium worth ~$57/year. The survivor is not an inefficiency — it is a fee
for standing in front of a crowded trade, and it will stop paying when HYPE sentiment turns.

The most important result in this document is the negative one. Hyperliquid's fee schedule,
read directly off our own account, says that **no amount of volume at any account size ever
earns us a maker rebate**; rebates exist only for entities running ~0.5% of the entire
exchange's maker flow. That permanently forecloses the strategy class that every profitable
HL account we have examined actually uses, and it fixes 9 bp as a hard floor under every
future idea. Combined with the two microstructure measurements — where the signals were
statistically solid at ~2 bp and the *spread* was under 1 bp, so the **fee alone** was what
killed them — the picture is consistent and unflattering: we are a pure taker on a venue whose
short-horizon inefficiencies are smaller than our cost of trading, and we have no route to
lowering that cost.

So the honest conclusion is that **a $641 account on Hyperliquid may have no accessible edge.**
That is not a failure of searching; it is the search returning a clean answer. The real options
are the ones the user already named:

- **A different venue** — one where a small account can be a rebate-earning maker, or where
  taker costs are low enough that a 2 bp microstructure signal is tradeable. Our measured
  signals are real; they are simply not real *enough* at 9 bp. This is the only option that
  changes the constraint rather than working around it.
- **A different scale** — the carry trade genuinely improves with size (capacity ~$54k versus
  $426 deployable), but reaching a size where it matters requires capital we do not have and
  cannot earn from a 6.7% APR premium. This option is circular.
- **Not trading** — deploy the carry as a low-effort ~7% yield on otherwise-idle USDC, stop
  paying attention to it, and stop spending effort hunting for an edge that this venue does not
  appear to offer a taker of this size.

Before any of that, the single highest-value unexecuted item is **hypothesis #8,
`our-own-losses`**: a full forensic decomposition of our own fill history by coin, surface and
holding period. It is the only remaining hypothesis that could produce an actionable result
*without* needing a new edge — if base-dex perps are profitable and a HIP-3 surface is dragging
them to zero, we would simply stop trading the losing surface. It costs one agent-run and no
capital. That, not another edge hunt, is what I would do next.

The $1,000 target is not reachable from anything measured in this document.
