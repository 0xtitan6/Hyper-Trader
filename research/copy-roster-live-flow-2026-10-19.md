# Copy-roster live flow — are our two always_follow leaders paying anything? (2026-10-19)

**NO EDGE. 5-day live copy flow = 3 reachable perp own_fills (xyz:SPCX round-trip only),
+$0.45 realized total, against 65 leader_fills on xyz:BE and 13 on xyz:SP500 that the
engine refused to mirror. n=3 own_fills in 120h (0.6/day).**

---

## Context — the file this cron brief points at is not on `main`

- `.claude/agents/quant-researcher.md` is missing on `main`. Lives on
  `feat/inplay-guard-pair-maker` (last touched 2026-09-22, commit `7e6878b`).
- `research/QUESTIONS.md` and top-level `MEASURED.md` are also only on that branch.
- I read the brief and queue out of `git show feat/inplay-guard-pair-maker:…`.
- The historical OPEN queue's first 4 questions have been answered in untracked
  reports already landed on `main` (barrier-lag-2026-09-28, oil-lag-2026-09-24,
  copysim-outcome-audit-2026-09-26, …). The queue is stale.
- With no `QUESTIONS.md` to work the top of, I picked the one bite-sized quant
  question the previous cron (`strategist-2026-10-18.md`) left open at the
  bottom of §2 — "if the leader stays sub-$100 next cycle, drop to 0.5" — and
  measured the actual copy flow from the current roster. That is the number
  the next strategist run needs.

Pre-registered as a measurable Y/N against a stated decision rule.

---

## What I measured

### Live state (per-dex `clearinghouseState`, 11 dexes each)

```
0x511e60d3: TOTAL acctValue=$0.00  totalNtlPos=$0.00
  (flat across base, xyz, flx, vntl, hyna, km, abcd, cash, para, mkts, io)

0x9551e7d4: TOTAL acctValue=$6,024.80  totalNtlPos=$23,485.00
  xyz: xyz:BE  szi=+100.0000  upnl=+$1,676.79
```

Change vs 10-18 strategist report:
- 0x511e60d3: $33.60 → $0.00 on xyz. Full decapitalization.
- 0x9551e7d4: $26,592 → $6,024 on xyz. SP500 short closed (+$535 realized at
  10-19 03:08 UTC), BE long topped up 86 → 100 shares, ~$21k withdrawn (not a
  loss — realized was positive).

### 5-day engine journal, same two leaders

```
leader_fill  xyz:BE     n=65   (0x9551e7d4)
leader_fill  xyz:SP500  n=13   (0x9551e7d4)
leader_fill  xyz:SPCX   n=11   (0x511e60d3)
own_fill     xyz:SPCX   n=3    (0x511e60d3) — only reachable perp fills in 5d

intent_skipped  "leader_closing_we_are_flat"  n=46   (all xyz:BE and xyz:SP500)
```

Every single xyz:BE and xyz:SP500 leader_fill routed to
`leader_closing_we_are_flat` — we weren't in the position, so there was
nothing to mirror. Why we weren't in it: BE and SP500 opens predate our
journal window; the ones *inside* the window (BE top-up 10-18 22:16–22:18,
n=32 leader_fills) still produced zero own_fills. Primary suspect is the
clip-floor interaction the 10-18 strategist report flagged explicitly:

```
weight 0.10 × fixed_usd $30 = $3 clip, below min_per_trade_usd=$10 → signal rejected
```

That was a *predicted* second-order outcome of cutting 0x9551e7d4 to 0.10.
This report confirms it in production: the leader opened 15 fresh BE shares
in a 2-minute window on 10-18 22:16-18 and we didn't fire. The weight cut is
operating as a mute, not a sizing control.

### 5-day own_fill PnL across all markets

```
reachable perp:  n=3    closed=$+0.45
outcome:         n=239  closed=$-127.25
```

Outcome-maker is a separate strategy (not copy-driven). Copy engine's
contribution in 5 days: **+$0.45 on n=3 fills, all xyz:SPCX**.

### Live config confirmed

```yaml
discovery.leader_weights:
  0x9551e7d4: 0.1
  0x511e60d3: 1.0
discovery.always_follow: [0x9551e7d4, 0x511e60d3]
sizing.fixed_usd: 30
sizing.min_per_trade_usd: 10
risk.max_dex_exposure_usd: 750     # bumped from 500 in e1cadda, post 10-18 report
risk.max_total_exposure_usd: 1200  # bumped from 800
```

The 10-18 strategist report assumed `max_dex_exposure_usd=500`; it's now 750.
Does not change this cron's conclusion — we're clip-floor-bound on 9551 and
leader-dead on 511, neither reaches the dex cap.

---

## What I assumed, and what breaks if the assumption is wrong

- **Journal is complete for the window.** `ps`-check and `state/main.log` tail
  (not opened in this cron — read-only budget) implicitly assumed. If the
  engine was down for part of the 5d, the "n=0 own_fills on BE/SP500" is
  overstated. Mitigation: 46 `intent_skipped` events spread across 10-18 13:47
  to 10-19 03:08 show the engine WAS processing leader_fills, so it was alive.
- **`leader_closing_we_are_flat` is a correct read.** If positions were held
  outside the engine's view (per the HIP-3 reconcile bug class in
  `INVARIANTS.md` §1,4), skips would be spurious. Not re-litigated here —
  `reconcile-blind-to-hip3` memory is marked RESOLVED 09-19.
- **$3 clip < $10 floor is the mute mechanism.** Not independently verified
  from source (`src/mirror.py:527` per `[[weight-scales-clip-size]]` memory
  claims weight-is-clip-multiplier). If instead the mute is a different filter
  (symbol filter, cap-pin, etc.), the recommendation changes to "diagnose the
  skip path" first. Fast falsifier: temporarily set weight to 0.4 at next
  strategist cycle and watch for own_fills.

## What I could not determine

- **Why 0x511e60d3 decapitalized $33 → $0 on xyz.** They moved into outcome
  markets (#71860, #132751) with the $27 realized on 10-18 — not a
  withdrawal, a rotation into a surface we structurally can't copy
  (`[[copysim-counted-unreachable-flow]]`).
- **Whether 0x9551e7d4 withdrew $21k or lost it off-strategy.** $20.6k of
  xyz equity gone, +$535 realized in the same window. Shortfall is consistent
  with a transfer, not a loss, but I didn't query `userNonFundingLedgerUpdates`
  to prove it. Doesn't affect the recommendation — their on-exchange roster
  position is BE +100, that's what we'd be copying.

## What it would take to resolve the open piece

Set `0x9551e7d4` weight back to 0.4 for one strategist cycle (6h), measure
own_fills on BE/SP500/SPCX/anything else. If still zero at 0.4 ($12 clip,
clears the $10 floor), the mute is NOT clip-floor and we need to dig into
`mirror.py`. If own_fills > 0, confirms the floor hypothesis.

---

## Verdict / recommended strategist actions

**Both members of `always_follow` are producing effectively zero reachable
copy flow at current weights:**

| leader     | 5d own_fills | 5d realized | leader 5d realized | status |
|------------|-------------:|------------:|-------------------:|--------|
| 0x9551e7d4 | 0            | $0.00       | +$535 (SP500 close)| MUTED (clip-floor) |
| 0x511e60d3 | 3 (SPCX)     | +$0.45      | +$27 (incl. unreachable outcomes) | TERMINAL ($0 account) |

**Recommended for next strategist cycle (Quorra owns the actual diff):**

1. **Drop `0x9551e7d4` from `always_follow`.** At 0.10 weight they're already
   muted; removing them frees a discovery slot without changing live
   behavior. If a future screen shows them back on the leaderboard with
   reachable flow, re-admit at an executable weight (≥0.34 clears the clip
   floor per `[[leader-screening-two-traps]]` arithmetic).

2. **Drop `0x511e60d3` weight 1.00 → 0.5** or de-list entirely. Strategist
   10-18's own conditional ("sub-$100 next cycle → 0.5") triggers at $0.00.
   The $0.45 reachable PnL on the SPCX round-trip is noise; the leader's
   residual activity is outcome markets we can't trade.

3. **Replace, don't just prune.** Both discovery slots now empty + 2
   always_follow leaders both terminal = no copy engine. If the engine is
   worth keeping on, a fresh leader screen is overdue (last full sweep was
   `[[leader-pool-exhausted-aug16]]`, 60 days ago).

If no fresh screen produces executable leaders, the strategist-grade finding
is **the copy strategy itself is producing +$0.45 / 5 days**, which is below
the operational cost of running it. Case for shuttering copy and leaving the
account on outcome-maker only.

---

## Reproducer

```python
import urllib.request, json, time
def post(p):
    r = urllib.request.Request("https://api.hyperliquid.xyz/info",
        data=json.dumps(p).encode(), headers={"content-type":"application/json"})
    with urllib.request.urlopen(r, timeout=20) as resp: return json.load(resp)

LEADERS = ["0x511e60d32a1fdcafb46bae7f43cfab0a87040713",
           "0x9551e7d4cd963558bb9882aecc74f549262e217f"]
DEXES = [""] + [d["name"] for d in post({"type":"perpDexs"}) if d]

for ldr in LEADERS:
    tot_av = 0.0
    for dex in DEXES:
        s = post({"type":"clearinghouseState","user":ldr,"dex":dex})
        tot_av += float(s["marginSummary"]["accountValue"])
        time.sleep(0.1)
    print(ldr[:10], f"total_acctValue=${tot_av:.2f}")
```

```python
import json, time
cutoff = time.time() - 5*86400
own_perp = [json.loads(l) for l in open('state/journal.jsonl')
            if '"own_fill"' in l]
own_perp = [e for e in own_perp
            if e.get('ts',0) >= cutoff
            and not str(e.get('coin','')).startswith(('#','@'))]
print(len(own_perp), sum(float(e.get('closed_pnl') or 0) for e in own_perp))
# -> 3 0.45
```

## Append to MEASURED.md (deferred — file not on main)

```
| date | surface | n | window | verdict |
|---|---|---|---|---|
| 2026-10-19 | copy engine, both always_follow leaders | 3 own_fills | 5d | NO EDGE — +$0.45 realized; 9551 muted by clip-floor at 0.10 weight, 511 terminal at $0 account |
```
