# Hand-rules pair maker has been dead for 12 days — 2026-10-10

**NO NEW EDGE AVAILABLE. The hand-rules pair maker has placed ZERO quotes
and ZERO fills on `#*` outcome markets since 2026-09-27 19:30 UTC — 12d 12h.
The last four `handrules-*` reports (10-06..10-09) have been re-slicing a
frozen 38-fill sample from 09-19..09-27 while the live engine loops
start→shutdown→stop every ~20 s on an expired surface. n_new=0.**

## Why this question wins the queue tonight

QUESTIONS.md still names #0a (a real MM model, cite A-S/GLFT/Hummingbot) as
topmost. That was delivered on 2026-09-25 as `research/mm-model-spec-2026-09-25.md`
and never moved to ANSWERED. The eight open-question reports since then
have drifted onto hand-rules diagnostics (`stop-loss`, `face-exante`,
`stratified`) under the assumption that new fills are accruing at ~2/day.
Before another re-slice of that sample, verify the sample is still growing.
It is not.

## What I measured

`state/journal.jsonl` (470,867 events, read-only, no exchange calls).

Last events for the hand-rules maker:

| event | ts (UTC) | coin | notes |
|---|---|---|---|
| last `maker_quote` on any coin | 2026-09-27 20:54:42 | `#45160` | 298.9 h ago |
| last `own_fill` on any `#*` coin | 2026-09-27 19:30:06 | `#45150` | 300.3 h ago |
| last `shadow_*` event ever | — | — | 0 of 470,867 events |

Last 24 h on `state/journal.jsonl`:

```
maker_start      3,985
maker_cancel_all 3,985   reason=shutdown
maker_stop       3,985   inventory_shares=0.0
maker_quote      0
own_fill (#*)    0
```

All 3,985 start/stop cycles target one coin: `#45160`, `expiry_ts =
1790812800 = 2026-10-01 00:00:00 UTC`. The surface **settled 9d 7h before
this run**. Every ~20 s the maker initialises, immediately cancels with
`reason=shutdown`, stops with `inventory_shares=0.0`, and the next tick
starts the same cycle again. 32,432 cycles since 2026-10-01, zero on any
other coin.

`own_fill` on `#*` per day since 09-19:

```
2026-09-19   6
2026-09-20  11
2026-09-21  45
2026-09-22  43
2026-09-23  47
2026-09-24  25
2026-09-25  10
2026-09-27   8      <- last day with any outcome fill
```

## What this means for the recent optimisation thread

- `handrules-baseline-2026-10-06.md`, `handrules-stratified-2026-10-07.md`,
  `stop-loss-signal-2026-10-08.md`, `handrules-face-exante-2026-10-09.md`
  all draw on **the same 38-fill pure-maker sample**. That sample closed on
  2026-09-27 and has not grown since. Four reports, one dataset, zero new
  evidence.
- The 10-08 stop-loss result (+207 bps blended, catches `#30140`) and 10-09
  face-cap result (+241 bps blended, drops 4/38 fills) are not confirmable
  without new fills. Each additional slice shrinks the degrees of freedom.
  At n=38 and one dominant loss trade (`#30140`, −$24.23 of −$10.04
  blended), any ex-post filter looks explanatory.
- The 10-09 report said "wait for n=100 pure-maker closes at current pace
  (~2 per day)" — current pace is **zero per day**, has been for 12 days,
  and would need the maker to actually quote. That expectation was already
  wrong when it was written.
- Shadow harness: 0 events in 470,867. The last ten reports' "topmost
  blocker" ask (three lines of plumbing to emit `shadow_quote`/`shadow_fill`)
  has not been actioned. Eleventh run saying the same thing is noise.

## The bug underneath (quant-adjacent, flagged not fixed)

Something in the maker's surface-selection path is pinned to `#45160` and
blind to its expiry. 32,432 start attempts on a settled surface in 9 days,
no attempt on any newer `#*` market, no `no_quote_target` events during
that window. Candidates (I did not read the code — this is for the operator
and `sally-agent`):

1. The maker reads `expiry_ts` once at process start and does not re-check
   when `now > expiry_ts`. Settle happens, book disappears, start cycle
   produces an immediate shutdown.
2. Surface-selection cache was written on 2026-09-27 and never invalidated.
3. The pair-maker's cron is passing a hard-coded `--coin #45160` after some
   09-27 manual intervention.

Any of these produces the exact "start → shutdown → stop, every 20 s"
signature we see. The operator should decide; a researcher cannot tell
from the journal alone which of the three it is.

## What I assumed

- The journal is complete for maker lifecycle events. Verified: the 36,165
  `maker_start` events on `#45160` match 36,162 `maker_cancel_all shutdown`
  events (3 missing, within normal process-exit tolerance).
- `own_fill` with `coin.startswith('#')` captures all hand-rules fills.
  Same scope as the 10-07..10-09 reports; if that scope was wrong there,
  it is wrong here, but the ratio (0 new vs frozen 38) is unaffected.
- `expiry_ts = 1790812800` is seconds-since-epoch UTC. Confirmed:
  `datetime.utcfromtimestamp(1790812800) → 2026-10-01 00:00:00`.

If the engine is actually quoting but the journal writes are failing, this
whole finding reverses. Journal is 55 MB and timestamped through 07:44 UTC
this morning, with 3,985 maker lifecycle entries in the last 24 h, so I do
not believe write-failure is live.

## What I could not determine

- Whether the engine process itself is healthy (would need
  `systemctl status hyper-trader` — out of scope for a read-only researcher).
- Whether the expired-surface loop is a quoting-side bug or a
  surface-selection-side bug. Needs code read, not journal read.
- The post-09-27 shadow-harness status. Zero events may mean the harness
  never started, or started and no code path emits — either way, no
  measurable output.

## What it would take to resolve

1. **Decide whether the hand-rules pair maker is still a live strategy.**
   If yes, fix the expired-surface loop and the surface-selection path,
   and the sample starts growing again. If no, close the thread and stop
   paying cron-time to re-slice it.
2. **Three lines of shadow-harness plumbing** (same ask, eleventh report).
   Without it, the only way to measure a replacement model is to deploy
   capital against it, which neither the operator nor the researcher wants
   at n=0.
3. **Move `MEASURED.md`, `research/QUESTIONS.md`,
   `.claude/agents/quant-researcher.md` from `feat/inplay-guard-pair-maker`
   to the branch this cron runs on, or point the cron at that branch.**
   Eleventh run writing to the wrong branch. Also mark #0a as ANSWERED
   while there — the spec exists.

## Verdict appendable to MEASURED.md

> **Hand-rules pair-maker liveness (2026-10-10, n=0 new fills).** NO NEW
> EDGE AVAILABLE. The hand-rules pair maker last quoted on 2026-09-27
> 20:54 UTC and last filled on 2026-09-27 19:30 UTC. Since 2026-10-01 it
> has run 32,432 start→shutdown→stop cycles on `#45160`, an outcome
> surface that settled on 2026-10-01 00:00 UTC. All four `handrules-*`
> optimisation reports between 10-06 and 10-09 share one 38-fill sample
> that has not grown. Any filter proposed on that sample (face-cap, stop-
> loss, hold-time) is unprovable without the engine resuming quotes.

## For the operator

- Live-trading implication: no action needed on P&L — the bot has traded
  zero outcome markets in 12 days. Standing capital is idle, not exposed.
- The surface-selection expired-market loop is a `sally-agent` /
  `INVARIANTS.md` candidate: a strategy that bills 32k wake-ups a day
  against a settled instrument is a silent kill switch in reverse (never
  acts, never errors, never notices).
- If the pair-maker thread is dead by design, note it in `MEASURED.md`
  and close the shadow-harness ask with it.
- Topmost unanswered question is now effectively `#1` (barrier lag), which
  was partially addressed in `barrier-depth-2026-09-29.md` /
  `binary-price-depth-2026-09-30.md` / `cl-shock-frequency-2026-10-04.md`.
  QUESTIONS.md needs a pass.

## Reproducing

```
cd /home/ec2-user/.openclaw/workspace/hyper-trader
.venv/bin/python - <<'PY'
import json, time
from collections import Counter
now = time.time()
last_q = last_f = None
cycles = Counter()
for L in open('state/journal.jsonl'):
    try: e = json.loads(L)
    except: continue
    ev = e.get('event','')
    if ev == 'maker_quote': last_q = e
    if ev == 'own_fill' and e.get('coin','').startswith('#'): last_f = e
    if e.get('ts',0) > now - 86400 and ev in ('maker_start','maker_stop','maker_quote'):
        cycles[ev] += 1
print(f"last_maker_quote    {(now-last_q['ts'])/3600:.1f}h ago on {last_q['coin']}")
print(f"last_outcome_fill   {(now-last_f['ts'])/3600:.1f}h ago on {last_f['coin']}")
print(f"24h cycles          {dict(cycles)}")
PY
```

Expected on 2026-10-10 07:44 UTC:

```
last_maker_quote    298.9h ago on #45160
last_outcome_fill   300.3h ago on #45150
24h cycles          {'maker_start': 3985, 'maker_stop': 3985}   # maker_quote: 0
```
