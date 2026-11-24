# Outcome-maker 10-17/18 cross-cluster trigger attribution (2026-10-24)

**MEASURED. The −$160 "cross cluster" from the 10-22 report is NOT one
mechanism — it is four separate flatten events from THREE distinct order
paths. Of −$159.50 cross-net over 30d, −$158.30 maps to these four
events: one emergency operator script (`flatten_balcle.py`, cluster A,
−$13.77), one hand-rolled operator dump (cluster B, −$15.58), and two
automated sports-monitor cut-losses (clusters C and D, −$128.95). The
`leader_reconcile` orphan-close path explicitly did NOT fire — config
has `leader_exit_auto_close: false` and no `_submit_close` was reached.
Of the four, exactly one is a real leak: cluster C force-sold the
WINNING NO leg of the BAL/CLE pair (386 × #118051 @ $0.175, which
would have settled at $1.00). Opportunity cost = ~$318, confirming
the `never-rearm-a-stale-stop-live` memory. The other three closed at
market prices consistent with EV or saved money vs. settlement.**

Follow-up to `outcome-maker-cross-vs-settle-2026-10-22.md`, "Concrete
asks for next cron / operator" item 1: *attach the 10-17 21:55 →
10-18 19:24 journal slice to the 7 catastrophic cross fills — identify
the trigger*.

---

## Workspace state

`research/QUESTIONS.md`, `MEASURED.md`, `.claude/agents/quant-researcher.md`
still absent from `main`. Fifth cron in a row flagging this. Continuing
to treat the previous cron report as the live research queue.

## Method

Source: `state/state.db::own_fills` (fill ledger), `state/journal.jsonl`
(5417 maker lifecycles + 196 reconciles + 788 leader_fills in-window),
`state/balcle_monitor.jsonl`, `state/nfl_games_monitor.jsonl`,
`state/hb_oversize.jsonl`. For each of the 7 catastrophic cross fills
(tids in the 10-22 report), pulled all events in ±180s. Decoded
timestamps and resolved order paths against the live code tree
(`src/leader_reconcile.py`, `src/maker.py`, `scripts/*monitor*.py`,
`scripts/flatten_balcle.py`, `scripts/hb_oversize_guard.py`).

Explicitly RULED OUT:
- `leader_reconcile._submit_close`: `config.yaml:997 leader_exit_auto_close: false`.
  Only `leader_exit_detected` alerts are journaled, no order path.
- Mirror follower (`src/mirror.py`): zero `leader_fill` or `order_result`
  events on the 5 cluster coins in-window.
- Maker (`src/maker.py`): `_hedge_one_sided` only buys the opposite leg
  on taker; it does not sell inventory.
- HB oversize guard (`scripts/hb_oversize_guard.py`): `action="stopped"`
  only invokes `systemctl --user stop hyper-hip4-mm-<slug>.service`; it
  does not place orders. Verified by reading the script.

## 1. Trigger attribution per cluster

| cluster | time (UTC) | coin(s) | sz | realized | TRIGGER | counterfactual |
|---|---|---|---:|---:|---|---:|
| **A** | 10-17 21:55:01 | #118050 (5 fills) | 1,600 | **−$13.77** | `scripts/flatten_balcle.py` — operator-run emergency unwind of 1642-share HB bug | #118050 settled $0 → SAVED ~$975 |
| **B** | 10-18 07:45–07:47 | #118010 (3) + #118020 (8) | 913 + 866 | **−$15.58** | Operator ad-hoc taker dumps (no automated trigger found; sizes match the HB-reported oversize bags of 1182/905; sold in 4-call ladder) | #118010/20 no settlement in db; closed near orphan avg, ≈ EV-neutral |
| **C** | 10-18 18:07:36 | #118051 | 386 | **−$82.09** | `scripts/balcle_live_monitor.py` → `cut_loss BAL+10 Q2 (confirmed 3x)` → `flat_coin(#118051)` IOC-taker | #118050 settled $0 ⇒ #118051 (NO leg) would settle $1 → **LEAK ~$318** |
| **D** | 10-18 19:24:08 | #114560 | 70 | **−$46.86** | `scripts/nfl_games_live_monitor.py` → `cut_loss NYG-17 Q3` → `flat_coin(#114560)` IOC-taker | NYG down 17 in Q3; implied win prob ≈ 4.5% → ~$0 opportunity cost |

Fills 8–10 in the 10-22 top-10 list (two #118050 at 09-20, two
sub-$3 blips on #30091 / #30140 / #85540 / #117990 / #118020) fall
outside this window and were not analysed. They sum to −$36 total,
dominated by the −$24 on #30140 (not a cluster event).

## 2. The three order paths, in detail

**Path 1 — operator one-shot flatten scripts (clusters A, B).**
`scripts/flatten_balcle.py` is checked in, docstring:
> *"Emergency flatten of oversize BAL/CLE YES bag. HB maker had a
> position-tracking bug; built up to 1642 shares vs $50 cap. Dumping
> ~1600 shares as crossing taker to get back to intended exposure."*

It walks the HL bid ladder for 5 levels, submits one IOC taker at
20bp below the worst touched level, and prints the result — no
alerting, no journal entry. Cluster A matches this script exactly:
SZ_TO_SELL=1600, px_submit≈0.611, 5 bid fills totaling 1600. Fired
10-17 21:55:01, 24s after the 21:54:37 `leader_exit_detected`
alert that surfaced the 1642-share bag.

Cluster B is the same mechanism but hand-rolled (no checked-in
script found for #118010/#118020). Sizes 523 and 322 on #118010,
and 273/203/201/94/50/21/21/3 on #118020, delivered in two 1-second
bursts at 07:45:46-47 and 07:46:09, consistent with two curl-level
IOC taker calls on each coin walking the bid book. The HB oversize
guard had `stopped` both services at 07:07:51 (first entries in
`state/hb_oversize.jsonl`), so the maker was already off; this was
cleanup of the stranded bag.

**Path 2 — balcle in-game auto-flat (cluster C).**
`scripts/balcle_live_monitor.py` runs under
`hyper-balcle-monitor.service`. Polls the live NFL scoreboard;
when the loser-margin crosses the configured cut-loss threshold
for `CONFIRM_POLLS` consecutive polls, calls `flat_position(coin)`.
Journal entry at 1792346856:

```json
{"event":"cut_loss","BAL":10,"CLE":0,"margin":-10,"quarter":2,
 "status":"SCHEDULED","flatten":{"status":"ok","reason":"cut_loss BAL+10 Q2",
 "sz":386.0,"result":{...filled 386 @ 0.17501, oid 578509066303}}}
```

Note `"status":"SCHEDULED"` while margin is already −10 in Q2 — the
feed emits SCHEDULED on games that have kicked off; the margin
field is authoritative. Monitor fired correctly on its own logic.
What's wrong is the **product logic**: the pair-maker was long
BOTH #118050 (BAL YES) and #118051 (CLE YES). Flattening ONLY the
losing leg (#118051, CLE YES, since BAL was winning) sold the
side that would gain, while the winning-at-the-time BAL YES
(#118050) was ALREADY cleaned up by the earlier `flatten_balcle.py`.
Net: we held the LOSER to settlement (−$69.09 on 113 residual
shares, documented in journal) and sold the WINNER at the bottom.

**Path 3 — generic NFL games auto-flat (cluster D).**
`scripts/nfl_games_live_monitor.py` is the generalised version of
Path 2, keyed on a hard-coded BETS dict:
```python
"#114540": {"team":"NE", ..., "flat_py":"flat_coin"},
"#114590": {"team":"KC", ...},
"#114560": {"team":"NYG","opp":"NO","label":"NO@NYG YES"},
```
Journal entry at 1792351449: NYG@NE/… wait, NO@NYG YES, down 17
in Q3, confirm_polls met, `flat_coin(#114560)` → sold 70 shares
@ 0.04553. This fired exactly as designed. The question for the
strategist is not "why did it fire" but "should we be TAKING these
in-game directional bets in the first place", which is a
different research thread (`handrules-*` series).

## 3. What this means for the 10-22 report

**The 10-22 report conflated** two mechanistically distinct
flatten paths under a single "cross-cluster" bucket. The split is:

| mechanism | realized | opportunity cost | real leak |
|---|---:|---:|---:|
| operator unwinds (A + B) | −$29.35 | SAVED ~$975 on A, EV-neutral on B | **−$0** |
| in-game auto-flat (C + D) | −$128.95 | +$318 on C, ~$0 on D | **−$318** |
| rest-of-tail (not in cluster, 149 other crosses) | +$23.39 | — | — |
| **total cross-net** | **−$134.91** | — | **−$318** |

The 10-22 point estimate "cross drift is EV-near-zero outside the
10-18 event" is now sharpened: the 10-18 event itself is 70% EV-neutral
operator cleanup + 25% a real $318 loss on cluster C's wrong-leg flatten
+ 5% ~EV-neutral NFL cut-loss on cluster D.

**The 10-22 cap-sizing argument changes.** The −$248 24h drawdown
mechanism is NOT "a cross cluster can eat $150 in a few hours" —
it is **"the pair-maker ran unbalanced, operator flattened the WINNING
leg of the pair while the losing leg bled to zero"**. Raising the
daily cap is unresponsive to this; a per-leg balance check on the
pair-maker inventory before any auto-flat fires IS responsive.

## 4. What this leaves open

- **The pair-maker ran 1642 YES vs 386 NO on BAL/CLE** (4.25× long
  the YES side). The 10-22 report quoted a 25-pair mean imbalance
  of −2.6% ± 47.5%; this single pair was +61%. Needs a separate
  look at *how* the pair-maker allowed such a one-sided build —
  likely the HB position-tracking bug named in `flatten_balcle.py`'s
  docstring, which the memory `hb-oversize-guard-coin-notation`
  entry says was fixed 10-18 but the broken-maker-sibling-leg gap
  is still open.
- **Cluster B counterfactual is weak** — #118010/20 never show up in
  settlement journal, so I can't bound opportunity cost. Needs a
  book-snapshot replay at 07:45 on 10-18 to say whether the dump
  price was close to the forward settlement expectation.
- **`balcle_live_monitor.py` had no visibility into #118050's state**
  when it fired on #118051. A one-line change — "if the paired YES
  leg is already flat, do not sell the NO leg" — would have avoided
  the $318 loss. This is the direct, cheap, mechanical fix the
  10-22 report begged for.

## 5. Reproducer

```python
# From hyper-trader repo root with .venv active.
import json, sqlite3
from datetime import datetime, timezone

# The 7 catastrophic cross fills from the 10-22 report
TIDS = [445319747111986, 151477952857643, 374374702760224, 770854294587449,
        1125893100542940,  # cluster A: 10-17 21:55 #118050
        1022157568118010, 29001531932424, 1117047996187656,  # cluster B: #118020
        886146718802577, 576229152510579, 1118495390907694,  # cluster B: #118010
        182322076837803,  # cluster C: 10-18 18:07 #118051
        1116094141280898, # cluster D: 10-18 19:24 #114560
       ]

# A: match in scripts/flatten_balcle.py (SZ_TO_SELL=1600, hardcoded #118050)
# B: no checked-in script; hand-rolled operator dump
# C: grep "cut_loss" state/balcle_monitor.jsonl → one entry at 1792346856
# D: grep "cut_loss" state/nfl_games_monitor.jsonl → one entry at 1792351449

for L in open("state/balcle_monitor.jsonl"):
    j = json.loads(L)
    if j.get("event") == "cut_loss": print("C:", j)
for L in open("state/nfl_games_monitor.jsonl"):
    j = json.loads(L)
    if j.get("event") == "cut_loss": print("D:", j)
```

## 6. Append to `MEASURED.md` (dormant branch)

```
| 2026-10-24 | outcome-maker cross-cluster triggers | 10-17/18 cluster of −$158 across 4 flatten events maps to 3 distinct order paths: operator one-shot `flatten_balcle.py` (A, −$14, SAVED ~$975 vs settle), hand-rolled operator dump of #118010/20 (B, −$16, ≈EV-neutral), `balcle_live_monitor.cut_loss` wrong-leg flatten of #118051 (C, −$82 realized, **$318 opportunity cost** — flattened winning NO leg), `nfl_games_live_monitor.cut_loss` on #114560 (D, −$47, ≈EV-neutral). `leader_reconcile` auto-close NOT the trigger (disabled in config). Real leak is C: one-line fix is "balcle monitor must check paired-YES-leg state before flattening". | 4 clusters, 13 fills, 3 scripts, 1 un-scripted operator action | MEASURED — 10-22's "cross cluster" is three mechanisms, not one; cap-sizing fix was the wrong lever. |
```
