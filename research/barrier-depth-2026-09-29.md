# Barrier book depth — follow-up (3) from `barrier-lag-2026-09-28.md`

**NO EDGE / real depth is dust.**
**Best-of-book size $0.30–$45 per barrier; 6/7 books did not reprice a single tick over 5 minutes.**
**n = 427 book snapshots across 7 priceTouch barriers, 300s window, BTC mid 83983–84033 (6 bps range).**

## Question

The 09-28 barrier-lag report showed the 90k YES barrier standing at a
0.01 / 0.03 bracket for 88.7 s while BTC drifted. Open question:
**is that quote real depth, or is it dust that a $200 taker instantly
sweeps past?** Book cadence was throttled to 5 s in that probe; today's
run polls `l2Book` directly at 3 s per barrier.

## Method

- `research/barrier_depth_probe.py` (read-only, 0.3 s per HL info call).
- Every 3 s, snap `l2Book` on all 7 `template:priceTouch` markets
  (6 BTC strikes 60k–100k, 1 HYPE 100), plus `allMids` for BTC/HYPE
  perp mark.
- 300 s window, 61 samples per barrier, 427 total accepted rows,
  zero errors, zero throttle events.
- Per snap I record: best bid px + $-size, best ask px + $-size,
  top-5 cumulative $-depth per side, total book $-depth per side,
  number of levels per side.

## Results — book state (median across 61 samples)

    coin     perp   tgt   mid_bid   mid_ask   spread   bb_$    ba_$    bid5_$   ask5_$   bidTot   askTot   lv_b   lv_a
    #12090   HYPE   100   0.03920   0.04120   0.00180    4.1    4.3     78.3    137.8      88.6    681.1    11     20
    #12110   BTC    100k  0.00500   0.00510   0.00010    0.3   24.1    182.8     86.0     187.5 119634.0    10     19
    #12120   BTC    95k   0.00426   0.03870   0.03444   31.1 1318.6     37.5   1409.8      38.5 115292.3     6     15
    #12130   BTC    90k   0.00630   0.01515   0.00885    2.7   38.7     20.5    141.0      24.5   2594.7     7     20
    #12150   BTC    70k   0.00500   0.00510   0.00010    0.3    0.3     80.6    579.6      80.6   1067.6     5     20
    #12160   BTC    65k   0.00020   0.00520   0.00500    1.0    8.9     86.4    170.3      86.4   1051.2     5     20
    #12170   BTC    60k   0.00020   0.00735   0.00715    1.0   45.1      4.0     92.5       4.0    428.7     3     20

Numbers are USD notional (`size * price` — barriers pay $1 on touch).

## Results — do the books reprice?

    coin     unique_bid_px   unique_ask_px   bb_$_stdev   ba_$_stdev
    #12090   21              18              6.17         10.69
    #12110    1               1              0.00          0.00
    #12120    1               1              0.00          0.00
    #12130    1               1              0.00          0.00
    #12150    1               1              0.00          0.00
    #12160    1               1              0.00          0.00
    #12170    1               1              0.00          0.00

**Six of seven barriers held the exact same best bid and best ask
for the entire 300 s window.** Not "the level unchanged" — the same
single resting order, same size, same price. HYPE is the only book
that repriced at all (~35% of samples showed a new best bid).

BTC perp only moved $50 (6 bps) in this window, so a static book is
consistent with a well-designed standing quote absorbing a
micro-move. Consistent with the 09-28 finding: the standing quote
absorbs the drift range by construction.

## What the depth actually means

Take BTC 90k (`#12130`), the same barrier the 09-28 report used:

- Best ask is 0.01515 with $38.70 of size. Top-5 ask depth is $141.
- A taker lifting 200 YES contracts ($3.03 at best ask) walks the
  book to 0.02 → 0.03 → 0.04395 → 0.05145.
- Fair value for touching 90k in ~2 days at BTC 84k, σ_2d ≈ 4.2%:
  P(touch) ≈ 8.9% → 0.01515 is dirt-cheap.
- Capacity at 5 bps capture on this barrier: single-digit dollars.
  Consistent with `barrier-lag-2026-09-28.md` ceiling.

**The quote is real** — someone's order sits there — **but the
dollar capacity per touch is $10–$45.** Not dust in the sense of
"phantom quote", but dust for mission-scale.

## What about the 100k barrier's $119k ask total?

`#12110` shows `askTot = $119,634` — misleading. Best ask is only
$24, and top-5 is $86. The 6-figure total is stacked at 0.20–0.90
levels (paying implicitly for a >20% BTC rally in 2 days, P<<1%).
Real accessible depth is the same $10–$50 range as the other
barriers.

## Locked-market oddities

`#12110` and `#12150` show a **0.005 / 0.0051 spread** (2 bps).
That's ~2 bps of edge to a market-maker on a market where fair value
is probably closer to 0.001. Either:

1. A programmatic MM standing 0.005 / 0.0051 with zero size ($0.30
   each side) to farm ranks / rebates without meaningful exposure,
   or
2. A stale bracket that has not repriced away from a prior
   equilibrium.

Both interpretations reinforce **NO EDGE at scale** — these are not
markets where a $100k-mission MM finds room.

## Verdict

1. **NO EDGE for a barrier fair-value MM on the priceTouch surface
   today.** Best-of-book size $0.30–$45, top-5 depth $20–$580.
   Six of seven barriers are static across a full 5-minute window
   even with the underlying moving. Mission capacity per barrier
   per day is single-digit dollars — same ceiling as
   `mm-model-spec-2026-09-25`.
2. **The 90k standing 0.01–0.03 bracket is REAL but shallow.**
   Not a phantom quote; a $200 taker sweeps it in one clip.
3. **HYPE-100 is the only book that actually breathes** (~35% of
   samples show a new best bid). Still $4 size per side, $88 total
   bid.
4. **Follow-up (1) — trigger during a real BTC move — is not
   falsified.** No such move happened today (6 bps intraday range).
   Zero repricing under a static underlying is what a well-hedged
   MM would produce; the interesting test remains a lag-taker
   snapshot during a >50 bps / 60 s BTC print.
5. **Follow-up (4) — HYPE-perp barrier — mostly answered.** HYPE-100
   reprices where BTC barriers don't, but capacity is smaller
   ($4 best, $88 top-5). Not an alternative surface.

Not tradeable on this account under any weighting. Recommend the
maker-shadow harness stops modeling priceTouch as a target market
class and shifts to `binaryPrice` templates (n=101, 15x the count)
where flow / capacity may be materially different — separate probe.

## MEASURED.md graft (append on `feat/inplay-guard-pair-maker`)

    | HIP-4 priceTouch depth (BTC + HYPE) | NO EDGE
    | 5min / 61 samples per barrier / 7 barriers / 427 total
    | 2026-09-29 | best-of-book $0.30-$45 USD, top-5 depth $20-$580;
    | 6/7 barrier books did not reprice a single tick over 300s
    | (BTC mid 6bps range); the 09-28 "standing 0.01/0.03 bracket
    | on 90k" is a real order, not a phantom, but only $39 at best
    | ask and $141 top-5. Confirms priceTouch capacity ceiling is
    | single-digit dollars/day/barrier and matches mm-model-spec-
    | 2026-09-25. HYPE-100 is the only book that breathes (~35%
    | resample rate) but sits at $4 best size. Kill priceTouch as
    | a target class; test binaryPrice (n=101) instead.
    | research/barrier-depth-2026-09-29.md

## Follow-ups

1. **`binaryPrice` depth probe** — same script, `template:binaryPrice`
   filter, 101 markets. Rank by top-5 ask depth × trade count. That's
   the actual candidate universe.
2. **Depth snapshot during a real BTC print.** Same collector, gated
   on `|Δ_BTC_1m| > 50 bps for 2 consecutive minutes`. That's the
   only condition under which the 09-28 lag-taker hypothesis could
   still be alive.
3. **Compare on-book size to public trades on the same barrier.**
   If daily trades on #12130 sum to $135k but best-ask size is $39,
   the market is either (a) many small clips through the same
   resting order or (b) trades are happening off-book / at
   different price levels. `state/journal.jsonl` has our own fills;
   need a public trades snapshot to disambiguate.

## Reproducing

    .venv/bin/python research/barrier_depth_probe.py
    # writes research/barrier_depth_samples.jsonl (427 rows / 5 min)
    # then the two aggregation snippets above.
