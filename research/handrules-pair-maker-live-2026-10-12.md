# Hand-rules pair maker — WOKE UP, LOST −$56.50 on #85540 — 2026-10-12

**NO EDGE. The pair maker's first 24h of live fills in 15 days took
−$56.50 realized on #85540 (−$12.72 from 48 paired closes +
−$43.78 settlement at $0.00). n = 132 fills, 48 unique closes,
29% win rate (14W/34L), avg per close −$0.265. Position settled
LOST at 00:51:49 UTC today.**

## Why this is a new report (vs the 12 prior "dead" reports)

The maker-shadow-harness branch's maker finally produced quotes and
fills. Prior cron 2026-10-11 at 07:43 UTC: `0 maker_quote`, `0 #*
own_fill` in 24h. This run at 07:43 UTC: `6 maker_quote`, `132 #*
own_fill`, `1 settlement verdict=lost`. The frozen-sample caveat
no longer applies; there is live data to score.

`QUESTIONS.md`, `MEASURED.md`, and `.claude/agents/quant-researcher.md`
still do not exist on branch `exec/maker-shadow-harness` — thirteenth
consecutive run. Deliverable 1 (research/*.md) is this file.
Deliverables 2–3 (MEASURED append, QUESTIONS move) are skipped,
same as every prior run.

## 24h delta vs 2026-10-11 report

| metric | 10-11 07:44 UTC | 10-12 07:43 UTC | Δ |
|---|---|---|---|
| hours since last `maker_quote` | 322.8 | 17.8 | reset — new activity |
| hours since last `#*` `own_fill` | 324.2 | 8.0 | reset |
| 24h `maker_start`→`stop` cycles | 3,985 | 4,064 | +79 (~22s period, consistent) |
| 24h `maker_quote` events | 0 | 6 | +6 (all #14870, all `side=B` px=0.11457) |
| 24h `maker_skip` events | ~0 | 32 | +32 (all #14870 `spread_too_tight`) |
| 24h `maker_cancel_all` events | ~0 | 4,101 | +4,101 |
| 24h `#*` `own_fill` events | 0 | 132 | +132 (ALL on #85540, NOT #14870) |
| distinct `#*` coins quoted since 09-27 | 0 | 2 (#14870, #45160) | +1 |
| distinct `#*` coins filled 24h | 0 | 1 (#85540) | +1 |
| 24h total `closed_pnl` + settlement | $0 | **−$82.00** | #85540 −$56.50, HYPE perp −$25.50 |

## The #85540 story (10-11 14:14 → 10-12 00:51 UTC)

- **14:14:05** — first fill, maker `B` 2 @ $0.61478 (no preceding
  `leader_fill` or `intent_skipped` event — this came out of the hand-
  rules engine, not the copy-trader).
- 17:00–20:00 — scalp-style grind, 25 fills, net long builds to
  ~15 contracts around avg $0.60.
- 20:00–23:43 — adverse spiral: price prints 0.605 → 0.016 across
  3.5h. 48 paired closes trigger, 34 of them losses. 84 total buys,
  519 contracts; 48 total sells, 200 contracts. Net left long
  **+319 contracts at avg entry $0.1373** (VWAP-weighted after
  closes).
- Last fill **23:43:24** — `B` 124 @ $0.01608 — looks like capitulation /
  reversed averaging on the way to zero.
- **10-12 00:51:49** — settlement: `verdict=lost`, `settle_px=0`,
  `closed_pnl = −$43.78` on the 319-sz residual. Repeats as
  `is_snapshot=True` every ~10 min thereafter (reconcile re-emits,
  32 settlement rows total; only the first is real).

### Trade quality on #85540

| metric | value |
|---|---|
| paired closes | 48 |
| wins / losses | 14 / 34 |
| win rate | 29.2% |
| avg closed_pnl per close | −$0.2650 |
| largest single-close loss | −$2.8503 |
| largest single-close win | +$0.5303 |
| sum of 48 closes | −$12.7214 |
| settlement loss on residual | −$43.7847 |
| fees paid on 132 fills | +$0.0640 (negligible, maker rebate / zero-fee tier) |
| **total #85540 realized** | **−$56.4701** |
| gross notional traded | $223.23 |
| cost basis of residual at avg entry | 319 × $0.1373 = $43.80 |

Blended on gross notional traded ($223): **−2,528 bps**.
Blended on open cost basis ($43.80): **−100%** (position zeroed).

## What this tells us vs the frozen 38-fill prior sample

The 2026-10-06 → 10-11 reports measured 38 clean paired closes
pre-wedge: blended −162 bps on $620 face, driven by one −$8.4 loss
(#30140). Tonight's 48 closes on #85540 are 15.8× deeper negative at
−$0.265/close (vs the prior −$0.044/close ex-#30140, or −$0.265 incl.
#30140 — same number by coincidence). The pair maker's realized-loss
distribution has NOT improved with the new live sample, and the
settlement-to-zero tail risk is now empirically paid for.

## Why I'm not calling it "edge found, negative"

- n = 1 coin and 1 settlement event. Single-market variance dominates;
  the 2026-10-07 stratified writeup established that one bad coin can
  flip the entire blended number.
- #85540 was a market the engine previously would not touch. Something
  on the harness side changed between 10-11 05:40 UTC (last empty
  cron) and 14:14 UTC (first fill). Likely branch merge / config bump
  / symbol-filter widening. **Confounder, not an edge test.**
- No shadow-vs-live head-to-head is possible: `grep -c shadow
  state/journal.jsonl = 0` — thirteenth cron with zero shadow events.
- The ex-ante filter work from 2026-10-09 (face > $30 cutoff)
  theoretically rejects #85540 (sz=124 @ $0.016 = $2 face, sz=2 @
  $0.61 = $1.22 face — all small). Face filter wouldn't have saved
  this one. **The hypothesis I'd re-run tomorrow is a `settle_px
  distance` ex-ante filter**, not face.

## What breaks if we extrapolate

Pair maker ran 10h, lost $56.47 realized. If this is representative
and the engine ran 24h/day with the same 132-fill-per-10h pacing:
**−$135/day burn on $223 notional traded = −60% ROI/day**. Fees are
not the problem (6¢ paid). Adverse selection + tail-settlement is.

## Reproducer

```python
import json, time
fills = [json.loads(l) for l in open("state/journal.jsonl") if '"#85540"' in l]
fills = [e for e in fills if e.get("event") == "own_fill"]
closes = [f for f in fills if float(f.get("closed_pnl") or 0) != 0]
print(len(closes), sum(float(c["closed_pnl"]) for c in closes))
# 48 -12.7214
```

Journal mtime 2026-10-12 07:44 UTC, size 21,039,935 bytes (down from
55 MB on 10-11 — a rotation / truncation happened. Prior-event
history before 2026-09-27 15:13 UTC is NOT in this file).

## Decision item for Quorra / Neil

- #85540 settled lost; residual is $0. **No live risk** on it now.
- Base-perp HYPE lost another −$25.50 in the same 24h window (60
  fills, net −$26.21 after $0.71 fees). Separate problem, outside
  this report's scope.
- The pair-maker-wedge investigation is **over** — the maker is no
  longer wedged. The new question is **"what are the eligibility
  rules that let #85540 through, and should #85540-shaped markets
  be gated out?"** Answering this needs the `handrules-face-exante`
  stratification redone with (a) 10-07 `n=38` + (b) 10-11 `n=48`
  pooled, and a new feature: **minutes-to-settlement at open time**.

## Verdict

**NO EDGE. −$56.47 realized on 1 coin, 132 fills, 48 closes, 29% win rate.**
