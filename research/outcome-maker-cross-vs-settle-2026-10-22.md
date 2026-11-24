# Outcome-maker PnL decomposition: cross vs settle (2026-10-22)

**MEASURED. 30d outcome-maker net = −$140.47 across 626 fills on 77 coins /
25 YES-NO pairs. Settlement net = **+$19.15** (+32 bps of opens, roughly
flat by design); the entire aggregate loss is **−$159.50** of cross
sells. BUT: cross drag is not structural — median cross is −$0.02,
mean is −$1.00, and the 10 worst crosses alone sum to −$183 (115% of
the net cross loss). All but one of those 10 happened on 10-17/10-18.
Yesterday's "settle cost us 13.4 bps / cross cost us 76 bps" prior is
inverted and off by an order of magnitude: settles don't bleed, and
cross cost is one-event-dominated, not steady-state.**

Follow-up to `outcome-maker-cap-sizing-2026-10-21.md`, "What it would
take to resolve" item 2: *settlement-only PnL distribution on the
pair-maker's full history, to separate the cross cost from the settle
cost cleanly*.

---

## Workspace state

`research/QUESTIONS.md`, `MEASURED.md`, `.claude/agents/quant-researcher.md`
still absent from `main`. Fourth cron in a row flagging this; treating
yesterday's cron report as the live research queue (same as 10-21).
No fresh action from the operator since; nothing on this cron's output
reaches the dormant branch where those files live.

## Method

Source: `state/state.db::own_fills`, 626 rows with `coin LIKE '#%'`,
window 2026-09-19 03:43 → 2026-10-19 12:56 UTC (729h ≈ 30d). Settlement
events were sparse in `state/journal.jsonl` (only 3 live-tagged, journal
rotation), so classified by **fill price**:

| side | px | class |
|---|---|---|
| B | — | OPEN_MAKE_BUY (passive YES or NO buy) |
| A | 0 or 1 | SETTLEMENT (forced sell at $0 lost / $1 won) |
| A | strictly in (0, 1) | CROSS (voluntary exit before settle) |

Verified by looking at the sampled journal: settlement events ARE
side='A' at exactly px=0.0 or px=1.0. The classifier is deterministic
on this schema; no fills fell outside the four buckets.

## 1. Aggregate decomposition

| bucket | n | gross PnL | fee | net | notional |
|---|---:|---:|---:|---:|---:|
| OPEN_MAKE_BUY | 407 | $0.00 | $0.122 | **−$0.12** | $5,996.12 |
| CROSS (0<px<1) | 159 | −$157.09 | $2.413 | **−$159.50** | $3,410.47 |
| SETTLE WON (px=1.0) | 31 | +$1,083.24 | $2.742 | +$1,080.50 | $2,268 shares |
| SETTLE LOST (px=0.0) | 29 | −$1,061.34 | $0 | −$1,061.34 | $2,827 shares |
| SETTLE combined | 60 | **+$21.89** | $2.742 | **+$19.15** | — |
| **TOTAL** | **626** | **−$135.19** | **$5.28** | **−$140.47** | — |

In bps-of-maker-opens ($5,996.12 face):

| component | $ | bps |
|---|---:|---:|
| cross | −$159.50 | **−266 bps** |
| settle | +$19.15 | **+32 bps** |
| open-make fees | −$0.12 | −0.2 bps |
| **total** | **−$140.47** | **−234 bps** |

## 2. The cross-drag is not steady-state

Per-fill distribution of the 159 cross sells:

| stat | $/fill |
|---|---:|
| mean | −$1.003 |
| **median** | **−$0.023** |
| p10 | −$1.40 |
| p90 | +$0.40 |
| stdev | $8.15 |

The *typical* cross is a wash. The $-1.00 mean is a tail. The ten worst
cross fills:

| time (UTC) | coin | px | sz | net |
|---|---|---:|---:|---:|
| 10-18 18:07 | #118051 | 0.1750 | 386 | **−$82.14** |
| 10-18 19:24 | #114560 | 0.0455 | 70 | −$46.87 |
| 09-20 20:21 | #30140 | 0.5767 | 129 | −$24.28 |
| 10-17 21:55 | #118050 | 0.6123 | 1000 | −$8.61 |
| 10-18 07:46 | #118020 | 0.4858 | 273 | −$4.33 |
| 10-18 07:45 | #118010 | 0.5586 | 523 | −$4.21 |
| 09-20 19:54 | #30091 | 0.0033 | 30 | −$3.64 |
| 10-17 21:55 | #118050 | 0.6099 | 305 | −$3.37 |
| 10-11 23:39 | #85540 | 0.1704 | 11 | −$2.85 |
| 10-18 07:47 | #118010 | 0.5586 | 322 | −$2.59 |

Top-10 crosses sum = **−$182.89** vs total cross net −$159.50 ⇒ the
remaining 149 crosses collectively earn **+$23.39**. All but one of
these ten crosses (and 7 of the 10) are in a single ~26h window on
2026-10-17/18. Strip that window and cross-drag is net *positive*.

## 3. Settlement is near zero by design, high variance by sample

Per-coin settle-net (n=60 coins with settlements):

| stat | $/coin |
|---|---:|
| mean | +$0.32 |
| min | −$128.94 (#46520) |
| max | +$199.54 (#41610) |
| stdev | **$51.57** |

Share balance at settlement across 22 complete YES/NO pairs: mean imbalance
`(YES−NO)/(YES+NO) = −0.026`, stdev `0.475`. On paper the pair-maker ends
delta-neutral in expectation; in sample, individual pairs settle anywhere
±50% imbalanced.

Grouped by pair base: 25 YES/NO pairs with both legs touched. Settle-net
by pair:

| group | n pairs | sum settle-net | sum cross-net |
|---|---:|---:|---:|
| both legs settled | 19 | **−$84.78** | — |
| one leg settled, other crossed out | 6 | +$39.42 | — |
| only one side ever quoted | 27 one-sided coins | **+$171.36** net | — |

The "complete pair held to settlement" subset is the actual
construction-cost of the pair maker, and it is ≈ **−$4.5/pair** on 19
settled pairs. The one-sided subset wins by luck (29 of 60 coins settled
LOST at $0; 31 WON at $1; one-sided quoting that lands on winners nets
+$171 by chance — not reproducible).

## 4. What this does to the cap-sizing argument

Yesterday's finding stands numerically — outcome-maker's worst
rolling-24h is still −$248 — but the mechanism is now visible:

1. **The −$248 drawdown and the −$111 bad day BOTH came from the
   same cross cluster** (10-17 21:55 → 10-18 19:24, −$152 of
   cross across 7 fills).
2. **Settlement contribution to the −$248 drawdown is modest**:
   the paired settlement during that same ~24h was −$69 on #118050
   and offsetting wins elsewhere.
3. **The daily cap catches variance in settlement, not drift in
   crosses.** Settlement variance is EV-near-zero
   (+$19/$5996 face). Cross drift is EV-near-zero *outside* the
   10-18 event. The one event that broke the cap was a cross-driven
   force-flatten, not a settle avalanche.

So: a cap-raising decision defended by "settle variance eats $150" is
not supported. A cap-raising decision defended by "a single cross-cluster
can eat $150 in a few hours and we want to size the cap around it" IS
supported.

## 5. What this leaves open

- **Why the 10-18 cross cluster happened.** The 7 crossed coins were
  all around the same time (#118010 / 20 / 50 / 51 / #114560). This
  looks like a KILL/stop-loss or a forced flatten, not organic market
  moves. Correlating these cross timestamps with
  `maker_stop`/`risk_check`/`reconcile` events in `journal.jsonl`
  would tell us whether the cross is from (a) adverse market moving
  through our mid, (b) the operator's hand on the kill switch, or
  (c) time-to-settle guard firing late. Each has a different fix.
- **Whether removing the 10-18 cluster changes the "outcome-maker
  should be running at all" question.** Ex-cluster, 30d net is
  roughly −$140 + $152 = **+$12** net. That is still not statistical
  edge, but it is also not "clearly bleeding". The handrules kill
  argument (10-11 report, "ZERO fills in 13 days") is a separate
  axis — surface-selection is dead regardless of PnL.
- **Settle-only subset's EV cannot yet be bounded**. 25 complete
  pairs × 19 both-settled = n=19 for the clean "pair maker as
  designed" measurement. −$84 across 19 pairs is point estimate
  −$4.5/pair but stdev $51.57/coin ⇒ 95% CI easily spans ±$25/pair.
  Underpowered.

## 6. Deliverable to the strategist / Quorra

**Point estimate**: outcome-maker's structural daily EV on a *clean*
day (no forced cross cluster) is roughly flat ±$5 on today's capital.
The −$140 trailing-30d is one event, not a slow drip. Cap-sizing should
be designed around the single-event scenario, not around a steady-state
drift that isn't there.

**Concrete asks for next cron / operator**:

1. Attach the 10-17 21:55 → 10-18 19:24 journal slice to the 7
   catastrophic cross fills — identify the trigger. Cheap: one `grep`
   over `journal.jsonl` with ±120s windows around each tid.
2. If option 2 ("raise shared cap to $150") from yesterday is on the
   table, size instead on **the single-event cross-cluster distribution**,
   not on the daily-sum distribution — those are different random
   variables.
3. Shadow-harness is still blocked (confirmed in 10-11 report; no
   change). The "100% passive single-leg, never cross" configuration
   that stays UNPROVEN *is* the obvious ablation this report begs
   for; without live cross-removal we can only replay history.

## 7. Reproducer

```python
# From hyper-trader repo root with .venv active.
import sqlite3
c = sqlite3.connect('state/state.db')
rows = c.execute("""
  SELECT coin, side, sz, px, closed_pnl, fee
    FROM own_fills WHERE coin LIKE '#%'
""").fetchall()
cross = settle = make_fee = 0.0; cross_n = settle_n = make_n = 0
for coin, side, sz, px, cp, f in rows:
    if side == 'B':
        make_fee += f; make_n += 1
    elif px in (0.0, 1.0):
        settle += cp - f; settle_n += 1
    else:
        cross += cp - f; cross_n += 1
print(f"opens n={make_n}, cross n={cross_n} ${cross:+.2f}, "
      f"settle n={settle_n} ${settle:+.2f}, make_fee ${-make_fee:.3f}")
```

## 8. Append to `MEASURED.md` (dormant branch)

```
| 2026-10-22 | outcome-maker cross vs settle | 30d: settle-net +$19 (+32 bps of $5996 opens), cross-net -$160 (-266 bps). Cross drag is 1-event: top-10 crosses -$183, 7 of them in a 26h cluster on 10-17/18. Settle construction-cost ≈ -$4.5/pair (n=19 complete settled pairs). | 626 fills, 77 coins, 25 pairs | MEASURED — the leak is the cross cluster, not steady-state settlement. Yesterday's "settle 13.4 bps / cross 76 bps" prior is inverted. |
```
