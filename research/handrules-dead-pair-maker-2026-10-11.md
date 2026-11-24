# Hand-rules pair maker — still dead, +24h — 2026-10-11

**NO EDGE AVAILABLE. NO NEW DATA. The hand-rules pair maker has placed
ZERO quotes and ZERO fills on `#*` outcome markets since 2026-09-27
19:30 UTC — now 13d 12h. Prior verdict from `handrules-dead-pair-maker-
2026-10-10.md` stands without amendment. n_new since yesterday's report
= 0 fills, 0 quotes, 0 distinct coins.**

## Why this isn't a new report

The quant-researcher cron ran at 07:43 UTC. It is pointed at
`research/QUESTIONS.md`, `MEASURED.md` and `.claude/agents/quant-
researcher.md`, none of which exist on branch `exec/maker-shadow-harness`
(this cron's branch). They live on `feat/inplay-guard-pair-maker`
(stashed as `622201b WIP ...`). This has been the case for twelve
consecutive runs. Writing a twelfth re-slice of the same frozen 38-fill
sample would be noise.

The one shred of truth available tonight — "has anything changed on the
maker in the last 24h?" — is a one-command check. It has not.

## Delta vs 2026-10-10 report

| metric | 10-10 07:44 UTC | 10-11 07:43 UTC | Δ |
|---|---|---|---|
| hours since last `maker_quote` | 298.9 | 322.8 | +23.9 (= wall-clock) |
| hours since last `#*` `own_fill` | 300.3 | 324.2 | +23.9 (= wall-clock) |
| coin targeted in last 24h | `#45160` only | `#45160` only | — |
| 24h start→stop cycles | 3,985 | 4,049 | +64 (same ~22s period) |
| 24h `maker_quote` events | 0 | 0 | — |
| 24h `own_fill` events on `#*` | 0 | 0 | — |
| distinct `#*` coins quoted since 09-27 | 0 | 0 | — |

Reproduction identical to the 10-10 report; same code block, run on
`state/journal.jsonl` (mtime 2026-10-11 07:44 UTC, 55 MB, writes current).

## What this means

- **The loop is real, the engine is wedged, nothing changed.** 23.9h of
  wall-clock elapsed. 23.9h of maker-dead time followed. 100 % of 24h
  `maker_start` events still land on `#45160` (settled 2026-10-01 00:00
  UTC, 10d 7h ago). Not a sampling fluke.
- **The 38-fill pure-maker sample is still frozen.** `handrules-baseline`
  (10-06), `handrules-stratified` (10-07), `stop-loss-signal` (10-08),
  `handrules-face-exante` (10-09), `handrules-dead-pair-maker` (10-10)
  all draw on it. A sixth re-slice tonight is five-days-worth of nothing.
- **Standing capital is idle, not exposed.** No action required on PnL.
  The copy-trade bots and systemd workers are separate — this report
  only speaks to the hand-rules pair maker.

## What I did NOT do tonight

- Did not re-fit any filter (face-cap, stop-loss, hold-time) on the
  frozen 38-fill sample.
- Did not touch `src/` or `config.yaml` — read-only researcher.
- Did not restart or kick the maker — out of scope for this role.
- Did not open the shadow harness — `0 of 470,867 shadow_* events`
  continues to mean the plumbing is not emitting.

## What would change this verdict

Exactly one thing: the engine resumes quoting a non-expired `#*`
surface and the fill count exceeds 38. Until then every report writes
the same words.

## For the operator (unchanged ask, now stated 13th time)

1. Decide whether the hand-rules pair maker is a live strategy. If yes:
   the surface-selection path is pinned to `#45160` and blind to
   `expiry_ts`. Three candidates in yesterday's report; the operator
   has to read code, a researcher cannot pick between them from the
   journal.
2. Three lines of shadow-harness plumbing so the next replacement model
   can be measured without live capital at n=0.
3. Point the quant-researcher cron at the branch that contains
   `research/QUESTIONS.md` + `MEASURED.md` + the agent brief — OR —
   merge those three files onto `exec/maker-shadow-harness` and mark
   #0a (real MM model) as ANSWERED (spec was delivered
   2026-09-25 in `research/mm-model-spec-2026-09-25.md`).

## Verdict (appendable wherever MEASURED.md eventually lives)

> **Hand-rules pair-maker liveness (2026-10-11, 24h re-check, n_new=0).**
> NO NEW EDGE AVAILABLE. 24h after the 10-10 report flagged the engine
> wedged on settled surface `#45160`, the state is identical: 4,049
> start→cancel→stop cycles in the last 24h, zero quotes, zero fills, one
> coin, one still-settled expiry. The 38-fill pure-maker sample used by
> all five preceding `handrules-*` and `stop-loss-signal` reports has
> not grown. Every filter proposed on that sample remains unprovable.
> Cron is still writing to the wrong branch; `research/QUESTIONS.md` and
> `MEASURED.md` do not exist on `exec/maker-shadow-harness`.

## Reproducing (same as 10-10, re-stated for standalone)

```
cd /home/ec2-user/.openclaw/workspace/hyper-trader
.venv/bin/python - <<'PY'
import json, time
from collections import Counter
now = time.time()
last_q = last_f = None
cycles = Counter(); coin_24h = Counter()
for L in open('state/journal.jsonl'):
    try: e = json.loads(L)
    except: continue
    ev = e.get('event',''); ts = e.get('ts',0)
    if ev == 'maker_quote': last_q = e
    if ev == 'own_fill' and e.get('coin','').startswith('#'): last_f = e
    if ts > now - 86400 and ev in ('maker_start','maker_stop','maker_quote','maker_cancel_all'):
        cycles[ev] += 1
        if ev == 'maker_start': coin_24h[e.get('coin','')] += 1
print(f"last_maker_quote    {(now-last_q['ts'])/3600:.1f}h ago on {last_q['coin']}")
print(f"last_outcome_fill   {(now-last_f['ts'])/3600:.1f}h ago on {last_f['coin']}")
print(f"24h cycles          {dict(cycles)}")
print(f"24h start by coin   {dict(coin_24h)}")
PY
```

Expected on 2026-10-11 07:43 UTC:

```
last_maker_quote    322.8h ago on #45160
last_outcome_fill   324.2h ago on #45150
24h cycles          {'maker_start': 4049, 'maker_cancel_all': 4049, 'maker_stop': 4049}
24h start by coin   {'#45160': 4049}
```
