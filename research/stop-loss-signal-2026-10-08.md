# Hand-rules stop-loss sim — 2026-10-08

**EDGE on a hard mid-adverse stop in the paired-close set.** A **-200 to -300
bps** stop on hand-rules closes flips blended-face from **-162 bps (95% CI
[-916, +418])** to **+207 bps (95% CI [+44, +441])** on **n=38** paired
closes. Catches **1 of 38** trades (`#30140`, 7-minute hold, -3,257 bps on $74
face). Mechanism-strong, sample-thin, kinematically optimistic.

## Why this question tonight

Nine prior cron runs have noted `MEASURED.md` / `research/QUESTIONS.md` live
on `feat/inplay-guard-pair-maker`, not this branch; the "topmost" question
(shadow harness head-to-head) is still blocked on `maker_shadow.py` emitting
`shadow_quote` / `shadow_fill` to `state/journal.jsonl` (`grep -c shadow
state/journal.jsonl` = 0). Yesterday's report
(`research/handrules-stratified-2026-10-07.md`) ended with "the shadow must
prove it would have declined [`#30140`] as its first test." That is a
measurable sub-question — tonight is a direct answer to it, on journal data
only, zero HL load.

## Data

Same filter as the 2026-10-07 stratified reading: `coin.startswith('#')`,
pure-maker territory (`leader_fill` count = 0 on same coin anywhere in the
file), one row per `tid`, drop `face<=$1`, keep closes (`|closed_pnl|>0`).

- n = 38 clean paired closes (hand-rules bot only)
- face = $620
- blended PnL = -$10.04 (-162 bps)
- 35 wins / 3 losses

## The pairing

Each close is paired with the **nearest-earlier opposite-side `own_fill` on
the same coin**. Not perfect — ignores partial fills and mid-hold adds — but
the 38-row set is clean enough that each row has exactly one unambiguous
earlier open.

Worst row:

| tid | coin | open side | open px | close px | hold | face | PnL | bps |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 61320805449458 | #30140 | B (buy) | 0.76451 | 0.57667 | 7.0 min | $74.39 | **-$24.23** | **-3,257** |

That single row is 3.2× the next-worst bps, 4× the next-worst dollars. The
mid-move was -24.6% in 7 minutes — a surface-wide repricing event that the
hand-rules bot has no exit for (the bot has no cost-adjusted re-quote, no
mid-move stop, no toxicity gate). The journal has no intervening
`maker_quote` / `maker_cancel_all` on `#30140` between open and close, so the
original resting bid at 0.76 was never withdrawn as the mid cratered.

## Hard-stop simulation

Replay each close under the rule: *"if realised bps on this close is worse
than -X bps, charge -X bps on face instead and discard the actual loss."*

Kinematically optimistic — assumes we can exit at the cap level with zero
slippage. Reality: the stop would have to cross IOC in a venue that just
reset by 24%, so **the achievable number is upper-bounded by this**.

| stop cap | n stopped | blended | mean | 95% CI (blended, 5k bootstrap) | note |
|---:|---:|---:|---:|---|---|
| none | 0 | **-162 bps** | +188 | [-916, +418] | zero inside CI |
| -100 | 3 | +223 | +270 | — | carves 2 shallow losers too |
| **-200** | **3** | **+207** | **+270** | **[+44, +441]** | **zero outside CI** |
| **-300** | **1** | **+193** | **+266** | **[+23, +436]** | **catches only #30140; zero outside CI** |
| -500 | 1 | +169 | +260 | [-34, +421] | borderline |
| -1000 | 1 | +109 | +247 | [-183, +420] | CI straddles |
| -1500 | 1 | +49 | +234 | [-343, +422] | — |

The cleanest cell is **-300 bps**: catches only `#30140`, leaves 37 untouched,
takes blended from `-162` to `+193` bps, with the bootstrap 95% CI entirely
positive. -200 is marginally better numerically because it also clips two
small losses (`#43050` at -244 bps, `#14870` at -204 bps), but those are
inside the noise of the win set and probably normal maker variance.

## What this does NOT prove

- **n=3** losers in the sample. One of them (`#30140`) is a 10× outlier; the
  stop rule's whole measured effect is that one row. The CI tightens with a
  stop because we are literally removing the fat left tail; that is not
  evidence the policy generalises.
- **Kinematic**: real exit-at-stop is a crossed IOC into a book that just
  moved 24%, not a maker fill at the cap price. Live PnL will be worse than
  this upper bound. By how much is an open question.
- **No feature identifies `#30140` pre-fill.** The open at 0.76 looks normal
  on its own. The stop rule is a *post-fill* inventory-management policy, not
  a *pre-fill* decline policy. The shadow harness still needs a toxicity
  signal to decline the entry; the stop is the second line.
- **No book snapshots** cover any of these fills — `state/book_snapshots/`
  ends 2026-09-25 (10+ days stale). This replay is journal-only, so we
  cannot cross-check with mid-move during the 7-minute hold.

## For the shadow harness

If `maker_shadow.py` wires a journal emitter this week, the baseline it must
beat is unchanged from 2026-10-07: median **+85 bps**, mean **+227 bps**,
95% CI **[+137, +323]** ex-outlier on n=36 pure-maker binary closes.

The specific head-to-head test is now **the catastrophe test**:

> Replay `#30140` through the shadow policy. Does its inventory-management
> code decline the open, pull the resting quote during the 7-minute hold,
> or cross out before the realised -3,257 bps? If not, the shadow has the
> same hole as hand-rules and loses to a 3-line hard stop. If yes, it is
> strictly dominant on this sample.

Hard stop as a candidate for the live hand-rules bot (without waiting for
the shadow): drop a -300 bps mid-adverse rule onto resting binary quotes,
checked on the existing reconcile loop (5 min cadence is marginal — `#30140`
burned the full move in 7 min, so a 1-min or event-driven check is safer).

## Verdict appendable to MEASURED.md

> **Mid-adverse stop on pure-maker binary paired closes (2026-10-08, n=38).**
> A hard **-300 bps** stop would have flipped blended face from -162 bps
> (95% CI [-916, +418]) to **+193 bps (95% CI [+23, +436])**, catching only
> `#30140` (1 of 38 trades, 7-minute hold, -3,257 bps on $74 face). -200 bps
> is numerically tighter (+207, 95% CI [+44, +441]) at the cost of carving
> two shallow losers inside noise. Mechanism-strong, n=1 catastrophe, assumes
> no slippage at exit — real PnL will be worse than the upper bound.

## For the operator

- `MEASURED.md` / `research/QUESTIONS.md` branch pointer is now **ten** cron
  runs stale. Please merge the stashed `feat/inplay-guard-pair-maker` queue
  onto this branch, or re-point the cron.
- If the live hand-rules bot can take a config flag, a `-300 bps` mid-adverse
  stop with a sub-minute cadence is cheap insurance. Catches 1 trade in 38.
  Even at a worse realised fill (e.g. -500 bps instead of the cap), it still
  dominates letting `#30140` run to -3,257 bps.
- Shadow harness is still unlanded. `grep -c shadow state/journal.jsonl` = 0.

## What I did not do

- No new API probes. Journal replay only.
- No touch of `MEASURED.md`, `INVARIANTS.md`, `research/QUESTIONS.md` — those
  live on `feat/inplay-guard-pair-maker` and I cannot graft onto a branch I
  am not on.
- No slippage model for the simulated stop. The reported numbers are a
  **ceiling**, not a point estimate. Modelling the stop fill under a 24%
  surface reprice needs book data we do not have for Sep 27.
- Did not fit the stop threshold against other coin classes (`para:*`,
  `perp:xyz:*`) — the hand-rules bot does not quote them.

## Reproducing

```
cd /home/ec2-user/.openclaw/workspace/hyper-trader
.venv/bin/python - <<'PY'
import json, statistics, random
from collections import defaultdict
has_leader={e['coin'] for line in open('state/journal.jsonl')
            for e in [json.loads(line)]
            if e.get('event')=='leader_fill' and (e.get('coin','') or '').startswith('#')}
seen=set(); by_coin=defaultdict(list)
for line in open('state/journal.jsonl'):
    e=json.loads(line); c=e.get('coin','') or ''
    if not c.startswith('#') or c in has_leader: continue
    if e.get('event')!='own_fill' or e.get('tid') in seen: continue
    seen.add(e['tid']); by_coin[c].append(e)
pairs=[]
for coin,fills in by_coin.items():
    fills.sort(key=lambda x: x['ts'])
    opens={'A':[], 'B':[]}
    for f in fills:
        pnl=float(f.get('closed_pnl',0) or 0)
        if abs(pnl)<1e-6: opens[f['side']].append(f); continue
        os_='A' if f['side']=='B' else 'B'
        if not opens[os_]: continue
        face=float(f['sz'])*float(f['px'])
        if face<=1.0: continue
        pairs.append(dict(coin=coin,bps=pnl/face*1e4,pnl=pnl,face=face,
                          hold=f['ts']-opens[os_][-1]['ts']))
def blended(ps,cap=None):
    tot=0; f=0
    for p in ps:
        f+=p['face']
        tot += (-cap/1e4*p['face']) if cap and p['bps']<-cap else p['pnl']
    return tot/f*1e4
for cap in (None,200,300,500,1000):
    print(f'cap={cap} blended={blended(pairs,cap):+.1f} bps')
PY
```

Expected on 2026-10-08 07:45 UTC:

    cap=None blended=-162.0 bps
    cap=200 blended=+206.7 bps
    cap=300 blended=+192.9 bps
    cap=500 blended=+168.9 bps
    cap=1000 blended=+108.9 bps
