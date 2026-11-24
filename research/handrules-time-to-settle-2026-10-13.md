# Hand-rules pair maker — time-to-settle is the loss axis — 2026-10-13

**UNPROVEN but suggestive. On #85540 (n=48 closes, 132 fills, −$56.47
realized): 71% of close-pnl loss (−$8.98 of −$12.72) comes from the
16 closes inside T−2h to settlement. A "no new entries inside T−2h"
filter would have cut this trade from −$56.47 to ~−$24 counterfactual
(saves ~$32). A "no first-touch inside T−24h" filter would have
blocked the trade entirely (first fill was T−10.6h). n=1 market —
hypothesis, not evidence.**

## Why this report (not the daily "dead" cadence)

Prior cron 2026-10-12 07:43 UTC flagged the next question:
> "the handrules-face-exante stratification redone with (a) 10-07 n=38
> + (b) 10-11 n=48 pooled, and a new feature: minutes-to-settlement at
> open time."

The 10-07 n=38 sample is in the pre-09-27 journal segment that was
truncated by log rotation (file was 55 MB on 10-11, 21 MB on 10-12,
23 MB today — all pre-09-27 events are gone). Pooling isn't possible
from on-disk data. So this report answers the easier sub-question:
**on the n=48 closes we DO have, does time-to-settlement predict loss?**

Also noted: `QUESTIONS.md`, `MEASURED.md`, and
`.claude/agents/quant-researcher.md` still absent on branch
`exec/maker-shadow-harness` — 14th consecutive run. Deliverables 2–3
(MEASURED append, QUESTIONS move) skipped, same as every prior run.

## 24h state — pair maker went dark again

| metric | 10-12 07:43 UTC | 10-13 07:43 UTC | Δ |
|---|---|---|---|
| hours since last `maker_quote` | 17.8 | 41.8 | +24.0 (quiet) |
| hours since last `#*` `own_fill` | 8.0 | 32.0 | +24.0 (quiet) |
| 24h `maker_start`/`stop` cycles | 4,064 | 4,077 | +13 (~21s period) |
| 24h `maker_quote` events | 6 | 0 | −6 |
| 24h `maker_cancel_all` events | 4,101 | 4,077 | all reason=`shutdown` |
| 24h `#*` `own_fill` events | 132 | 0 | −132 |
| 24h non-snapshot `settlement` | 1 | 0 | — |
| 24h base-perp own_fill n / net | 60 / −$26.21 | 35 / **−$0.015** | ~flat ex-fees |
| 24h **total realized** | **−$82.00** | **~$0** | — |

The maker is now targeting `#45160` (new coin since 10-11), but every
`maker_start` is immediately followed by `maker_cancel_all
reason=shutdown` + `maker_stop` within the same millisecond. Not a
`spread_too_tight` skip — the maker instance is being torn down by the
harness before it can quote. 4,077 start/stop cycles in 24h = exactly
one every 21s, same cadence as prior "wedged" days. Zero quotes, zero
fills, zero PnL.

Something in the maker loop is bailing out immediately after start-up
on `#45160`. Can't diagnose further without reading `src/maker.py` and
following the `shutdown` call site — out of scope for this read-only
analyst run.

## Time-to-settle stratification on #85540 (n=48 closes)

Settlement: 2026-10-12 00:51:49 UTC. All 48 paired closes bucketed by
hours-to-settlement **at the time of the close**:

| T-to-settle | n | W/L | win rate | sum close_pnl | avg/close |
|---|---|---|---|---|---|
| >8h | 0 | — | — | — | — |
| 4–8h | 5 | 0/5 | 0% | −$0.85 | −$0.170 |
| 2–4h | 27 | 10/17 | 37% | −$2.89 | −$0.107 |
| 1–2h | 16 | 4/12 | 25% | **−$8.98** | **−$0.561** |
| <1h | 0 | — | — | — | — |

- **71% of close-pnl loss is in the final 2h window** (−$8.98 of −$12.72).
- Avg-per-close grows 5× from 2–4h bucket to 1–2h bucket.
- First fill was T−10.6h, last fill was T−1.14h, settlement verdict `lost`.

## Counterfactual filters

**Filter A — "no new entries inside T−2h":** at T−2h the net position
was 33 shares long at avg ~$0.60. If pair-maker froze both legs at
T−2h, residual going to zero loses ~$20 instead of $43.78, close-pnl
loses the pre-cut $3.74 instead of the full $12.72. Total: ~−$24 vs
actual −$56.47. Saves ~$32 on this trade.

**Filter B — "no first-touch inside T−24h":** first fill at T−10.6h
would have been skipped entirely. Saves full $56.47. More conservative
— also skips any profitable late-day entries we might have found in a
larger sample.

**Filter C — "no first-touch below P($0.10) or above P($0.90)":** the
starting mid at first fill was ~$0.615, so this market would NOT have
been blocked. Doesn't help here.

## What this does NOT prove

- **n=1 coin and n=1 settlement event.** The 2–4h bucket is 37% win
  rate (vs the 1–2h bucket at 25%) — if the next T−2h trade is a
  lucky winner, the ordering flips.
- **Not a Lindy argument** — binary markets expiring tomorrow or next
  week may have fundamentally different ex-post variance; this one
  decayed to zero which is the maximum-loss settlement path.
- **The filter is counterfactual-only.** The pair maker closes
  through its own quotes; a hard T−2h cutoff might behave differently
  with the real queue state (fewer resting bids = different fills).

## Decision item for Quorra

- Maker is quiet again (0 quotes/24h). Diagnose `shutdown` on
  `maker_start` for `#45160` separately — not a research question.
- The T−to−settle finding is **cheap to turn into code**: an
  ex-ante filter in `src/maker.py` that refuses new quote cycles
  when `expiry - now < 2h`. Doesn't require retraining anything.
- Pooling across all 48 closes + the pre-09-27 n=38 pre-wedge sample
  needs a journal-replay from compressed logs (if they exist) or a
  wait for new fills. Add to backlog.

## Reproducer

```python
import json, datetime as dt
settle_ts = dt.datetime(2026,10,12,0,51,49,tzinfo=dt.timezone.utc).timestamp()
fills = [json.loads(l) for l in open("state/journal.jsonl") if '"#85540"' in l]
fills = [e for e in fills if e.get("event")=="own_fill"]
closes = [e for e in fills if float(e.get("closed_pnl") or 0) != 0]
for b_lo, b_hi, label in [(4,8,"4-8h"),(2,4,"2-4h"),(1,2,"1-2h")]:
    bucket = [c for c in closes if b_lo <= (settle_ts-float(c["ts"]))/3600 < b_hi]
    pnl = sum(float(c["closed_pnl"]) for c in bucket)
    wins = sum(1 for c in bucket if float(c["closed_pnl"])>0)
    print(f"{label}: n={len(bucket)} wins={wins} pnl={pnl:.4f}")
```

## Verdict

**UNPROVEN. On n=1 market: 71% of close-pnl loss concentrated in last
2h to settlement; T−2h filter saves ~$32 of $56 counterfactual.
Statistically a hypothesis, not evidence — needs 10-07 n=38 pool and
≥3 more live settlements before shipping as a config change.**
