# Hand-rules bot realised baseline — 2026-10-06

**NO EDGE in blended wallet terms. +$50.71 net over 16.5 days / 229 fills /
$4,635.82 face = +109 bps face, +$3.07/day. The entire positive sign comes
from two lucky binary settlements (+$327 on #41610 and #46521 — 356% of total
settlement PnL from 2 lotteries); strip those and the window is −$276.
Paired-close edge is MEASURED but statistically indistinguishable from zero:
mean +62.7 bps, bootstrap 95% CI [−121, +227], n=54.**

The queue priority proposed in `queue-status-2026-10-05.md` was *"does the
shadow harness beat the hand-rules bot by a margin that clears the
+3.8..+15.6 bps/face paired-quoting ceiling, over N≥50 fills on comparable
surfaces?"* The ceiling itself was the n=2 estimate in `MEASURED.md`. The
shadow isn't logging to `state/journal.jsonl` yet so the head-to-head is
unanswerable this run, but the (a) side — the live hand-rules PnL the shadow
has to beat — is now measured at n=54 close-cycles and the ceiling is wrong:
real paired closes see median +50 bps but mean/CI tells the fat left tail is
real.

## Method

`state/journal.jsonl` 2026-09-19 01:17 UTC → 2026-10-06 07:44 UTC
(16.5 days, 417,385 lines). Filtered to `coin.startswith('#')` or `'para:'`,
deduplicated `own_fill`/`settlement` by `tid` to collapse snapshot repeats
(each settlement is written on every reconcile until the market disappears —
#45250 had 90 identical rows). Split `own_fill` by `|closed_pnl|<1e-6` into
opens vs closes. "Face" = `sz × px` of the fill itself.

Confounders ruled in:
- **Snapshot inflation**: deduped by `tid`, verified 56 unique settlements vs
  hundreds of repeats. Without dedup the settlement PnL would be ×6-×90.
- **Mixed is_snapshot=true opens from pre-window inventory**: 171 opens
  include some pre-Sep-19 standing inventory (first fills show
  is_snapshot:true at ts=1789780635). Including them is conservative because
  it credits the window with closes against baskets it did not open.
- **Micro-face reduces produce absurd bps**: four tids closed `sz × px < $0.20`
  with closed_pnl of −$1 to −$3.6 (settlement remainders), inflating the raw
  mean to −18,943 bps. Filter: `face > $1`, giving n=54 clean paired closes.

## Numbers

| segment | n | face | PnL | bps/face |
|---|---:|---:|---:|---:|
| Opens | 171 | $3,182.85 | 0 (by defn) | — |
| Closes (paired) | 58 | $1,452.97 | −$40.94 | **−282 blended** |
| Closes, face>$1 | 54 | — | — | **mean +63, median +50, 95%CI [−121, +227]** |
| Settlements | 56 | — | +$91.65 | 29W / 27L, p=51.8%, 2-sided p=0.79 |
| Top 2 settle wins | 2 | — | +$326.73 | 356% of total settle PnL |
| **Blended wallet** | **229** | **$4,635.82** | **+$50.71** | **+109 bps / +$3.07/day** |

The paired-close distribution is right-skewed: 68.5% positive, median +50 bps,
but the mean's left-tail destroys it — a few opens get stuck and reduce at the
worst tick. Bootstrap 2000x on the n=54 clean sample puts the 95% CI squarely
on both sides of zero.

Settlement lottery: 54.3% of opened face (by $) was never closed by another
fill and went to binary settlement. 29W/27L is one standard deviation off
50/50; z=+0.27. The +$92 settlement PnL is driven by two single-market wins
(+$199.89 on #41610, +$126.84 on #46521) that offset the five biggest losers
(−$478 combined). This is not a measurement of maker edge, it is 56 pulls of
a coin-flip arm.

Biggest contributors on the dollar side:

```
settlement WINNERS                 settlement LOSERS
#41610  +199.89 (soccer)           #46520  −128.94
#46521  +126.84                    #46620   −99.91
#44710   +94.38                    #44711   −93.16
#46490   +77.21                    #44851   −86.71
#45140   +68.16                    #42950   −69.33
```

## Implication for the shadow-harness head-to-head

The ceiling in `MEASURED.md` ("+3.8..+15.6 bps of face, n=2 fills, turnover
unmeasured") was too high AND measured on too few samples:

- real **median paired-close** is +50 bps (10× the lower ceiling) — the
  spread is being captured when a close happens
- real **mean paired-close** is +63 bps with wide 95% CI including large
  negatives — adverse selection is real
- real **blended per-dollar-face** is +109 bps BUT 54% of face is
  unpaired/settlement variance

Therefore the correct bar for the shadow harness is NOT "beat +15.6 bps/face
on a paired fill". It is **"close more than 46% of opened face at better than
−282 bps blended"** — i.e. shrink the unpaired-tail. If the shadow lets a
larger fraction of inventory time-decay into settlement without a hedge, the
median-vs-mean gap stays destructive regardless of per-close edge.

Prerequisite before (b): the shadow harness has to actually emit events to
`state/journal.jsonl`. `grep "shadow" state/journal.jsonl` returned 0. I did
not read `src/maker_shadow.py` beyond the class signatures — it defines
`ShadowSimulator.report() -> dict` but no journal emitter.

## For the queue

- The `MEASURED.md` paired-quoting ceiling needs to be rewritten to the
  n=54 numbers above (median +50 bps / mean +63 bps / 95% CI [−121, +227]).
  I did not graft it myself because the queue still lives on
  `feat/inplay-guard-pair-maker` and this is the 8th consecutive cron run
  on a stale pointer; writing to `exec/maker-shadow-harness`-local
  `MEASURED.md` would fork the ledger. Please merge the queue onto this
  branch, or point the cron at the branch that carries the queue.
- The actual shadow-vs-live head-to-head needs `maker_shadow.py` to log
  `shadow_quote`/`shadow_fill` events to `state/journal.jsonl`. Right now
  it only exposes `.report()` in-memory, which dies with the process.
  Suggest a `--journal` flag that routes `ShadowSimulator` fills through
  the same `journal.emit(...)` call `maker.py` already uses — three lines
  of plumbing, no new data pipeline needed.

## Reproducing

```
cd /home/ec2-user/.openclaw/workspace/hyper-trader
.venv/bin/python -c "
import json; from collections import defaultdict
seen=set(); fills=[]; settles={}
for line in open('state/journal.jsonl'):
    e=json.loads(line); c=e.get('coin','')
    if not (c.startswith('#') or c.startswith('para:')): continue
    if e.get('event')=='own_fill':
        t=e['tid']
        if t in seen: continue
        seen.add(t); fills.append(e)
    elif e.get('event')=='settlement':
        settles.setdefault(e['tid'], e)
print(len(fills), 'fills,', len(settles), 'settlements')
"
```

Expected on 2026-10-06 07:44 UTC: `229 fills, 56 settlements`.

## What I did not do

- No new API probes — journal replay only, zero read-side load on HL.
- Did not touch `MEASURED.md`, `INVARIANTS.md`, or `research/QUESTIONS.md`.
- Did not read `maker_shadow.py` end-to-end, only class signatures. The
  prerequisite I named (route shadow fills through `journal.emit`) is a
  recommendation to the executor, not a verified diff.
- Did not segment the paired-close bps distribution by surface class
  (soccer `#` vs stock `para:` vs other). n=54 is thin for a 4-way split.
  Follow-up when settlements get to n>150.
