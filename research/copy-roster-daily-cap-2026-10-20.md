# Copy roster, day 2 — mute mechanism is NOT clip-floor, it's the shared daily_loss_cap (2026-10-20)

**NO EDGE. 24h window: 48 reachable perp leader_fills, 0 own_fills, 11 opens
blocked by `daily_loss_cap (net=-120.11)` on a $80 cap. The engine sized every
intent correctly; outcome-maker settlement losses from 10-18 blocked every
copy open through the rolling-24h window. Falsifies the 10-19 report's
clip-floor hypothesis.**

---

## What I set out to measure

The 10-19 report (`copy-roster-live-flow-2026-10-19.md`) left one explicit
falsifier: *"Set `0x9551e7d4` weight back to 0.4 for one strategist cycle,
measure own_fills — if still zero at 0.4 the mute is NOT clip-floor."* Config
hasn't moved (verified below), so I ran the next-best test: another 24h at the
same weights, and *why* each open didn't fire.

## Config at 2026-10-20 07:43 UTC (unchanged since 10-18 23:17)

```yaml
always_follow: [0x9551e7d4, 0x511e60d3]
leader_weights: {0x9551e7d4: 0.10, 0x511e60d3: 1.00}
sizing.fixed_usd: 30
sizing.min_per_trade_usd: 10
risk.max_daily_loss_usd: 80          # <-- the binding constraint
risk.max_dex_exposure_usd: 750
risk.max_total_exposure_usd: 1200
```

## 24h journal reality

| event                              | count |
|------------------------------------|------:|
| leader_exit_detected               | 822   |
| settlement (377 of them snapshots) | 377   |
| reconcile                          | 232   |
| leader_fill (reachable perp)       | **48** |
| intent_skipped                     | 40    |
| risk_check (ALL `ok:false`)        | 11    |
| size_rounded_up                    | 10    |
| own_fill                           | **0** |

### Reachable leader_fills by action

| leader     | coin       | action | n  | downstream |
|------------|------------|--------|---:|------------|
| 0x9551e7d4 | xyz:BE     | close  | 24 | `intent_skipped: leader_closing_we_are_flat` |
| 0x9551e7d4 | xyz:SP500  | close  | 13 | `intent_skipped: leader_closing_we_are_flat` |
| 0x9551e7d4 | xyz:SP500  | **open** | **10** | `risk_check ok:false reason=daily_loss_cap (net=-120.11)` |
| 0x511e60d3 | xyz:SPCX   | **open** | **1**  | `risk_check ok:false reason=daily_loss_cap (net=-120.11)` |

The **48 reachable leader_fills → 0 own_fills** story factors as:
- 37 closes on positions we never had (because earlier opens were blocked) →
  routed to `leader_closing_we_are_flat`.
- **11 opens correctly sized and intent-built, every one blocked at
  `_risk_check` by the daily loss cap.**

## The sizing step actually works

`size_rounded_up` fired 10 times in 24h, bumping 0x9551's $7.69 clip to
$15.39 to clear `min_per_trade_usd=$10`:

```
leader=0x9551e7d4 coin=xyz:SP500
from_sz=0.001  from_notional=$7.69
to_sz  =0.002  to_notional  =$15.39
effective_min=$10
```

So at weight 0.10, the engine sizes to **$15.39, not $3.00.** The 10-19 report's
arithmetic (`weight 0.10 x $30 fixed = $3 clip < $10 floor`) was wrong because
the engine floor-UPS, it doesn't drop. **The clip-floor mute hypothesis is
falsified.** `[[weight-scales-clip-size]]` is wrong in the small-weight regime.

## The actual mute mechanism

`src/mirror.py:836-839`:
```python
net_realized = self.positions.realized_pnl_today()
if -net_realized >= r.max_daily_loss_usd:
    self.alerter.alert("critical", f"Daily loss cap hit: net=${net_realized:.2f}")
    return False, f"daily_loss_cap (net={net_realized:.2f})"
```

`realized_pnl_today` is a ROLLING-24h sum over the `own_fills` sqlite table
(see `src/state.py:149` `pnl_since`). The table holds **every own_fill AND
every HIP-4 settlement**; `_handle_settlement` calls `record_own_fill` with
the settle PnL (`src/positions.py:525`). There is **no strategy tag**.

What was in the rolling window at 2026-10-19 13:38:34 UTC (when the 10 opens
were blocked):

```
2026-10-18 18:07  #118051  settle  cp=$ -82.10
2026-10-18 19:24  #114560  settle  cp=$ -46.86
2026-10-19 00:30  #114590  settle  cp=$ +42.09  fee=$0.26
2026-10-19 00:32  #118050  settle  cp=$ -69.09
```

Plus ~$1.03 of other maker fills on #117990. Rolling net was reported as
−$120.11 by the live code at 13:38:34. The 11th block fired at 13:52:40 on
0x511e60d3's one SPCX open. **100% of 24h copy opens were killed by outcome
settlement losses from the day before.**

The cross-contamination is strict and verified by code path, not inferred.

## What this changes about the 10-19 verdict

| claim from 10-19                                 | status |
|--------------------------------------------------|--------|
| copy engine delivered +$0.45 / 5d                | **holds** (now +$0.45 / 6d, no new reachable fills) |
| 9551 at weight 0.10 is muted                     | holds (0 own_fills) |
| 9551 is muted BY clip-floor                      | **FALSIFIED** — engine rounds up to $15.39, intent builds, risk cap blocks |
| 511 is terminal at $0 account                    | partially falsified — leader opened SPCX +2.69 shares today (2026-10-20 ~13:52 UTC per the risk_check tid timing) |
| strategist's "sub-$100 next cycle → cut 511 to 0.5" condition triggered | obsoleted — the leader isn't dead, it's trading again |

## What falsifies this new story

- If the next 24h have `realized_pnl_today > −$80` AND we see 0 own_fills on
  10+ reachable leader_fills, cap is not the mute — go dig again.
- If a cold copy day (0 outcome settlements, 0 outcome maker fills) still shows
  0 own_fills on live reachable leader_fills, cap is not the mute.
- If `size_rounded_up` stops firing at weight 0.10 (because fixed_usd or min
  changes), the clip-floor hypothesis could re-enter at those parameters.

## What I did NOT do

- Did not query HL REST for current leader state — 429'd once in-session, so
  deferred. The journal shows 0x511e60d3 opened a fresh 2.69-share SPCX long
  at $148.38 at the same minute as the 11th block (tid 187447298976626), so
  they are not terminal.
- Did not read `~/.config/hyper-trader/.env` or wallet-derived values.
- Did not touch config, orders, or the kill switch.

## Recommendations for Quorra / strategist

1. **The 10-19 recommendation "drop 9551 from always_follow because clip-floor
   mutes it" is now wrong-for-the-reason-stated.** At weight 0.10 the engine
   does fire, when the cap allows. Decision becomes: do we care about the
   30d edge of copying 9551 at $15 clip vs the operational cost? Independent
   of the mute hypothesis.
2. **Strategy accounting isolation is the real finding.** One shared
   `max_daily_loss_usd` across copy + outcome-maker means a bad settlement
   day guarantees a day of zero copy flow — not because copy is losing, but
   because another strategy is. Options, in order of surgery:
   a. Separate the risk cap per strategy (filter `pnl_since` by coin class).
   b. Raise `max_daily_loss_usd` to a number that outcome-maker's realistic
      1d drawdown can't trip (last 7d max daily outcome drawdown worth measuring).
   c. Accept the cross-contamination as a feature — "one strategy's bad day
      pauses the whole account" is actually a defensible global risk rule;
      the fix is then shrinking outcome-maker's single-day blast radius.
3. **The strategist cron's leader-roster logic has no visibility into
   risk-cap blocks.** It will keep recommending weight tweaks that cannot
   fire. Suggest adding a "blocked-by-risk" counter to the strategist's
   diagnostic prompt before it writes any `leader_weights` diff.

## Reproducer

```bash
cd /home/ec2-user/.openclaw/workspace/hyper-trader
.venv/bin/python - <<'PY'
import json, time
cutoff = time.time() - 24*3600
with open("state/journal.jsonl") as f:
    for ln in f:
        try: e = json.loads(ln)
        except: continue
        if (e.get("ts") or 0) < cutoff: continue
        if (e.get("event") or "") == "risk_check" and str(e.get("reason","")).startswith("daily_loss_cap"):
            print(e["ts"], e["reason"], e["intent"]["coin"], e["leader"][:10])
PY
```

```sql
-- Rolling-24h own_fills table state (= what the risk gate reads)
sqlite3 state/state.db \
  "SELECT ts, coin, closed_pnl, fee FROM own_fills WHERE ts >= strftime('%s','now')-86400 ORDER BY ts"
```

## Append to MEASURED.md (deferred — not on main)

```
| 2026-10-20 | copy engine (both leaders, 24h) | 48 reachable fills, 0 own_fills, 11 risk-cap blocks | 24h | NO EDGE — mute is `max_daily_loss_usd=$80` tripped by -$128 of outcome settlements, not clip-floor. Clip-floor hypothesis from 10-19 falsified: engine `size_rounded_up` bumps $7.69 clips to $15.39 and the intent builds. Shared daily cap is the real knob. |
```
