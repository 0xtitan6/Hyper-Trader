# Hand-rules face-size as ex-ante filter — 2026-10-09

**UNPROVEN. Blended -162 bps → +241 bps if we drop opens with face>$30
(n=38→34), but the entire effect is one trade (#30140). ex-#30140 the
open_face↔PnL correlation collapses from r=−0.64 to r=+0.05.**

## Why this question tonight

The 2026-10-08 stop-loss sim (`research/stop-loss-signal-2026-10-08.md`)
answered "would a mid-adverse stop catch #30140?" — yes, 1 of 38, blended
flips to +207 bps. That finding is kinematically optimistic (simulated
crossing, not a live stop).

Tonight's complement: **can we refuse #30140 at open time**, from journal
metadata alone, without needing a live stop? If an ex-ante filter works, it
is cheaper to run than a stop and does not depend on being able to cross
mid under adverse conditions.

Candidates in reach from journal only: `open_face`, `open_px`, `open_side`,
coarse hold-time proxies. No new book snapshots exist for `#30140` so book-
state features are out of scope. Shadow harness still emits nothing to the
journal (`grep -c shadow state/journal.jsonl = 0`), same as the ninth prior
cron run — the head-to-head is still blocked on three lines of plumbing.

## Data

Same 2026-10-07 pure-maker filter: `coin.startswith('#')`, zero `leader_fill`
events ever on the coin, dedup on `tid`, drop `face<=$1`, keep closes with
`|closed_pnl|>0`.

- 38 clean paired close fills (hand-rules bot only)
- Collapsed to **24 unique open-events** (3 of them have 2–4 close fills
  against one open — same `(coin, open_ts)` pair, almost certainly partial
  fills of one position)
- Face total $620, PnL -$10.04, blended **-162 bps**

Every open was `side=B` (hand-rules only buys — HIP-4 legs are bid-only, no
short). `open_side` is not a filter.

## Open-face strata (collapsed, n=24 open-events)

| open_face bucket | n | face | pnl | blended | mean bps | median bps |
|---|---:|---:|---:|---:|---:|---:|
| [$0, $2) | 1 | $20 | +$1.68 | +840 | +840 | +840 |
| [$2, $5) | 1 | $25 | +$0.16 | +63 | +63 | +63 |
| [$5, $15) | 8 | $184 | +$0.79 | +43 | +55 | +79 |
| [$15, $30) | 12 | $249 | +$8.91 | **+357** | +323 | +67 |
| [$30, $999) | 2 | $142 | **−$21.58** | **−1,524** | −1,432 | −1,432 |

The [$30,$999) bucket is two trades: `#30140` open_face $98.6 → −$24.23, and
`#44850` open_face $64.6 → +$2.65 (one open, three partial-fill closes). One
catastrophic, one small winner.

## Face-cap simulation (per-fill basis, n=38)

| cap | n_kept | excl | face | pnl | blended | bootstrap 95% CI |
|---|---:|---:|---:|---:|---:|---|
| none | 38 | 0 | $620 | −$10.04 | **−162** | [−898, +418] |
| $50 | 34 | 4 | $478 | +$11.54 | **+241** | — |
| $30 | 34 | 4 | $478 | +$11.54 | **+241** | [+80, +494] |
| $25 | 34 | 4 | $478 | +$11.54 | **+241** | — |
| $20 | 24 | 14 | $359 | +$10.16 | **+283** | [+73, +635] |
| $15 | 16 | 22 | $229 | +$2.63 | +115 | — |
| $10 | 10 | 28 | $115 | +$2.39 | +209 | — |

Caps $25, $30, $50 drop the same 4 trades (because nothing sits in
[$30, $65) or [$65, $99)). Those 4 are #30140 (−$24.23) and the three
partial fills of a single #44850 open (+$2.65 combined).

## The honest attribution

Pearson corr(open_face, bps) on 24 open-events: **r = −0.64, permutation
p = 0.027** (5,000 shuffles). Looks real.

Drop `#30140`: **r = +0.05, n=23**. The whole correlation is one trade.

Null check — random-drop-4 permutation: of 5,000 random exclusions of 4 of
38 fills, 8.7% produced a blended bps ≥ +241. The cap-$30 effect is better
than two-thirds of random drops but it is not clean.

## What this means

- An open_face > $30 filter would have refused 2 of 24 opens: one
  catastrophic loser (`#30140`, −$24.23) and one small winner-with-three-
  partials (`#44850`, +$2.65). **Net ex-ante +$21.58 on $620 face in this
  window.**

- The filter rests on one leverage point. A face >$30 open that resolves
  within the hand-rules bot's natural spread (3 of 4 excluded fills) is not
  evidence that the cap works — it is evidence that most big-face opens are
  fine and one of them was ruinous.

- The 2026-10-08 stop-loss remains the better tool at this sample. It
  catches the same trade (−3,257 bps crosses any threshold between −200 and
  −500) and does not require ex-ante knowledge of which trade will blow up.

## What I assumed, and what fails if it is wrong

- **Pairing is nearest-earlier opposite-side open on same coin.** Same as
  10-07 and 10-08. If the hand-rules bot layered opens on `#30140`, the
  pairing I used attributes the whole close PnL to the last open only. The
  journal shows exactly one `own_fill` on `#30140` before the loss close,
  so there is no layering ambiguity on the leverage trade. The other three
  excluded fills (#44850) have three identical partial closes against one
  open at the same timestamp — grouping them as one event is correct.

- **Face = px × sz at fill time**, not weighted by any later adds. Correct
  for a single-open, single-close pairing. Would understate exposure if
  the bot averaged in; it did not here.

- **"Hand-rules territory" = `#*` coin with zero `leader_fill` ever.** Same
  scope correction the 10-07 report introduced. Mixed coins are excluded.

If the no-ex-ante-filter conclusion is wrong, the most likely path is
book-state at open time (micro-price pressure, imbalance, prior adverse
prints) rather than fill metadata. We have no `h30140.jsonl` book snapshot,
so this cannot be tested from current data.

## What I could not determine

- Whether a hard open_face cap holds up as the sample grows. One
  catastrophic trade is a very weak basis for a filter.
- Whether book features at open time would have flagged `#30140`
  specifically. Need `#30140` in `state/book_snapshots/`.
- Whether the hand-rules bot averaged into `#30140` at tighter touch-prices
  before the catastrophic open. Only one `own_fill` is recorded prior to
  the loss close, so this looks like a single bid that got hit at the top
  of a 24% drop in 7 minutes.

## What it would take to resolve

1. **Add every `#*` coin we quote to `state/book_snapshots/`** — current
   coverage is 28 coins and `#30140` is not among them. Without this, no
   ex-ante book-state filter is checkable in replay.
2. **Wait for n=100 pure-maker closes** at current pace (~2 per day). At
   this flow, the next catastrophic open is on average 38 trades away.
3. **Separately: the shadow harness needs to emit `shadow_quote` and
   `shadow_fill` to `state/journal.jsonl`.** Still 0 shadow events in the
   journal as of 2026-10-09 07:44 UTC. This is the tenth cron run flagging
   it. The topmost question (shadow head-to-head) stays blocked until that
   lands.

## Verdict appendable to MEASURED.md

> **Hand-rules open_face as ex-ante filter (2026-10-09, n=24 open-events,
> 38 close fills).** UNPROVEN. Dropping opens with face>$30 lifts blended
> close PnL from **−162 bps to +241 bps** (bootstrap 95% CI [+80, +494]),
> but ex-`#30140` the open_face↔PnL correlation collapses from r=−0.64
> (perm p=0.027) to r=+0.05. The entire face signal is one leverage
> point. Stop-loss (`handrules-stop-loss-signal-2026-10-08`) remains the
> safer lever at this sample size. No book snapshot exists for `#30140`,
> so book-state ex-ante features are not testable in replay.

## For the operator

- Same ask as the 10-07 and 10-08 reports: please move `research/QUESTIONS.md`
  and `MEASURED.md` to the branch the cron runs on, or point the cron at
  `feat/inplay-guard-pair-maker`. Tenth consecutive run writing to the
  wrong branch.
- Three lines of shadow-harness plumbing remain the blocker on the real
  head-to-head.
- If the operator ships a face cap anyway, cap at $30 or $50 — same 4
  excluded trades, but tighter caps start dropping genuinely profitable
  mid-size opens.

## Reproducing

```
cd /home/ec2-user/.openclaw/workspace/hyper-trader
.venv/bin/python - <<'PY'
import json, statistics, random, math
from collections import defaultdict
leader=set()
for L in open('state/journal.jsonl'):
    try: e=json.loads(L)
    except: continue
    if e.get('event')=='leader_fill' and e.get('coin','').startswith('#'):
        leader.add(e['coin'])
seen=set(); fills=[]
for L in open('state/journal.jsonl'):
    try: e=json.loads(L)
    except: continue
    if e.get('event')!='own_fill': continue
    c=e.get('coin','')
    if not c.startswith('#') or c in leader: continue
    t=e.get('tid')
    if t in seen: continue
    seen.add(t); fills.append(e)
opens=[e for e in fills if abs(e.get('closed_pnl',0.0))<=1e-9]
closes=[e for e in fills if abs(e.get('closed_pnl',0.0))>1e-9 and e['sz']*e['px']>1.0]
by=defaultdict(list)
for o in opens: by[o['coin']].append(o)
for v in by.values(): v.sort(key=lambda e:e['ts'])
paired=[]
for c in closes:
    cands=[o for o in by[c['coin']] if o['ts']<c['ts'] and o['side']!=c['side']]
    if not cands: continue
    o=cands[-1]; face=c['px']*c['sz']
    paired.append({'coin':c['coin'],'pnl':c['closed_pnl'],'face':face,
                   'bps':c['closed_pnl']/face*1e4,'open_face':o['px']*o['sz']})
total_pnl=sum(p['pnl'] for p in paired); total_face=sum(p['face'] for p in paired)
print(f'baseline n={len(paired)} blended {total_pnl/total_face*1e4:+.0f} bps')
kept=[p for p in paired if p['open_face']<=30]
pnl=sum(p['pnl'] for p in kept); face=sum(p['face'] for p in kept)
print(f'cap $30 n={len(kept)} blended {pnl/face*1e4:+.0f} bps')
PY
```

Expected on 2026-10-09 07:44 UTC:
`baseline n=38 blended -162 bps` / `cap $30 n=34 blended +241 bps`.
