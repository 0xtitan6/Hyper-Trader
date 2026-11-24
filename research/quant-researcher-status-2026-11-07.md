# Quant-researcher cron status — 2026-11-07

**NO EDGE TO MEASURE. The queue has been stale since 2026-09-23; 38 distinct
report-dates produced across 44 days, 0 of them committed to any branch.
This run is operational-only, same verdict as `queue-status-2026-10-05.md`.**

A fabricated measurement here is exactly what the brief forbids. The honest
delta since 10-05 is the elapsed time and the count, not a new finding.

## State, measured now

- Current HEAD: `main` @ `191d9b8`, written 2026-10-18.
- `MEASURED.md`, `research/QUESTIONS.md`, `.claude/agents/quant-researcher.md`
  live on `feat/inplay-guard-pair-maker` (tip `137f50d`, 2026-09-22) and
  `stash@{1}` (`622201b`, 2026-09-23). None of the three files exist on `main`.
- Reports written since the mismatch was first flagged: **38 distinct
  date-stamped files under `research/`**, all untracked, none committed to
  `main`, `feat/inplay-guard-pair-maker`, or any other branch
  (`git log --all --oneline -- research/<file>.md` returns empty for every
  sampled 10/11-dated file).
- Queue items on branch: five OPEN, all with delivered reports listed in
  `queue-status-2026-10-05.md`. None moved to ANSWERED since.
- `state/polymarket/` is 7 months stale (latest `ts=1794037458` ≈ Mar 2026),
  so the "Polymarket overlap" candidate from 10-05's next-priority list
  cannot be worked without a fresh collection first.

## What needs to happen before this cron does useful work again

One of:

1. Merge `stash@{1}` and `feat/inplay-guard-pair-maker`'s queue files to
   `main` (or wherever the cron checks out), and move items #1, #2, #4, #5,
   and 0a to ANSWERED with pointers to the reports already on disk.
2. Point the cron at a worktree checked out on the strategy branch.
3. Retire this cron and replace it with a tighter prompt that writes
   against the live `handrules-*` / `outcome-maker-*` / leader-flow research
   path that the last 30 days of untracked reports have actually been on.

Any of the three closes the gap. Doing none of them again produces another
stranded report next cron.

## Why no measurement this run

- The topmost item (0a, MM model) has a spec dated 2026-09-25. Converting
  spec → number requires a live shadow run or a backtest against order-book
  tape, not an afternoon of API probes. `handrules-*` and `outcome-maker-*`
  series appear to be doing exactly that, outside this cron.
- Items #1 and #2 (barrier/oil lag) are CLOSED-NO-EDGE with n in the tens of
  thousands of polls; re-measuring would be the eighth negative on a dead
  surface.
- Item #4 (tournament guard) blocks on a code-landing event, not a
  measurement.
- Item #5 (equity reconcile) was resolved inside the queue file itself.

A new probe would be busywork, and three cron runs ago it would have been
the fifth busywork probe in a row.

## Reproducing

    git log --all --oneline -- research/mm-model-spec-2026-09-25.md   # empty
    git ls-files --others --exclude-standard research/*.md | wc -l     # 39
    git ls-files --others --exclude-standard research/*.md \
      | grep -oE '2026-[0-9]{2}-[0-9]{2}' | sort -u | wc -l            # 38
    git show stash@{1}:research/QUESTIONS.md                           # live queue
    git show feat/inplay-guard-pair-maker:MEASURED.md                   # ledger

## For the operator

This is the 15th+ cron run against the same branch mismatch. If the next one
is also a no-op, please do (1), (2), or (3) above. No new findings until
then; this file exists only so the pattern is visible in one place at the
most recent date.
