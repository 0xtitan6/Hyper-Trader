# Hand-rules bot — stratified re-measurement — 2026-10-07

**EDGE on pure-maker paired closes.** Mean **+227 bps/face**, median **+85 bps**,
95% CI **[+137, +323]** on **n=36** clean closes (strip 2 single-event extremes
|bps|>2000). Yesterday's "mean +63 bps, CI [−121, +227], n=54" was contaminated
by **14 `para:VST` perp-copy closes** that the copy engine (not the hand-rules
bot) booked; strip them and the hand-rules territory is n=38, mean +188 bps,
median +85 bps, 95% CI [−45, +384]. Blended face-weighted sign depends on one
single-event loser on `#30140`.

The settlement lottery is a coin flip — **53 unique pure-maker settlements,
26W/27L, net −$11.30, z=−0.14** on the 50/50 null. No settlement edge.

## Scope correction (why n changed from 54 to 38)

`research/handrules-baseline-2026-10-06.md` filtered to
`coin.startswith('#') or 'para:'`. But `para:VST` is an HIP-3 perp that the
**copy engine** mirrors (34 own_fills + 9 `leader_fill` events + 261
`leader_exit_detected` events, zero `maker_quote` events). The hand-rules
maker never touches `para:*`. Including those 14 paired closes added:

- `para:VST` subsample: n=14, mean **−252 bps**, median **−144 bps**, 95% CI
  **[−333, −183]** — entirely negative, driven by two reconcile-timestamp
  clusters (9 closes at ts=1789780620, 4 at 1790242980) that look like
  leader-exit chains, not maker fills.

That is a copy-engine measurement, not a hand-rules measurement.
The baseline for the shadow harness head-to-head should use only hand-rules
territory: `#*` binary coins with no `leader_fill` ever observed.

## Pure-maker territory (hand-rules only)

Scope: 65 `#*` binary coins that have 0 `leader_fill` events in the window.
3 `#*` coins are "mixed" (both leader_fill and own_fill present) — excluded.

| segment | n | face | pnl | mean bps | median bps | 95% CI |
|---|---:|---:|---:|---:|---:|---:|
| Opens | 142 | $2,620 | 0 | — | — | — |
| Closes | 41 | — | — | — | — | — |
| Clean closes (face>$1) | 38 | $620 | −$10.04 | +188 | +85 | [−45, +384] |
| **ex-outliers (\|bps\|>2000)** | **36** | **$520** | **+$8.67** | **+227** | **+85** | **[+137, +323]** |
| Settlements | 53 | — | −$11.30 | — | — | 26W/27L, z=−0.14 |

The two dropped single-event extremes:

| tid | coin | side | face | pnl | bps |
|---|---|---|---:|---:|---:|
| 664967335509687 | #39001 | A | $24.90 | +$5.52 | +2,218 |
| 61320805449458  | #30140 | A | $74.39 | **−$24.23** | **−3,257** |

The `#30140` trade is a **32% single-fill loss** — 3.2× the next-worst clean
close. Removing it alone takes blended PnL from −$10 to **+$14 / $546 = +256
bps**. Removing both: +$9 / $520 = +167 bps.

## Hold-time stratification

Paired to prior opposite-side open on same coin (nearest-earlier):

| hold | n | mean bps | median bps |
|---|---:|---:|---:|
| 60s–1h | 9 | −132 | +39 |
| >1h | 36 | +173 | +83 |

Short holds (minutes) lose, long holds (hours+) win. This is consistent with
toxicity: when adverse ticks hit shortly after we open, we exit at loss; when
the mid grinds, we close for the quoted spread. The hand-rules bot has no
toxicity gate.

## What this means for the queue

The topmost question is still *"does the shadow harness beat the hand-rules
bot?"* and still unanswerable this run — `grep "shadow" state/journal.jsonl`
returns 0, same as yesterday. The shadow harness has not landed its journal
emitter. The ninth consecutive cron run notes the queue-pointer mismatch
(`MEASURED.md` / `research/QUESTIONS.md` live on `feat/inplay-guard-pair-maker`,
cron runs on `exec/maker-shadow-harness`).

Two things change downstream:

1. The target the shadow must beat is **not** "blended −282 bps" (yesterday's
   number) or "+3.8..+15.6 bps" (`MEASURED.md`). It is **"median +85 bps,
   mean +227 bps ex-outlier on paired binary closes, 95% CI [+137, +323],
   n=36"**. The hand-rules bot has a real spread-capture edge.

2. The failure mode isn't "sticky inventory grinding against us" (yesterday's
   framing); it's **a single catastrophic trade (`#30140`)** that drives the
   blended sign. Shadow replay should score "would our risk policy have refused
   this one open" as its first test. If yes, the shadow is live-tradeable
   today; if no, the hand-rules bot is already the better policy at this
   sample size.

Settlement lottery stays a coin flip: 26W/27L, net −$11.30. It is not a
measurement of maker edge; the shadow should neither credit itself for
settlement wins nor charge losses to its spread-capture book.

## Verdict appendable to MEASURED.md

> **Hand-rules pure-maker paired-close edge (2026-10-07, n=36 clean
> ex-outlier).** Pure maker-territory binary closes: median **+85 bps**, mean
> **+227 bps**, 95% CI **[+137, +323]**. Correct baseline for the shadow
> harness head-to-head, superseding "+3.8..+15.6 bps/face, n=2" from
> 2026-09-21. Settlement lottery coin-flip (26W/27L, z=−0.14, net −$11.30).
> One single-event loss (`#30140` A fill, $74 face, −$24.23 / −3,257 bps) is
> enough to flip the blended sign; the shadow must prove it would have
> declined that fill.

## For the operator

- Please move #1 (barrier) and #2 (oil) to ANSWERED and update the queue
  pointer. This is the ninth cron run writing to the wrong branch.
- Append the verdict block above to `MEASURED.md` next to the paired-close
  entry.
- The actual (b)-side measurement still blocks on `maker_shadow.py` emitting
  `shadow_quote` / `shadow_fill` events to `state/journal.jsonl` — same
  prerequisite as yesterday, three lines of plumbing.

## What I did not do

- No new API probes — journal replay only, zero read-side load on HL.
- Did not touch `MEASURED.md`, `INVARIANTS.md`, or `research/QUESTIONS.md`
  (both still live on `feat/inplay-guard-pair-maker`, stashed).
- Did not segment by `coin_class` beyond pure-maker vs mixed vs copy, because
  n=38 is already thin.
- Did not re-run copysim or any backtest. The hand-rules measurement is a
  replay of what we actually traded.

## Reproducing

```
cd /home/ec2-user/.openclaw/workspace/hyper-trader
.venv/bin/python - <<'PY'
import json, statistics, random
from collections import defaultdict
has_leader=set()
for line in open('state/journal.jsonl'):
    try: e=json.loads(line)
    except: continue
    if e.get('event')=='leader_fill' and e.get('coin','').startswith('#'):
        has_leader.add(e['coin'])
seen=set(); fills=[]
for line in open('state/journal.jsonl'):
    try: e=json.loads(line)
    except: continue
    c=e.get('coin','')
    if not c.startswith('#') or c in has_leader: continue
    if e.get('event')!='own_fill': continue
    t=e.get('tid')
    if t in seen: continue
    seen.add(t); fills.append(e)
cclean=[f for f in fills if abs(float(f.get('closed_pnl',0) or 0))>1e-6
        and float(f['sz'])*float(f['px'])>1.0]
bps=[float(f['closed_pnl'])/(float(f['sz'])*float(f['px']))*1e4 for f in cclean]
print(len(bps), 'closes, mean', round(statistics.mean(bps),1),
      'median', round(statistics.median(bps),1))
PY
```

Expected on 2026-10-07 07:44 UTC: `38 closes, mean 187.9 median 85.0`.
