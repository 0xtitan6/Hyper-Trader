# HIP-4 binaryPrice incumbent-wall responsiveness — 2026-10-03

**NO EDGE, but with a correction to the 09-30 report.** The incumbent book
on live `xyz:CL` binaryPrice markets is NOT a frozen "calibrated fixed
policy" — it reprices on a seconds-to-minutes cadence and tracks CL mid.
Across 3 markets × 30 snaps × 10 s intervals, I saw 3–6 best-bid price
changes and 5–7 best-ask changes per market while CL mid moved only 8.9 bps
(91.065 → 90.985 → 91.003). But a responsive incumbent is harder to
fade, not easier: no stale quote window to pick off, same ~$500 top-5
depth ceiling, same adverse-selection wall. n = 30 iters × 3 markets, 5 min.

## Why this probe

The 09-30 report (`research/binary-price-depth-2026-09-30.md`) called the
top-of-book incumbent on binaryPrice a "calibrated fixed policy":

> Best-bid changed 0/2 across a 40 s window on the top-5 while ~29
> trades/hr passed through, meaning either the incumbent is confidently
> right or we would be filled only when they are wrong (adverse
> selection).

That was 3 book snaps × 40 s total — a thin window that can't distinguish
"frozen incumbent" from "incumbent that reprices every 60–120 s and we
happened to sit between two re-quotes". This probe stretches the window
to 5 min across the three live `xyz:CL` binaries.

## Method

Read-only probe (`research/binary_wall_responsiveness_probe.py`), 30
iterations × 10 s interval, 0.15 s inter-call sleep. Each iteration
snaps:

1. `allMids(dex="xyz")` → `xyz:CL` mid
2. `l2Book` for `#73540` (CL@100, exp 2026-10-30 20:00 UTC, ~27 d)
3. `l2Book` for `#73550` (CL@82,  exp 2026-10-30 20:00 UTC, ~27 d)
4. `l2Book` for `#77420` (CL@91.5, exp 2026-10-05 13:35 UTC, ~2.3 d)

30 snaps × 3 markets = 90 book observations. 3 iters had transient
`None/None` books (iters 10, 21, 23) — momentary book-empty states
during incumbent cancel/replace cycles.

## Findings

### 1. The wall moves

Transition counts over the 5-min window (ignoring None-boundary flaps):

| market       | strike | ttl   | bid Δ | ask Δ | median spread | spread range     |
|--------------|-------:|------:|------:|------:|--------------:|------------------|
| #73540 (CL@100)  | $100.00 | 27 d | 3     | 5     | $0.00459      | $0.00459–0.00933 |
| #73550 (CL@82)   |  $82.00 | 27 d | 6     | 6     | $0.00472      | $0.00472–0.01073 |
| #77420 (CL@91.5) |  $91.50 | 2.3 d | 4     | 7     | $0.01999      | $0.01998–0.02998 |

That is 3–6 real best-bid price changes and 5–7 real best-ask changes
per market in 5 minutes. The 09-30 "0/2 changes in 40 s" result holds
only in that narrow window; the longer window shows the incumbent is
actively quoting. The three transient book-empty states (iters 10, 21,
23) are consistent with a cancel-and-replace loop — not a static resting
order.

### 2. Reprices track CL mid directionally

CL mid trajectory: 91.065 → 91.066 → … → 91.055 → 91.046 → 91.024 →
91.010 → 91.004 → 90.985 → 91.003. ~9 bps total round-trip.

Representative repricings (paired with the CL step):

- `#73540` ask: 0.23109 → 0.23034 → 0.22985 at CL 91.065 → 91.055, then
  0.23366 as CL slipped to 91.010. YES = "CL above 100 at Oct 30 20:00";
  near-term CL drift should barely matter for a far-OTM 27-d strike,
  and indeed the moves are 20–40 bps on the YES price.
- `#73550` ask: 0.76694 → 0.77078 at CL 91.065 → 91.046. Threshold 82 is
  deeply ITM; a small CL dip raising "will CL stay above 82" probability
  is the right-sign move only if the market reads threshold the opposite
  way (sign ambiguity depending on `priceDescription` semantics; the
  magnitude is small enough it's noise either way).
- `#77420` (closest-to-money, 2.3 d): bid 0.44 → 0.43001 → 0.43 and ask
  0.45999 → 0.45 → 0.45999 → 0.44999 as CL slipped from 91.065 toward
  91.004 (below the 91.5 strike). YES ("CL above 91.5 at Oct 5 13:35")
  dropping from 0.45 mid toward 0.44 mid is the right direction.

With only 2–4 non-flat paired observations per market, I don't report
a numeric β — the point is the sign and the fact that reprices happen
at all, not a precise coefficient.

### 3. Still no edge

A responsive incumbent is strictly worse for a maker-fade strategy than
a frozen one:

- No stale-quote window to fade. If the incumbent updates in seconds
  after a CL move, our fv-based reprice has to be seconds faster than
  theirs to earn anything, and we have no latency advantage over an
  on-exchange MM.
- Capacity ceiling unchanged: top-5 ask depth was $500–$620 on 09-30's
  xyz:CL top market, and 5000-size × $0.46 ≈ $2300 top-of-book notional
  on #77420 today. That's quote capacity per side, not realised flow.
  Realised 24-h flow on 09-30 was $750/hr on the top-of-flow market —
  implying a maker share of a few $/hr before adverse selection.
- The paired-outcome-above-par failure mode from 09-30 is unchanged:
  quoting inside a wide incumbent on a YES/NO pair that sums above $1
  locks a loss.

The 09-30 verdict ("treat `binaryPrice` the same as `priceTouch`: a
class we do not target") stands — but for the right reason. It's not
that the wall is frozen; it's that the wall is actively quoted by
someone with equal or better information than us.

## What this does NOT answer

- **Adverse selection on the incumbent's own fills.** HL `recentTrades`
  returns HTTP 500 on outcome coins (`#NNNNN`) and `candleSnapshot`
  returns 500 for the same, so public per-trade data is not available
  for outcome markets. We cannot score "did the incumbent's maker
  flow win or lose against settlement" without wallet-level data. The
  09-30 follow-up #2 is **infeasible with public endpoints** and should
  be de-scoped unless we can identify the incumbent's wallet and pull
  `userFillsByTime`.

- **Repricing cadence under a real BTC/CL print.** CL moved only 9 bps
  during this sample. Follow-up #3 from 09-30 — "snapshot during a
  >50 bps BTC print" — remains open. The 1-minute incumbent response
  I observed here is on background drift, not on a shock.

## Verdict

**NO EDGE.** The incumbent on `xyz:CL` binaryPrice is a live quoting
agent, not a frozen policy. The 09-30 "static wall" framing was a
sampling artifact (40 s window); the no-edge conclusion is unchanged
and the mechanism is clarified. Do not reopen `binaryPrice` as a
maker target. The remaining open probe is the shock-window one.

## Follow-ups (scoped, not urgent)

1. **Shock-window probe (unchanged from 09-30 #3).** Trigger the same
   30-iter loop when `|Δ_CL_1m| > 50 bps` for 2 consecutive minutes.
   Measures whether the incumbent's update latency *degrades* under
   stress — the only condition under which a lag-fade might still be
   alive on this class.

2. **De-scope: adverse-selection post-mortem on the incumbent.** HL
   does not expose public trades on outcome coins. Mark 09-30 follow-up
   #2 blocked unless (a) we identify the incumbent wallet via on-chain
   fill events or (b) HL exposes outcome-coin trade history.

3. **Reconcile the 09-30 top-market trade-count math.** 09-30 reported
   ~29 trades/hr with "0/2" best-bid changes in 40 s. If the incumbent
   reprices like today's data, the real metric should be reprices-per-
   trade, not reprices-per-second. A reprice every 60 s with 29 trades/hr
   means ~0.5 trades per quote window — different story from "frozen
   policy".

## Reproducing

    .venv/bin/python research/binary_wall_responsiveness_probe.py
    # writes research/binary_wall_responsiveness_samples.jsonl
    # 30 iters, 10 s interval, ~5 min total

## MEASURED.md graft (append on `feat/inplay-guard-pair-maker`)

    | HIP-4 binaryPrice incumbent-wall responsiveness (xyz:CL × 3)  | NO EDGE
    | 5 min / 10s interval / 30 iters / 3 live CL binaries
    | 2026-10-03 | Incumbent is NOT frozen (09-30 report wrong on this
    | sub-point): 3-6 best-bid and 5-7 best-ask price transitions per
    | market in 5 min while CL mid moved 9 bps. 3 transient book-empty
    | states consistent with cancel/replace. Reprices track CL mid
    | directionally. No-edge conclusion from 09-30 unchanged and
    | strengthened — a responsive incumbent is strictly worse for a
    | maker-fade. Shock-window probe (|dCL_1m| > 50 bps) remains the
    | only still-alive hypothesis. Public per-trade data on outcome
    | coins is unavailable (recentTrades + candleSnapshot both 500 on
    | '#NNNNN'); 09-30 follow-up #2 blocked.
    | research/binary-wall-responsiveness-2026-10-03.md
