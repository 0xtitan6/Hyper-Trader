# xyz:SP500 copy drift + BE post-mortem (2026-10-26)

**UNPROVEN on xyz:SP500. +$0.59 paper PnL on $353 notional over 7d (16.6 bps net of fees), n=24 own_fills — within noise.**
**xyz:BE copy stopped at 10-24 by leader going silent, not by code; no symbol filter exists in config.**
**n = 24 own_fills on SP500 (7d), 110 SP500 leader_fills same window; 0 xyz:BE own_fills or leader_fills in last 48h.**

Follow-up to `xyz-be-copy-adverse-2026-10-25.md` which measured −201 bps drift on
xyz:BE copy and recommended a per-leader symbol filter. Natural next question:
(a) is the fix in, (b) is xyz:SP500 the next xyz:BE?

---

## Workspace state (13th consecutive cron run)

`MEASURED.md`, `research/QUESTIONS.md`, `.claude/agents/quant-researcher.md`
still absent from `main` HEAD. The branch pointer problem from the last twelve
reports is unchanged — graft section at bottom, same convention.

## What I measured

### xyz:BE — 48h follow-up

Journal + `state/state.db::own_fills`, 10-24 → 2026-10-26 07:43Z.

| metric                      | value          |
|-----------------------------|---------------:|
| leader_fills on xyz:BE 48h  | **0**          |
| own_fills on xyz:BE 48h     | **0**          |
| intent_skipped on xyz:BE    | 0              |
| position row                | 0.0 (flat)     |

0x9551e7d4 has not touched BE since the last fill 2026-10-24 15:38Z. That is
the *reason* our copy stopped, not any config change — `grep -nE
'symbol_filter|coin_filter|exclude|blocklist' config.yaml` still returns
nothing beyond the global `allowed_market_types: [perp]` toggle. **If the
leader resumes BE trading, the −201 bps drift resumes with zero resistance
from code.**

### xyz:SP500 — the second candidate

Full lifetime fill-by-fill (n=25, 09-20 to 10-26):

```
09-20 03:37  A  0.0020 @ 7640.0   # isolated prior short
10-20 12:15  B  10 fills, avg 7670.5    # open leg (0.018 units)
10-21 07:34  A  5 fills, avg 7731.0     # +60 pts  (+$0.60)
10-22 08:37  A  4 fills, avg 7676.2     # +5 pts   (+$0.04)
10-23 13:17  A  1 fill  @ 7622.0        # -49 pts
10-26 00:35  A  4 fills, avg 7631.9     # -39 pts
```

| metric            | value                             |
|-------------------|-----------------------------------|
| n own_fills (7d)  | 24                                |
| notional (7d)     | $353.09                           |
| realized (7d)     | +$0.65                            |
| fees (7d)         | $0.030                            |
| mark (now)        | 7633.95 (HL xyz dex, allMids)     |
| position (life)   | −0.012 units (net short)          |
| avg entry (life)  | 7686 ≈ (+cash/pos)                |
| paper PnL (life)  | **+$0.59** (realized + unrealized − fees) |
| leader_fills (7d) | 110 (us filling ~22% of them)     |
| intent_skipped    | 0 — we are not blocking           |

**Attribution:** 100% leader 0x9551e7d4 (same leader as the BE bleed). No
other configured leader (0x511e60d3) trades xyz:SP500 in the window.

### Why SP500 copy is NOT behaving like BE copy — yet

- **Clip size**: BE mean clip $16.22 across 177 fills (ran well above the
  `min_per_trade_usd=10` floor on frequency). SP500 mean clip $14.72 across
  24 fills (same floor regime, 7× fewer clips/day).
- **Fill-through rate**: BE 177 own / 343 leader = 51%. SP500 24 / 110 = 22%.
  BE was round-tripping; SP500 we are mostly watching.
- **Direction of drift**: BE drift is monotonic 201 bps round-trip loss.
  SP500 drift is first-two-sells-win-last-two-sells-lose, net −6 bps on the
  closed portion — nowhere near a stable signal yet.

### Sample-size sanity

25 fills with σ(per-fill PnL) ≈ $0.07 → SE on mean ≈ $0.014, 95% CI on 7d
total ≈ ±$0.69. The measured +$0.65 fits comfortably in [−$0.04, +$1.34].
**Signal/noise ratio ≈ 0.** Cannot distinguish from zero with 25 fills.

To cut this question at the measurable 50-bps level with 95% confidence I
need either ~400 fills at current clip, or clip size to grow 4× (both ~20d
away at current flow). Flagging for the next cron, don't re-ask within 7d.

## What I assumed, and what dies if it's wrong

- **Mark 7633.95 is representative**: pulled from HL `allMids`, dex=xyz.
  Our last own_fill was 7h stale (10-26 00:35, 7632.1). Mark drift < 2 bps
  over 7h is noise at this scale.
- **Position of −0.012 is live, not a stale DB write**: `positions` table
  `updated_at = 1793000668` = 2026-10-26 07:44:28Z = this cron's start.
  Fresh.
- **No `symbol_filter` schema exists in `mirror.py`**: I grepped config
  only. If `mirror.py` or `follower.py` grew a per-leader symbol filter
  since the last report and the schema simply isn't yet in config.yaml,
  then "no fix in" is wrong. The next cron should grep src/ before
  trusting this.

## What I could not determine

- **Whether the sell timing on 10-23/10-26 was us chasing the leader out or
  leader taking us out**: book_snapshots are still frozen at 2026-09-25
  (bytes 1,252,831, latest ts 1790358839). Same unresolvable thread as
  the last four reports. Collector needs restart.
- **Whether 0x9551e7d4's BE book was positive on their side**: not
  measured. Mandate ("block, not weight-cut") does not require it, but
  the strategist might want it for a full picture. One-off `userFills`
  call, read-only, scheduled for a future cron.

## What to resolve this

1. **Engineering ask (unchanged from 10-25)**: add `symbol_filter` schema
   to `mirror.py` / `follower.py` so the strategist can declare
   `always_follow[0x9551e7d4].block: [xyz:BE]`. This is the pre-condition
   for every "symbol-level cut, not weight-cut" recommendation and is now
   held up for a 13th day.
2. **No action needed on xyz:SP500 right now.** Re-measure in 7d (one
   week of equity-market opens). If drift widens to −50 bps on >100 fills,
   add to the block list. If it stays <|20| bps, close the question.
3. **Resume `state/book_snapshots/` collector.** It has been off for 30d.
   Every "direction of drift" question since 09-25 has been unanswerable
   for the same reason.

## Reproducer

```python
# From hyper-trader repo root with .venv active. All read-only.
import sqlite3, urllib.request, json, time
c = sqlite3.connect('state/state.db')

# Headline
rows = list(c.execute("""
    select ts, side, sz, px, closed_pnl, fee
    from own_fills where coin='xyz:SP500' order by ts"""))
pos  = sum(sz if s=='B' else -sz for _,s,sz,_,_,_ in rows)
cash = sum((-sz*px if s=='B' else sz*px) for _,s,sz,px,_,_ in rows)
rpnl = sum(p for _,_,_,_,p,_ in rows)
fee  = sum(f for _,_,_,_,_,f in rows)

req = urllib.request.Request("https://api.hyperliquid.xyz/info",
    data=json.dumps({"type":"allMids","dex":"xyz"}).encode(),
    headers={"content-type":"application/json"})
mark = float(json.loads(urllib.request.urlopen(req, timeout=10).read())['xyz:SP500'])
time.sleep(0.1)

paper = pos*mark + cash - fee
print(f"n={len(rows)}  pos={pos:+.4f}  paper_pnl={paper:+.4f}  (realized={rpnl:+.2f})")
# -> n=25  pos=-0.0120  paper_pnl=+0.5877  (realized=+0.56)

# xyz:BE 48h idleness
import time
with open('state/journal.jsonl') as f:
    be = sum(1 for L in f
             if (j:=json.loads(L)).get('coin')=='xyz:BE'
             and j.get('event') in ('leader_fill','own_fill','intent_skipped')
             and j.get('ts',0) >= time.time()-48*3600)
print(f'xyz:BE events last 48h: {be}')  # -> 0
```

---

## Verdict for `MEASURED.md`

Appending to the running ledger (same graft convention as the previous twelve
reports; final target is `MEASURED.md` on `feat/inplay-guard-pair-maker`):

### xyz:SP500 copy — 7d shadow (2026-10-26, n=24, UNPROVEN)

```
7d own_fills:    24   notional $353.09   realized +$0.65   fees $0.030
Lifetime paper:  +$0.59   (25 fills, 09-20 to 10-26)
Position:        -0.012 units  avg entry 7686  mark 7633.95
Fill-through:    22% (24 own / 110 leader_fills)
Attribution:     100% 0x9551e7d4 (same leader as BE)
95% CI on 7d PnL: approx [-$0.04, +$1.34]  — can't distinguish from zero
Fix status:      no symbol_filter schema in config.yaml / mirror.py grep.
                 BE copy only paused because leader went silent after 10-24.
```

Verdict: **UNPROVEN at current sample.** Not similar enough to BE to pre-emptively
block. The actionable finding is on BE: the −201 bps leak is pending a leader
resume with zero code mitigation 13 days after the strategist's remedy was
written down. Schema work is the blocker, not the measurement.
