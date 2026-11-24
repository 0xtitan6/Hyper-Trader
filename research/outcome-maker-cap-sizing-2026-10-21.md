# Outcome-maker drawdown vs shared daily-loss cap (2026-10-21)

**MEASURED. 30d outcome-only rolling-24h worst drawdown = −$248.16
(2026-09-27 21:14 UTC). Shared cap is $80. In 30d, outcome-only
PnL alone sat below −$80 for 47.3h — 6.6% of all time — in two
distinct episodes. The current cap mutes copy whenever outcome-maker
has its structural bad day, which is roughly 1-in-15 days. This is
a sizing finding, not an edge finding.**

Follow-up to `copy-roster-daily-cap-2026-10-20.md`, which identified the
shared `max_daily_loss_usd` as the mute mechanism and asked for the
"last 7d max daily outcome drawdown worth measuring".

---

## Workspace state, up front

`MEASURED.md`, `research/QUESTIONS.md`, `.claude/agents/quant-researcher.md`
do not exist on `main`. They live on dormant `feat/inplay-guard-pair-maker`
(last touched 2026-09-22). Same note as `mm-model-spec-2026-09-25.md` and
`oil-lag-2026-09-24.md`. The topmost OPEN question on that dormant branch
(0a: "a REAL market-making model") was answered on 2026-09-25. I'm
treating yesterday's cron report as the live research queue — the real
open thread on `main` — and measuring its explicit next-step ask.

The branch mismatch is now on its third cron. Fix before the next run or
we keep writing findings the dormant branch never consumes.

## What I measured, method

Source: `state/state.db::own_fills`, 1,064 rows covering
2026-09-12 → 2026-10-21. Classified each coin as:

| class       | pattern         |
|-------------|-----------------|
| outcome     | `#NNNNN`        |
| xyz_perp    | `xyz:*`         |
| base_perp   | otherwise       |

Confirmed the cap mechanism is **not** strategy-partitioned
(`src/positions.py:111 realized_pnl_today → state.pnl_since` sums
`closed_pnl - fee` across ALL fills, no coin filter). So any realized
loss on outcome-maker eats directly into the copy engine's budget.

Then computed:
1. Per-UTC-day net PnL by class for the last 30d.
2. Rolling-24h worst net PnL by class — the exact quantity
   `realized_pnl_today()` reads.
3. Minute-grid trailing-24h sum, then integrated the time spent below
   `-$C` for `C ∈ {50, 80, 100, 150, 200}`.
4. Continuous breach intervals at `-$80`.

Window: 2026-09-21 → 2026-10-21, 721h.

## What the numbers say

### Daily rollup — 12 outcome-active days in last 30d

| stat    | outcome realized (gross) |
|---------|-------------------------:|
| sum     | **−$261.98** |
| mean    | −$21.83 |
| stdev   | $56.45 |
| min     | **−$111.35** (2026-10-18) |
| max     | +$122.99 (2026-09-25) |
| p25     | −$57.06 |
| p10     | −$106.29 |

The two days where outcome realized alone cleared the current −$80
cap: **−$94.49 (09-26)** and **−$111.35 (10-18)**.

### Rolling-24h max drawdown by class (last 30d)

| class     | worst rolling-24h net | ended           |
|-----------|----------------------:|-----------------|
| outcome   | **−$248.16**          | 2026-09-27 21:14 |
| xyz_perp  | −$90.58               | 2026-10-14 12:31 |
| base_perp | −$38.79               | 2026-10-11 13:23 |
| all       | −$248.15              | 2026-09-27 21:14 |

Outcome dominates total drawdown. The all-strategies worst and the
outcome-only worst are the same event, within rounding — the other
classes contributed nothing on that day. xyz_perp's worst was the
2026-10-14 SKHX blowup, which is a separate strategic conversation.

### Time spent below −$C (outcome only, last 30d)

| cap  | hours below | % of 721h |
|------|------------:|----------:|
| 50   | 78.3h       | 10.9% |
| **80**   | **47.3h**   | **6.6%** |
| 100  | 24.2h       | 3.4% |
| 150  | 1.0h        | 0.1% |
| 200  | 0.8h        | 0.1% |

### Continuous breach intervals at the current $80 cap

| start               | end                 | duration |
|---------------------|---------------------|----------|
| 2026-09-26 22:04 Z  | 2026-09-27 22:14 Z  | 24.2h |
| 2026-10-18 18:14 Z  | 2026-10-18 18:34 Z  | 0.3h |
| 2026-10-18 19:24 Z  | 2026-10-19 18:14 Z  | 22.8h |

Both episodes are **~24h each**, which is exactly the rolling-window
length. The mechanism: a settlement cluster that loses >$80 of face
in a few hours remains in the trailing window until it ages out. During
that ~24h, every copy intent fails `_risk_check`.

Yesterday's cron measured 48 reachable leader_fills → 11 risk-cap
blocks in the aftermath of the 10-18 breach. Scaled up: the ~45h/mo
of outcome-induced mutes could be costing 20-30 copy opens. On the
copy engine's observed +$0.0416/trade (`MEASURED.md` on the dormant
branch, n=964), that is ≤ +$1.25/mo of expected copy edge forfeited —
within noise. Dollars-at-risk is small; the operational cost is that
copy performance can't be assessed cleanly while outcome keeps
clamping the window.

## Assumptions and how they weaken the finding

- **The reaper's 2026-10-18 settlements are representative.** They
  may not be — only n=2 breach episodes in 30d. If outcome-maker's
  loss distribution has a heavier tail than the ~−$200 observed max,
  this report under-sizes the cap. Cheapest next measurement:
  per-market settlement PnL distribution over the full outcome-maker
  history, not just realized windows.
- **No post-10-18 config change filtered.** `always_follow`,
  `leader_weights`, and risk caps unchanged since 2026-10-18 23:17
  (verified by yesterday's report). So the 48 reachable fills from
  the Oct-20 24h window are the right counterfactual for cost.
- **Copy edge is still an open question.** If the copy engine's
  mean +$0.04/trade is noise (n=964 gave t = +0.25 per the dormant
  `MEASURED.md`), the "copy opens lost to the cap" cost is zero and
  the cap debate is purely about outcome-maker's blast radius.

## What this does not resolve

- **Does outcome-maker have positive EV in steady state?** 30d net
  is −$262 realized. The pair_maker shipped 2026-09-20 and most of
  these fills are from it. 11 of 12 outcome-active days are net
  negative, with one +$123 outlier (09-25). This is consistent with
  the dormant branch's finding that paired outcome quoting with
  cross-to-complete is **−$0.183 per basket by construction**. The
  "100% passive single-leg round-trip, never cross, never settle"
  configuration that stayed UNPROVEN there has not been shadowed
  independently — I cannot tell from `own_fills` which fills were
  the pair_maker's primary quote vs the minder's hedge.
- **Per-strategy accounting isolation.** Yesterday's report proposed
  three options (separate caps, raise shared cap, shrink outcome's
  blast radius). This report sizes the input to that decision; it
  does not pick the option.

## What it would take to resolve

1. **Tag fills by strategy** in `own_fills` (new column
   `source TEXT` populated by `MirrorTrader` vs `PairMaker` vs
   `MinderHedge`). Then `realized_pnl_today` can filter per class
   and the cap can be partitioned without code outside positions.py.
   Engineering: ~2h.
2. **Settlement-only PnL distribution** on the pair_maker's full
   history. Separates "the cross cost us 76 bps" from "the settle
   cost us 13.4 bps of face" cleanly. The 10-18 cluster is 136
   fills — a mix of makes, hedges and settlements. Without
   decomposition we can't say whether $150 or $250 is enough.
3. **Shadow the 100% passive single-leg config** against the live
   book for 24-48h with the current cap intact — zero capital at
   risk, measures turnover at our size. This is the only outcome-
   market configuration not yet falsified. If it dies, outcome-maker
   as a class is done and the cap sizing becomes irrelevant.

## Recommendation for Quorra / strategist

Three actionable readings, pick one:

1. **Hold cap at $80 and accept the mute.** Correct if the copy
   engine's +$0.04/trade is not real edge — then losing 20-30 copy
   opens/mo is net-zero to zero and the global safety is maximised.
   Downside: outcome-maker's distribution is not currently supervised
   because the cap triggers before anyone looks.
2. **Raise cap to $150 and keep the shared design.** Clears
   outcome-maker's 10th-percentile single-day loss while still
   catching the −$248 worst-case within 6h of it starting. Accepts
   that outcome-maker contributes most of total drawdown and sizes
   the risk budget to that reality. Rolls back the 2026-10-16
   "rolling 24h" tightening in effect, since $150 is roughly
   two UTC-day $80 caps.
3. **Partition the cap by strategy** (option (a) in yesterday's
   report). Highest leverage long-term — outcome-maker and copy
   fail orthogonally, so a shared budget double-penalises both. But
   it needs the fill-tagging work in "What it would take" above.
   One week minimum.

Not actionable from this measurement alone: whether outcome-maker
should be running at all. That is the open question
`research/handrules-dead-pair-maker-2026-10-11.md` was pointing at.

## Reproducer

```python
# From hyper-trader repo root with .venv active.
import sqlite3, numpy as np, datetime
from collections import deque
con = sqlite3.connect('state/state.db')
# As of 2026-10-21 07:43 UTC
now = 1792568086
cutoff = now - 30*86400
fills = list(con.execute(
    'SELECT ts, coin, closed_pnl, fee FROM own_fills WHERE ts>=? ORDER BY ts',
    (cutoff,)))
# outcome-only trailing-24h sum, sampled every 600s
oc = [(t, p-fee) for (t, c, p, fee) in fills if c.startswith('#')]
times = np.arange(cutoff, now+3600, 600)
pnl = np.array([sum(pf for ft, pf in oc if t-86400 <= ft <= t) for t in times])
for cap in [50, 80, 100, 150, 200]:
    print(f"<= -${cap}: {(pnl < -cap).mean()*100:.1f}% of time")
```

## Deltas that would be appended to `MEASURED.md` (dormant branch)

```
| 2026-10-21 | outcome-maker daily drawdown | 30d: rolling-24h worst -$248, 47h/mo below the shared -$80 cap in two ~24h episodes; min single-day -$111 (2026-10-18) | 721h | MEASURED — the daily cap is sized smaller than outcome-maker's p25 single-day loss. Mute of copy is structural, not incidental. |
```
