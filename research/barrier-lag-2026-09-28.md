# HIP-4 barrier lag vs the underlying — 2026-09-28

**NO EDGE for a lag-taker. UNPROVEN as a fair-value maker. Sample: 600 s of
`bbo` on BTC perp + four `template:priceTouch` barriers. BTC = 5,122 BBO
ticks (8.54 Hz). Barrier BBO = 0–9 ticks per market (0–1.5/min). Standing
90k-YES bracket was 0.01 / 0.03 (100 % of mid) against a BS-implied fair-
value drift of ~1 % of face across the whole window. The lag is real — 500×
in tick-count — but the standing spread is calibrated to absorb it.**

## Workspace state, up front

`MEASURED.md`, `research/QUESTIONS.md`, and `.claude/agents/quant-researcher.md`
do **not** exist on `exec/maker-shadow-harness`. They live on
`feat/inplay-guard-pair-maker` (`stash@{0}` has newer edits than that branch
tip). Fifth consecutive quant-researcher run to note it — same warning as
`research/oil-lag-2026-09-24.md`, `mm-model-spec-2026-09-25.md`,
`copysim-outcome-audit-2026-09-26.md`, `tournament-guard-2026-09-27.md`. The
branch pointer needs a look before the next run; this file writes findings
here and stages a `MEASURED.md` graft delta at the bottom.

Question worked: `research/QUESTIONS.md → OPEN §1` — "Do HIP-4 crypto
barriers reprice slower than their underlying?" (topmost open in the stashed
queue).

## What I measured

Ran `research/barrier-lag-2026-09-28/collect_bbo.py` for 600 s at 2026-09-28
07:56 UTC, subscribing simultaneously to HL WebSocket `bbo` for:

| feed          | asset id | note                     |
|---------------|----------|--------------------------|
| BTC perp      | native   | reference underlying     |
| `#12110`      | 100k YES | +20.5 % up-touch, 3 d    |
| `#12130`      | 90k YES  | +8.5 % up-touch, 3 d     |
| `#12111`      | 100k NO  | mirror of 100k YES       |
| `#12131`      | 90k NO   | mirror of 90k YES        |

`bbo` fires on every touch change (unlike `l2Book`, which HL throttles to a
~5 s heartbeat — the earlier attempt at
`research/barrier-lag-2026-09-22/collect.log` used `l2Book` and never wrote a
verdict).

24 h flow, as sanity: 382 trades / $41 k face on 100k, 795 / $135 k on 90k —
these ARE real markets, just quiet during my sample.

## Results

BTC moved 82,937.5 → 83,062.5 over the 600 s, range 82,916 – 83,121
(25 bps peak-to-trough). This is a quiet BTC window.

### Cadence

| feed          | BBO updates / 600 s | ticks / s |
|---------------|---------------------|-----------|
| BTC perp      | 5,122               | 8.54      |
| BTC_90k_yes   | 9                   | 0.015     |
| BTC_100k_no   | 6                   | 0.010     |
| BTC_100k_yes  | 0                   | 0         |
| BTC_90k_no    | 0                   | 0         |

Median BTC BBO ticks between barrier BBO updates:

| barrier       | median stale-ticks | max | median dt |
|---------------|--------------------|-----|-----------|
| BTC_90k_yes   | 228                | 765 | 24.5 s    |
| BTC_100k_no   | 30                 | 39  | 3.7 s     |

The 100k NO update stream at 3.7 s is a heartbeat (bid unchanged, ask
alternates ±0.00001), not a reprice. Two of the four active feeds emitted
**zero** BBO updates in 10 min.

### The updates are noise, not repricing

For the 90k YES barrier, every one of the 8 inter-update deltas moved the ask
by exactly one quote-tick (±0.00001) with the bid unchanged. And the sign was
NOT correlated with BTC drift:

| # | BTC ticks in window | BTC drift (bps) | Δask       |
|---|---------------------|-----------------|-----------:|
| 1 | 656                 | −3.5            | +0.00001   |
| 2 | 228                 | +2.7            | −0.00001   |
| 3 | 146                 | +3.5            | +0.00001   |
| 4 | 161                 | −0.7            | −0.00001   |
| 5 | 765                 | −6.4            | +0.00001   |
| 6 | 381                 | +1.1            | −0.00001   |
| 7 | 33                  | +0.5            | +0.00001   |
| 8 | 104                 | 0.0             | −0.00001   |

Correlation of Δask sign with BTC-drift sign: 4 agree / 3 disagree / 1 tied.
Random. The MM is shuffling one price-tick, not tracking underlying moves.

### The standing spread absorbs the plausible fair-value drift

Back-imply annualised vol from current mid at S = 83,000, T = 3 d:

| barrier | mid   | implied σ_ann |
|---------|-------|---------------|
| 90k YES | 0.020 | 0.384         |
| 100k YES| 0.018 | 0.869         |
| 60k YES | 0.002 | 1.158         |

The vol skew is telling — deeper OTM barriers price higher σ (fat-tail /
jump premium). Fine, ours is the 90k so use 0.38.

BS one-touch (`2 · Φ(−ln(K/S)/(σ√T))`) at the observed BTC extremes:

- S = 82,916 → fair(90k YES) ≈ 0.019
- S = 83,120 → fair(90k YES) ≈ 0.023

So over the entire 600 s window the true fair value of 90k YES drifted in a
~0.4-cent-of-face band, all comfortably inside the standing 0.01 / 0.03
bracket. The MM has no reason to reprice; anyone lifting the 0.03 ask is
paying ~30–40 % over fair (0.03 vs 0.02 mid).

### Where a taker would win

Solve for the BTC price that pushes BS fair value up to the standing ask
(0.03) at σ = 0.38, T = 3 d, K = 90k:

    0.03 = 2·Φ(−ln(90/S)/(0.38·√(3/365)))
    ⇒ S ≈ 84,050

BTC would need to rally to ~84.0 k — a **+130 bps** move from the sample
midpoint — before the standing 0.03 ask goes on-the-money. Symmetric on the
downside: standing 0.01 bid goes off-the-money at S ≈ 81,600, a −170 bps
move. So the standing quote survives every BTC swing within roughly ±1.5 %.

That's not tight. It IS bigger than a normal BTC 10-min swing (we saw
25 bps here); larger swings happen many times a day. A taker running a
live BS engine would in principle pick off the ask on a fast +130 bps
rally. Two catches:

1. The MM cancels on the same move — our data has zero example of this
   because BTC never moved that far during the window. Cannot rule out
   fast pull-and-refresh under real stress.
2. The taker's edge is directional in the underlying, not in the
   barrier per se. If you have a signal that BTC will move 130 bps up
   fast, you take BTC — no barrier hop needed.

### Where a maker would win

A live-priced maker quoting ±5–10 bps around continuous BS fair value
would sit ~0.019 / ~0.021 on 90k YES, versus incumbent 0.01 / 0.03. That
is dramatically tighter. The catch is capacity: 24 h flow on 90k YES/NO
combined is $135 k face, i.e. ~$1.5 / min of paired notional. A 5 bps
capture on that flow is ~$4/day for THE BEST barrier — nowhere near
mission-scale, and the mm-model-spec-2026-09-25 ceiling calculation
already flagged capacity as the hard wall.

The required reprice cadence to survive: at σ = 0.38 the 90k-YES delta
w.r.t. BTC is ~0.0035 per $100 of BTC move. To keep quote error < 0.001
(0.1 of face) you must refresh whenever BTC moves >$30 (~35 bps). At
BTC's observed 200-point / 10-min range that's a mid-single-digit-Hz
reprice cadence when quiet, higher on any real move. Our current 20-min
maker loop is 100× too slow. A 5–10 s reprice loop is trivially in reach
for a Python process; the constraint is order-placement rate limits, not
model compute.

## Sample-size caveats

- 600 s / one window / one time of day (07:56 UTC, low-activity).
- BTC in a 25 bps range — no move large enough to stress the standing MM.
- 4 barriers observed; 2 emitted zero BBO events. Extrapolation across
  underlyings (HYPE barriers were skipped for compute budget) not made.
- HL bbo may still throttle on non-BTC coins; the zero-count barriers could
  be silence-by-quiet-market rather than silence-by-throttle. The 9-count
  and 6-count feeds show throttling is not the binding constraint here.

## Verdict

**NO EDGE for a lag-taker in this 600 s.** Barrier lag is measured in
minutes (median 24.5 s inter-update on the active barrier; max 88.7 s),
which is 500× BTC's BBO cadence — but the standing 0.01 / 0.03 bracket on
90k YES is designed to hold across a full ±1.5 % BTC swing. In-sample BTC
moved 0.25 %. The quote survived by construction, not by luck.

**UNPROVEN as a fair-value MM.** The math (BS fair value in a 0.4-cent
band vs a 2-cent standing spread) says a 5–10 bps quote is
theoretically tighter than incumbent. But the flow is $135 k/24 h for
the best BTC barrier — capacity ~$4–$8 / day at 5 bps capture,
consistent with the `mm-model-spec-2026-09-25` ceiling. Not
mission-scale on its own. Would need aggregation across HYPE + all 6
BTC barrier strikes + faster reprice than 5 s to become material, and
the incumbent MM will not stand still while you erode them.

**Not falsified: barriers may LEAD the underlying on jumps.** All our
lag was measured passively — barrier BBO shuffles a tick on some
internal clock, BTC prints continuously. A separate experiment
subscribing to trades (not bbo) during a real BTC move (>50 bps in
<60 s) is the follow-up. This window had no such move.

## MEASURED.md graft (append to the table on `feat/inplay-guard-pair-maker`)

    | HIP-4 barrier lag (BTC touchpoints) | NO EDGE / UNPROVEN
    | 600s / 5,122 BTC BBO ticks / 0-9 barrier BBO ticks per market
    | 2026-09-28 | barrier BBO cadence 500x slower than underlying, but
    | standing 0.01/0.03 bracket on 90k-YES absorbs the entire ±1.5% BTC
    | range implied by BS at σ=0.38. lag-taker edge zero in this window;
    | fair-value MM edge exists on paper but $135k/24h flow caps daily
    | capture at single-digit dollars per barrier. Reprice must run
    | every ~35 bps of BTC (5-10s under normal vol) to compete; current
    | 20-min maker loop is 100x too slow.
    | research/barrier-lag-2026-09-28.md

## Follow-ups

1. **Rerun during a fast BTC move.** Trigger the collector when BTC 1-min
   |Δ| > 50 bps for 3 consecutive minutes; that's the only condition
   under which lag-taker edge would show up.
2. **Trades-feed variant.** `bbo` misses within-touch trades. Replay HL
   `trades` stream on the 90k barrier and see if trades print at 0.03
   AFTER a BTC rally — that's the direct "picked off" signal.
3. **Book-depth sensitivity.** Standing 0.01/0.03 — is that ONE quote or
   real depth? `l2Book` at higher polling would answer; my 5 s throttle
   couldn't. If depth on the 0.03 ask is $10, the taker edge is dust.
4. **HYPE-perp barrier.** Only 1 HYPE barrier active (`#12090`, target
   100 vs current 89) — should behave identically but volumes and
   reprice cadence may differ. Not measured today.
