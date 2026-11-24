# 0x9551e7d4 xyz:SKHX round-trip — 2026-10-15

**NO EDGE. Closed round-trip 10-03 → 10-14: n=13 buys / 11 sells
(0.312 sh), realized net −$90.62 (close_pnl −$90.55, fees −$0.065)
on the only leader-copy coin that produced any own_fills this
journal window. Entire 10-14 cut was leader-driven (reduce_only
IOC against leader's close cascade); position was then flat.**

## Why this report (not the daily pair-maker check)

Pair maker is still wedged — 24h stats: 4,040 `maker_start` cycles,
0 `maker_quote`, 0 `#*` own_fills, 0 realized on the shadow book.
Prior cron 2026-10-13 flagged this as *not a research question* and
asked for a pool across 10-07 + 10-11 time-to-settle samples; both
sources remain gone to log rotation (journal still 26 MB, start
2026-09-28). Nothing new to measure there.

What **is** new: 24h base-perp realized went from ~$0 to **−$87.72**,
driven by a single leader-close cascade on `xyz:SKHX` at 12:33–12:34
UTC on 10-14. That cascade closed an 8-day bag. Worth paying the
tape to understand before the next SKHX trade.

## Reconstruction

All 24 own_fills on `xyz:SKHX` in `state/journal.jsonl`
(2026-09-28 → now):

| metric | value |
|---|---|
| first own_fill | 2026-10-03 05:15 UTC (buy 0.024 @ $1367.10) |
| last own_fill | 2026-10-14 12:34 UTC (sell 0.002 @ $1063.00) |
| own buys | n=13, total 0.312 sh, vwap **$1353.55** |
| own sells | n=11, total 0.312 sh, vwap **$1063.32** |
| residual position | 0.000 sh (clean round-trip) |
| realized close_pnl | **−$90.55** |
| fees | $0.0651 |
| **net** | **−$90.62** |

Side-by-side with leader `0x9551e7d4cd963558bb9882aecc74f549262e217f`:

| metric | leader | copy (us) |
|---|---|---|
| coin | xyz:SKHX | xyz:SKHX |
| fills (open/close) | 983 B / 319 A | 13 B / 11 A |
| total shares | 1,764.0 B / 1,800.0 A | 0.312 B / 0.312 A |
| vwap buy | $1,172.23 | $1,353.55 (+$181 / +15.5%) |
| vwap sell | $1,095.84 | $1,063.32 |
| realized (FIFO avg-cost, long side) | **−$144,437** | **−$90.55** |
| loss per unit bought | ≈ $82 / sh (7.0%) | $290 / sh (21.4%) |

Leader ran a 1,764-share long on SKHX, DCA'd down from the mid-$1300s
to the sub-$1000s, then forcibly closed at mid-$1000s for a ~$144k
realized loss on the long leg (±36sh excess sell is likely an opened
short, ignored here).

Our copy was 13 buys all between 10-03 and 10-06, in a tight
$1336–$1367 band (vwap $1353.55). The per-dex exposure cap on xyz
then blocked the next 970 of the leader's 983 opens — exactly as
designed. We held 0.312 sh static for 8.4 days while the leader
averaged down ~$180 further. When the leader finally cut, our
reduce_only mirrors fired on 11 of 319 close fills (the first 11
that landed with margin to spare) and flattened us at vwap $1063.32.

## Why we did ~3× worse per share than the leader

Three mechanics, nothing new:

1. **Cap gives us the top.** `[[xyz-dex-capped-blocks-skhx]]` /
   `[[weight-scales-clip-size]]`: hitting the per-dex cap stops
   adds, so we eat the opening fills and miss the DCA that improves
   the leader's basis. Our vwap buy was $181 higher than theirs
   (+15.5%); the entire gap is "fills the leader got that we
   couldn't."
2. **No independent stop.** We held 8.4 days at a worsening unrealized
   because the leader was still open; we exit only when they do.
   `[[backtest-blind-to-unrealized]]`: this is the martingale-leader
   failure mode the backtester cannot see.
3. **Clip asymmetry on close.** Leader closes in large chunks; our
   reduce_only clips are 0.031 sh. Our 11 close fills landed early
   in their cascade at vwap $1063.32 — essentially identical to the
   leader's own vwap sell ($1095.84, slightly worse because the
   leader kept selling into weaker levels after the cap was no
   longer binding on reduce_only). The sell leg was not the problem.

## What this does and doesn't prove

- **One round-trip.** n=1 clean entry→exit cycle. One trade is not
  a strategy verdict.
- But it's a **complete** cycle: pos→0, no residual, both legs
  realized. There is no unrealized hiding, no "wait for the leader
  to come back" story.
- Confirms the cap-at-the-top hypothesis **with a number**: +15.5%
  worse vwap on entry maps 1:1 to the loss we took vs the leader's
  rate.
- Does **not** say the leader is dead — pre-10-03 journal rotation
  removed the window where the leader's net was reportedly +$82/30d
  (config comment, 2026-08-25 measurement).

## Decision item for Quorra

- `always_follow` still carries `0x9551e7d4` at weight **0.60**
  (down from 1.27). On the only completed copy loop we can audit,
  the leader cost us $90.62. That's **~40% of a $230-ish account**.
- Two clean options:
  1. **Symbol-filter 9551e7d4 to NOT trade xyz:SKHX** (per
     `[[leader-9551e7d4-ondo-drift]]`'s "needs symbol filter not
     weight cut"). The leader's edge, if any, was earlier/elsewhere
     — SKHX just hit the cap-at-the-top failure cleanly.
  2. **Drop weight to the 0.1 floor** (0.0 = SystemExit per
     `[[dead-leaders-at-stale-weights]]`) and keep them live for
     signal shadowing only.
- Preference is (1) — targeted, preserves the leader for non-SKHX
  flow, and SKHX is the only coin we actually copy-filled against
  them in this window.

## Reproducer

```python
import json
rows = []
with open("state/journal.jsonl") as f:
    for line in f:
        if '"xyz:SKHX"' not in line: continue
        e = json.loads(line)
        if e.get("event") != "own_fill": continue
        if e.get("coin") != "xyz:SKHX": continue
        rows.append(e)
rows.sort(key=lambda e: float(e["ts"]))
buys  = [e for e in rows if e["side"] == "B"]
sells = [e for e in rows if e["side"] == "A"]
vwap = lambda xs: sum(float(e["px"])*float(e["sz"]) for e in xs)/sum(float(e["sz"]) for e in xs)
print(f"n_buy={len(buys)} vwap_b={vwap(buys):.2f}")
print(f"n_sell={len(sells)} vwap_s={vwap(sells):.2f}")
print(f"close_pnl_sum={sum(float(e.get('closed_pnl') or 0) for e in rows):+.4f}")
print(f"fees_sum={sum(float(e.get('fee') or 0) for e in rows):+.4f}")
```

## Operational note

`MEASURED.md`, `research/QUESTIONS.md`, and
`.claude/agents/quant-researcher.md` are still absent on branch
`exec/maker-shadow-harness` — 15th consecutive run. Deliverables 2–3
(MEASURED append, QUESTIONS move) skipped; the research file is the
only artifact.

## Verdict

**NO EDGE on 0x9551e7d4 xyz:SKHX copy-flow. n=1 round-trip, net
−$90.62 over 11 days — the cap gives us the top of their DCA and
the exit price is the same, so the arithmetic cannot work on this
symbol. Recommendation: symbol-filter SKHX off 9551e7d4 before the
next entry; leave the leader otherwise live.**
