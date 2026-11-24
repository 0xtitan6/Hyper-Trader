# HIP-4 binaryPrice depth + flow — 2026-09-30

**NO EDGE for us at $2.8k. Flow is concentrated on two markets — xyz:CL and
xyz:SPCX — but even the top book is a fixed 530 bps standing quote with
zero repricing under a 40 s stare and $500-$620 top-5 depth. Capacity
ceiling ~$50-$100/day/market and the same adverse-selection wall as
priceTouch and paired outcomes: the standing spread is calibrated, not
mispriced. n = 99 binaryPrice markets, 24 h candle flow, 3 book snaps
over 40 s per top-20.**

## Question worked

Follow-up (1) from `research/barrier-depth-2026-09-29.md`: priceTouch
confirmed dead — single-digit $/day/barrier capacity, best-of-book
$0.30-$45. The 09-29 report explicitly recommended killing priceTouch
as a target class and probing `template:binaryPrice` (n=99, 15x the
count) as a possibly-different candidate universe.

This is that probe.

## Workspace state note

`MEASURED.md`, `research/QUESTIONS.md`, and `.claude/agents/quant-researcher.md`
still do NOT exist on the current branch (`exec/maker-shadow-harness`). They
live on `feat/inplay-guard-pair-maker` and `stash@{0}`. This is the **sixth**
consecutive quant-researcher run to note it — same warning as
`research/oil-lag-2026-09-24.md`, `mm-model-spec-2026-09-25.md`,
`copysim-outcome-audit-2026-09-26.md`, `tournament-guard-2026-09-27.md`,
`barrier-lag-2026-09-28.md`, `barrier-depth-2026-09-29.md`. The branch
pointer needs a look before the next run; this file writes findings here
and stages a MEASURED.md graft delta at the bottom.

## Method

`research/binary_price_depth_probe.py` (read-only, 0.3 s per HL info call).

1. Enumerated all `template:binaryPrice` outcomes from `outcomeMeta`,
   filtered to future expiry (99 markets).
2. Per market: 24 h × 1 h `candleSnapshot` → summed trade count (`n`)
   and USD volume (`v × close`).
3. Ranked, then for the top 20 by trade count: snapped `l2Book` three
   times at 20 s intervals — best bid / ask / spread, best-of-book USD,
   top-5 USD.

## What the flow looked like

99 active markets total, **1 055 trades / $27 182 in 24 h**. The
distribution is extreme:

| segment | n_markets | share |
|---|---|---|
| zero trades / 24 h | 64 / 99 | 65 % |
| < 10 trades | 92 / 99 | 93 % |
| ≥ 20 trades | 3 / 99 | 3 % |
| top-1 (`xyz:CL @ 88.93`) | — | **65.9 % of trades, 66.2 % of $** |
| top-3 | — | 88.2 % of trades, 88.9 % of $ |

By underlying perp:

    xyz:CL     713 trades  $18 638
    xyz:SPCX   183 trades  $ 4 824
    BTC         60 trades  $     62
    xyz:SKHY    19 trades  $  1 414
    xyz:MU      14 trades  $    311
    (16 other perps split 66 trades / $1 933)

By time-to-expiry:

    <6h      24 markets   60 trades   13 nonzero
    6-24h    26 markets  964 trades   15 nonzero    <- 91 % of all flow
    1-7d     49 markets   31 trades    7 nonzero
    >7d       0 markets    -    -           -

Everything trades in the last 24 h before expiry. Long-dated binaries
are effectively dead — the same "no flow" pattern that killed the depth
probe on priceTouch and the 50c symmetric bids.

## What the top books looked like

Averages over 3 snaps × 40 s window on the top-20 by trades:

    coin       perp        trades  spread   best_bid$ best_ask$ bid5$   ask5$
    #68150     xyz:CL         695  5.31 %    $ 111     $ 119    $ 531   $ 621
    #67890     xyz:SPCX       179  8.30 %    $  22     $ 115    $ 372   $ 599
    #12100     BTC             56  0.20 %    $   0.01  $  25    $   7   $ 143
    #68010     xyz:SKHY        19 44.0 %     $  80     $ 125    $ 383   $ 895
    #49260     xyz:MU          13 166 %      $ 232     $  26    $ 654   $13 700
    #24940     xyz:CL          11 79 %       $   3     $ 164    $   8   $ 250

The top-two are the only books with symmetric two-sided depth. Every
market below rank-3 is either near-certainty (BTC $100k at $0.005 mid)
or has a lopsided book that puts most of the resting size on one side
only.

## Was anyone repricing?

Across the 3 snaps × 40 s window per market:

    #68150 xyz:CL     best-bid 0/2 changes, best-ask 1/2   <- 695 trades/day
    #67890 xyz:SPCX   0/2, 0/2                             <- 179 trades/day
    #12100 BTC        0/2, 0/2                             <-  56 trades/day
    #68010 xyz:SKHY   0/2, 0/2
    #49260 xyz:MU     0/2, 0/2

The most active market (695 trades / 24 h = one every ~2 min) put out
ONE new best ask across 40 s. Nobody was moving. This is exactly the
priceTouch pattern from `barrier-depth-2026-09-29.md`: a fixed policy
resting a wide spread that absorbs model drift by construction. It is
not a lag opportunity.

## Capacity under an honest ceiling

Take the best market, `xyz:CL #68150`:

- 24 h flow: 695 trades / $17 993 → ~$750/hr, ~29 trades/hr.
- Standing spread: 530 bps on a 0.565 mid = 3¢ wide.
- Top-5 depth: $530 bid / $620 ask.

Cost floor from `MEASURED.md` (as of 2026-09-20 fee audit): 8.97 bps
taker + 13.4 bps settlement per basket = 22.4 bps round-trip.

**If** we quoted one tick inside the incumbent and captured 10 % of the
flow at mid-recapture, expected gross ≈ $750 × 0.10 × 0.5 × 0.053 =
**$2 / hr = ~$48 / day**, before adverse selection.

But the paired-outcome finding (`stash@{0}:research/QUESTIONS.md → §1
answered set`) directly falsifies "quoting inside the incumbent":

- quoting behind: **zero fills in 5 h** — flow does not reach us
- quoting at the touch: fills arrive **above par** — locked loss on the
  basket regardless of outcome (realised −0.80 % against +1.25 %
  quoted)
- passive hedging: **−0.93 % vs −0.78 %** for crossing

binaryPrice does not escape that trilemma. Wider spreads mean the
incumbent has more to lose per pick-off, and quoting on their side gets
us picked when our quote is stale — exactly the same failure mode with
a bigger error term.

## What I assumed and where the result would break

- **Flow rate is stable across the day.** If the entire 24 h flow is
  concentrated in the last 30 minutes before expiry (very plausible for
  `xyz:CL` given the 20:00 UTC settlement), then hourly capacity in
  that window is higher and the rest is zero. The "capacity" number is
  soft either way — too little to matter to a $2.8k account.
- **The 40 s snap window represents typical repricing behaviour.** A
  larger BTC / CL print could trigger cascade repricing we did not see.
  This is exactly follow-up (2) from `barrier-depth-2026-09-29.md`:
  the standing-quote resilience is a null result under a static
  underlying. `xyz:CL` had a 6 bps intraday range during this probe.
- **The paired-outcome quoting result generalises.** binaryPrice pays
  $1 face at expiry same as any binary; the paired-basket-above-par
  failure mode is a mechanical consequence of that, not a market-
  specific artefact.

## What I could not determine

- Adverse-selection cost per fill on binaryPrice specifically. The
  paired-outcome baseline (−80 bps realised on +125 bps quoted) is
  from priceTouch + sports outcomes. binaryPrice has faster settlement
  (300 s window on most CL markets vs event-driven for sports), which
  could either amplify or dampen adverse selection.
- Whether the same operator runs the fixed-policy quotes on
  `xyz:CL #68150` and `xyz:SPCX #67890`. Both show ~5–8 % standing
  spreads and no repricing under a static underlying. If it is one
  policy, one behavioural change kills the whole surface; if it is
  two, they are correlated by a common risk model.
- The pre-expiry flow distribution. `xyz:CL` at 88.93 threshold
  expires 20260930-2100 UTC — 90 minutes after the reference time of
  this report. The 24 h number includes the runup; a fair capacity
  estimate would sample the last hour separately.

## Verdict

**NO EDGE.** binaryPrice is not the shortcut around the outcome-market
quoting problem. The universe is larger than priceTouch (99 vs 7),
top-book depth is 10× larger, and the top two markets carry real
flow ($750/hr and $200/hr) — but:

1. 65 % of markets have zero trades / 24 h.
2. The top book does not reprice under a 40 s stare while 29 trades/hr
   pass through, meaning either the incumbent is confidently right or
   we would be filled only when they are wrong (adverse selection).
3. The paired-outcome result generalises: quoting inside a wide
   incumbent locks a loss when both legs sum above par.
4. Even under charitable assumptions the whole-surface capacity ceiling
   is ~$50-$100 / day at 10 % flow share and mid-recapture — before
   fees, before adverse selection, before actually implementing
   anything.

Recommend the maker-shadow harness treat `binaryPrice` the same as
`priceTouch`: a class we do not target. Two follow-up probes remain
scoped but not urgent (below).

## Follow-ups (scoped, not urgent)

1. **Pre-expiry flow shape on `xyz:CL`.** Sample trades in the last
   60 minutes before a 20:00 UTC or 21:00 UTC settlement to see if
   flow concentrates enough that a short-window quote could clear a
   larger share. Same script, `--hours 1 --window pre_expiry`.
2. **Adverse selection on the incumbent's fills.** Fetch all trades on
   `#68150` for a 24 h window; back-check which side won against the
   settlement price. If the incumbent is P/L-negative, the "wall" is
   softer than assumed. If they are P/L-positive, the spread they set
   is a fair-value quote and we are just adverse selection to them.
3. **binaryPrice + priceTouch depth snapshot during a >50 bps BTC
   print.** Same as follow-up (2) of `barrier-depth-2026-09-29.md`.
   That is the only condition under which the lag-taker hypothesis on
   this class of surface is still alive.

## Reproducing

    .venv/bin/python research/binary_price_depth_probe.py
    # writes research/binary_price_depth_samples.jsonl (~160 rows, ~3 min)

## MEASURED.md graft (append on `feat/inplay-guard-pair-maker`)

    | HIP-4 binaryPrice flow + depth (n=99)                       | NO EDGE
    | 24h candle flow / 3 book snaps x 40s / top-20 by trades
    | 2026-09-30 | 99 markets, 1,055 trades / $27,182 in 24h.
    | 65% have zero trades / 24h. Top-1 xyz:CL@88.93 is 66% of
    | flow, top-3 are 88%. All flow is in the 6-24h ttl bucket
    | (91%), long-dated is dead. Top book best-of-book $22-$110,
    | top-5 depth $370-$620 (order of magnitude bigger than
    | priceTouch), standing spread 530-830 bps on the two active
    | markets. Best-bid changed 0/2 across a 40s window on the top-5
    | while ~29 trades/hr passed through -- same "calibrated fixed
    | policy" pattern as priceTouch. Charitable capacity ceiling
    | ~$50-$100/day on the best market before adverse selection,
    | fees, and the paired-outcome-above-par failure mode. Do not
    | target this class; treat it as priceTouch.
    | research/binary-price-depth-2026-09-30.md
