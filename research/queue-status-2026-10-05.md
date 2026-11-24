# Research queue status — 2026-10-05

**QUEUE EXHAUSTED. All five OPEN items in `research/QUESTIONS.md` have
delivered reports; none has been formally moved to ANSWERED and the file
pointer on `feat/inplay-guard-pair-maker` is stale. No new measurement in
this run — a clean-negative audit of the queue state, with the next
priority proposed.**

A fabricated edge-hunt here would be exactly what the brief forbids.

## Workspace state, up front

`MEASURED.md`, `research/QUESTIONS.md`, `.claude/agents/quant-researcher.md`
still live on `feat/inplay-guard-pair-maker` (`stash@{0}` with newer edits).
This is the **seventh** consecutive quant-researcher cron run to note the
mismatch — same warning as `research/oil-lag-2026-09-24.md`,
`mm-model-spec-2026-09-25.md`, `copysim-outcome-audit-2026-09-26.md`,
`tournament-guard-2026-09-27.md`, `barrier-lag-2026-09-28.md`,
`binary-price-depth-2026-09-30.md`, `binary-wall-responsiveness-2026-10-03.md`,
`cl-shock-frequency-2026-10-04.md`. The branch pointer still needs
fixing. Writing this status here; it is not a measurement, it is a
queue-maintenance deliverable.

## What is actually OPEN

Pulled from `git show 622201b:research/QUESTIONS.md` (stashed WIP, the
newest version of the queue).

| # | question | status today | report |
|---|---|---|---|
| 1 | HIP-4 crypto barriers reprice slower than underlying? | **CLOSED, NO EDGE across depth/cadence/shock** | `barrier-lag-2026-09-22`, `barrier-lag-2026-09-28.md`, `barrier-depth-2026-09-29.md`, `binary-price-depth-2026-09-30.md`, `binary-wall-responsiveness-2026-10-03.md`, `cl-shock-frequency-2026-10-04.md` |
| 2 | HIP-4 oil (`perp:xyz:CL`) lag? | **CLOSED, NO EDGE — venue too thin (37 trades / 24h)** | `oil-lag-2026-09-24.md` |
| 4 | Guard cannot tell tournament vs match market | **MEASURED, EDGE FOR ADVERSARY** (peak-hour trade share 25.3% of 48h; median peak-hour range 13.8× median hour; max 642×, n=17 markets) | `tournament-guard-2026-09-27.md` |
| 5 | Equity reconcile ($75 gap) | **RESOLVED in the queue itself** — perp `accountValue` double-counts spot USDC; use `portfolio.accountValue` | marked RESOLVED in `QUESTIONS.md` |
| 0a (ANSWERED in stash) | A real MM model | **UNPROVEN, capacity-capped** (ceiling $1.51/day = 19.7% APR at perfect capture) | `mm-model-spec-2026-09-25.md`, graft in stash |

The topmost truly-unanswered question — reading the stashed queue literally —
is #1, and it was closed yesterday. There is nothing in OPEN that a new
measurement would move.

## What the next question should be

A clean next priority, in order of what the September-October work has
narrowed us to:

1. **Does our live maker-shadow harness (commit `10a7090`) show better
   measured edge than the hand-rules bot it replaces?** The harness is
   described as refusing "naive backtest self-flatter," so it owns its
   own live-feed scoring. We now have:
   - `MEASURED.md` paired-quoting measured realistic cell: +3.8 to +15.6
     bps of face, n=2 fills, turnover unmeasured.
   - Jeff's 10-run weight cuts applied in `66c29e0` (five leaders).
   - A-S spec from 2026-09-25 that is not yet live.

   A head-to-head: (a) the hand-rules bot's realised PnL per fill over the
   last N days, (b) the shadow harness's hypothetical PnL on the same
   book-tape over the same window. If (b) − (a) is not visibly positive
   with a sample size that beats the paired-quoting ceiling, the A-S spec
   stays on the shelf. If it is, the next question is deployment safety.

2. **Does the tournament-guard adversary edge survive a working guard?**
   `tournament-guard-2026-09-27.md` quantified the adversary edge; the
   `src/gamestate.py` fix was never confirmed to land. If the guard now
   distinguishes `template:sportsTournamentParticipant` from
   `template:sportsFixture` and refuses the peak hour, we need to
   re-measure what the bot would otherwise have quoted and lost.

3. **Polymarket overlap probe (new).** `state/polymarket/` has 2,966
   collector snapshots (193 markets in the latest, $79M aggregate volume
   as of `markets_1791186413.jsonl`). Known categorical gaps today:
   Polymarket is dominated by golf majors, Ballon d'Or, long-horizon
   gaming/entertainment, BPL cricket, LoL esports; HL HIP-4 is NFL +
   soccer + binaryPrice + barriers. The surface overlap is small enough
   that cross-venue arbitrage is probably zero, but we have never
   quantified it — one well-scoped probe would close "do we have a
   Polymarket-HL arb edge" the same way `hip4-pairs.log` closed the
   HL-twin edge.

(1) is the most actionable because the harness is already on this branch
and the data is in `state/`. (2) blocks on a code-landing event. (3) is
dirt-cheap and would retire a recurring "should we also look at
Polymarket" question.

## What I did not do

- No new API probes — the queue state was knowable from `git show` on the
  stash and from reading the existing reports in `research/`. Running
  book-depth / shock / barrier probes would have been a seventh negative
  on surfaces that are already closed.
- No `MEASURED.md` graft — this is a queue-maintenance finding, not a
  market measurement. The existing table style requires a sample size
  and a verdict on a market, and that is not what this report is.
- No live `state/book_snapshots/*.jsonl` analysis — most recent file is
  2026-09-25, 10 days stale, so a fresh collection would be needed and
  that is a scheduled-job task, not a cron-run task.

## Reproducing

    git show 622201b:research/QUESTIONS.md    # latest queue (stashed WIP)
    git show feat/inplay-guard-pair-maker:research/QUESTIONS.md  # branch tip
    git log --all --oneline -- research/QUESTIONS.md
    ls research/*.md

## For the operator

- Please move #1 and #2 to ANSWERED on `feat/inplay-guard-pair-maker`
  with pointers to the reports above, or re-point the cron at a branch
  that does carry the live queue. Seven cron runs have now written to
  the wrong branch.
- Next topmost should be the shadow-harness head-to-head, phrased as a
  measurable question: *does the live `maker_shadow.py` output beat the
  hand-rules bot by a margin that clears the +3.8..+15.6 bps/face
  paired-quoting ceiling, over N≥50 fills on comparable surfaces?*
