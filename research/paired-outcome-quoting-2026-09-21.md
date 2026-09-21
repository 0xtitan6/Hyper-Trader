# Is there ANY positive-EV configuration of paired outcome quoting?

**NO EDGE in the configuration we run.** Cross-to-complete costs −18.3 bps of face
per basket by construction and realised −76 bps; 8 peer wallets running the same
policy lost **−5.31 bps of notional on $420,481 / 17,057 fills** (1/8 profitable).

**UNPROVEN, and the only survivor:** 100% passive single-leg round-trip (buy at the
bid, sell the *same* leg at the ask, never cross, never settle) prices at **+3.8 to
+15.6 bps of face per round trip**. Turnover at our size is unmeasured — our only
live evidence is 2 passive fills in 4h.

Samples: 42,251 public maker fills / $1.73M notional / 30d; 3,075 tape trades with
counterparties; 142 live book legs; 198 markets screened.

---

## 1. The finding that reframes the question: YES and NO are ONE book

Every trade prints on **both** legs simultaneously, at prices summing to exactly
1.000000 — min = max = mean = 1.000000 over **n=807** matched prints, with opposite
aggressor tags (`{('A','B'): 807}`). The live books agree: `askNO == 1 − bidYES` to
within 0.0000% on **142/142** legs, and mid(YES)+mid(NO) = 1.00000 exactly.

So the two legs are two representations of one instrument. This has three
consequences that invalidate how we have been reasoning:

1. **"Resting bids on both legs" is not a paired trade — it is a two-sided quote in
   a single asset.** Our NO bid at `bidN+tick` is arithmetically an *offer* on YES at
   `askY−tick`. The strategy is plain market making and should be priced as spread
   capture minus adverse selection, not as basket assembly.
2. **"Both legs filling" is not two independent events.** It is the price crossing
   our bid *and* our offer — i.e. round-tripping the spread. It cannot be modelled as
   two fill probabilities multiplied together.
3. **"Hedging a one-sided fill by buying the complement" is not a hedge.** It is
   crossing the spread to flatten. Cost is one tick *by construction*:
   `(bidY+tick) + askN − 1 = (bidY+tick) + (1−bidY) − 1 = tick`, and this held on
   **142/142** measured legs with zero dispersion (p10 = p90 = +0.050%).

## 2. The fee model in MEASURED.md is wrong, and the error matters

Measured across 42,251 public outcome fills, $1.73M notional:

| action | n | notional | fee |
|---|---|---|---|
| **Buy, taker** | 10,243 | $478,616 | **0.00 bps** |
| **Buy, maker** | 11,272 | $376,587 | **0.00 bps** |
| Sell, maker | 10,069 | $418,392 | 7.83 bps |
| Sell, taker | 10,105 | $202,543 | 13.73 bps |
| Settlement | 340 | $223,947 | 13.27 bps |
| Merge Outcome | 222 | $28,682 | 14.00 bps |

**Entry is free; every exit is charged.** MEASURED.md records "taker 8.97 bps",
which is not the current schedule — our own last two taker *buys* (the Giants and
Croatia minder hedges) were billed **$0.00**. Our older `Buy/crossed` fills were
charged ~10 bps, so the schedule changed or varies by `deployerFeeScale`; either
way the live regime is buy-free.

Two corrections follow:
- **The −0.80% on Giants/Croatia was not fees. It was drift.** Crossing was free;
  the 6 minutes between the maker fill and the hedge cost 105.6 bps and 21.2 bps.
  The minder's *latency*, not its policy, is what we paid for.
- **Holding to settlement is the expensive exit (13.27 bps of face), not the cheap
  one.** Selling the leg back as a maker costs 7.83 bps of *notional* = 3.9 bps of
  face at px 0.50 — **3.4× cheaper than settling.**

## 3. What the people running this strategy actually earn

I identified the makers from the WS tape (`users:[buyer,seller]`), which removes the
tid-matching that 429'd on 2026-09-20. Convention verified against 1,210 tape trades
matched to known fills: role and side correct **1210/1210**.

Eight wallets are near-identical — 2,125–2,375 fills, $51k–59k notional, ~1.3 days,
48–50% maker, 100% outcome markets — and trade **with each other on 27.3% of tape
trades**. A reward-farming cluster running our exact strategy:

| | value |
|---|---|
| fills | 17,057 |
| notional | $420,481 |
| **gross of fees** | **−0.43 bps** |
| fees paid | 4.88 bps |
| **net** | **−5.31 bps of notional** |
| profitable wallets | 1 / 8 |

They are 50% maker / 50% taker, and their gross is ~zero — consistent with earning
the half-spread passively and paying it back aggressively. **Their entire loss is
the fee on the taking half.** Ten makers, fully marked: 1/9 with closed books was
profitable, median −6.0 bps, mean −9.8, t = −2.10.

The one large winner (0x35a0e277, +$29,881 on $1.09M) is **not** a quoter: it is
58% taker and its PnL is `−$230,036 on trades + $223,649 at settlement + $25,037 on
merges` across 277 markets — a directional forecaster holding to resolution. Checked
for the obvious trap: zero net-short legs and history starting inside the window, so
this is not 30-day truncation. It is simply a different strategy and says nothing
about quoting.

## 4. Adverse selection on passive fills

Markout on passive fills, in bps of $1 face, mark = mean trade price in
[t+h, t+h+180s], 5% winsorised, legs restricted to 0.05 ≤ px ≤ 0.95:

| horizon | n | median | trim. mean | t |
|---|---|---|---|---|
| 5s | 1,222 | +1.98 | +3.91 | 5.33 |
| 30s | 1,022 | +4.78 | +7.28 | 9.56 |
| 60s | 1,012 | +7.73 | +7.22 | 8.56 |
| 900s | 404 | +14.36 | +16.44 | 14.89 |

(pure third-party flow — no farm wallet on either side.) Passive fills are **not**
catastrophically adversely selected. But the median book half-spread is 14.8 bps of
face, so a fill that is only worth +1.98 bps at 5 seconds has given up ~87% of the
spread to impact immediately, recovering over minutes.

## 5. The arithmetic, per configuration

Median book spread 29.5 bps of face (n=142 legs); median paired edge after our
one-tick improvement each side +19.5 bps.

| configuration | bps of face | verdict |
|---|---|---|
| both sides fill passively, hold to settlement | +19.5 − 13.27 = **+6.2** | thin |
| one side fills, cross instantly, settle | −5.0 − 13.27 = **−18.3** | **negative by construction** |
| one side fills, cross after 6 min (observed) | **−76** (n=2) | what we did |
| **passive round-trip, sell the leg back, never settle** | +19.5 − 3.9 = **+15.6** | best case |
| same, charged the measured 60s markout | +7.7 − 3.9 = **+3.8** | realistic |

Breakeven passive-fill share for the settle path, with instant crossing:
p\* = 18.3/(6.2+18.3) = **74.7%**. At the drift we actually realised, p\* = **92.5%**.
We ran ~50% maker. That is why it lost.

## 6. What I assumed, and what dies if I am wrong

- **Turnover is assumed, not measured.** Every dollar figure below rests on it.
  At our only observed rate (2 passive fills in 4h on 2 surfaces, $50 legs → ~$1,200
  of face bought per day), +3.8 to +15.6 bps is **$0.46–$1.87/day = $167–$683/yr**,
  6–24% APR on a $2,800 account. That brackets HLP (3.55%) and HYPE carry (13.63%).
  **If turnover is half what I assumed, this is worse than the carry trade.**
- **The markout mark is an estimator, not a book.** I have no historical L2, so the
  mark is a mean of subsequent trade prices. Order-flow autocorrelation biases it
  down; bid/ask bounce biases it up. The *sign* is robust; the magnitude is not.
  Section 5's "realistic" row dies if this is off by 4 bps.
- **The cluster's gross is contaminated.** 27.3% of their tape trades are internal,
  which mechanically drags gross toward zero. Their −5.31 bps *net* is sound; their
  −0.43 bps *gross* is weak evidence about a non-farming participant.
- **The fee schedule may vary by market.** `deployerFeeScale` is 1.0 on the markets
  I sampled, and our own older fills were charged differently. If buys become
  chargeable again, the round-trip config loses ~4.5 bps and goes to breakeven.
- Sections 1 and 2 are exact identities and billing records. They do not depend on
  any of the above.

## 7. What I could not determine

- **Our achievable fill rate at the front of the queue.** This is now the only thing
  standing between "UNPROVEN" and a verdict. n=2.
- **Whether a tick improvement survives competition.** The 29.5 bps spread is ~6
  ticks; if the incumbent re-improves on us we lose the queue, and I have no
  requote-latency data on them.
- **Why our taker buys were charged ~10 bps in August and $0.00 in September.**

## 8. The specific next measurement

Quote **one leg only** on 3–5 flowing surfaces, at the front of the book, $25 a leg,
with `leader_exit_auto_close` off and **no minder hedging at all**. On each fill,
immediately post the *same leg* back at `ask − tick`. Never cross. Never hold
through resolution. Log every fill with `crossed`, `dir` and `fee`.

The number to read after 72h: **maker share of our fills** (target ≥90%; we ran 50%)
and **completed passive round-trips per day**. If round trips/day × $50 × 3.8 bps
does not clear $0.50/day, the configuration is capacity-dead at our size and the
question closes for good — redirect to the crypto-barrier build (question 2), which
out-trades all 28 NFL markets combined.
