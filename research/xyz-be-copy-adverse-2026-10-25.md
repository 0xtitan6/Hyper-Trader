# xyz:BE copy — 7d drift measurement (2026-10-25)

**EDGE (negative). Our copy of 0x9551e7d4's xyz:BE book realised −$57.78 across a flat round-trip of 7.01 shares over 10-21→10-24. −201.2 bps of $2,871 copied notional, fees only 0.9 bps — the loss is adverse selection, not fees.**
**n = 177 own_fills (134 buys / 43 sells, position flat at report time); 343 leader_fills on the same book / $262,951 notional.**

Follow-up to the two most recent reports that left the mute mechanism as the open question:
- `copy-roster-live-flow-2026-10-19.md` ("5-day live copy flow = 3 reachable perp own_fills (xyz:SPCX round-trip only), +$0.45 realized")
- `copy-roster-daily-cap-2026-10-20.md` ("24h window: 48 reachable perp leader_fills, 0 own_fills, 11 opens blocked by `daily_loss_cap`")

Both reports said effectively "the engine is not trading". It is now.

---

## Workspace state (12th consecutive cron run)

`MEASURED.md`, `research/QUESTIONS.md`, `.claude/agents/quant-researcher.md`
still ABSENT from `main` HEAD (`191d9b8`). They live on
`feat/inplay-guard-pair-maker` tip `137f50d` (2026-09-22); PR #54 was merged
as a single commit (`447cc1b`) that did not include them. The branch pointer
needs a look before the next cron. Writing findings to `research/` and
staging a `MEASURED.md` graft at the bottom, same convention as the
previous eleven reports (`oil-lag-2026-09-24` onward).

## Question worked

Not from a queue — queue absent. Picked up the two live-flow reports' open
thread: *the 10-20 report called `daily_loss_cap` the binding mute. The
rolling-24h loss window has aged out. What is binding now, and what has
the engine been doing?*

## What I measured

Source: `state/state.db::own_fills` and `state/journal.jsonl`, 10-18→10-25.
Read-only, no HL calls (data already on disk).

### 7-day own_fills by coin

| coin        | mkt     | n   | notional   | realized | fees   |
|-------------|---------|----:|-----------:|---------:|-------:|
| #118051     | outcome |  1  |    $67.55  |  −$82.10 |  $0.04 |
| #118050     | outcome | 18  |   $167.66  |  −$69.18 |  $0.02 |
| **xyz:BE**  | **perp**| **177** | **$2,871.23** | **−$57.78** | **$0.25** |
| #114560     | outcome |  2  |    $53.24  |  −$46.86 |  $0.00 |
| #118010     | outcome | 42  | $1,285.59  |   −$8.88 |  $0.44 |
| #118020     | outcome | 35  |   $897.74  |   −$8.67 |  $0.29 |
| xyz:SPCX    | perp    |  9  |   $260.48  |   +$0.49 |  $0.02 |
| xyz:SP500   | perp    | 20  |   $292.04  |   +$0.65 |  $0.03 |
| #114540     | outcome |  2  |   $186.11  |  +$36.46 |  $0.25 |
| #114590     | outcome |  1  |   $192.00  |  +$42.09 |  $0.26 |
| **perp total** |      | **206** | **$3,423.75** | **−$56.64** | **$0.30** |
| outcome total  |      | 141 | $2,913.85  | −$137.32 |  $1.33 |

Outcome totals are mostly the 10-17/18 BAL/CLE cluster already investigated
in `outcome-maker-cross-trigger-2026-10-24.md`. **The new, previously-
unmeasured bleed is xyz:BE perp copy** — the strategist should hear about
this before the pattern 30-days.

### xyz:BE round-trip, 10-21 → 10-24

Started 10-21 (one day after the 10-20 report said "0 own_fills"), ended
flat at report time.

| day        | buys (sz / notl)  | sells (sz / notl) | realized |
|------------|------------------:|------------------:|---------:|
| 2026-10-21 | 26 / $304.9       | 0                 | $0.00    |
| 2026-10-22 | 71 / $731.9       | 4 / $405.3        | −$22.87  |
| 2026-10-23 | 37 / $427.7       | 6 / $643.5        | −$33.14  |
| 2026-10-24 | 0                 | 33 / $357.8       | −$1.77   |
| **total**  | **134 / $1,464**  | **43 / $1,407**   | **−$57.78** |

Position flat (7.01 shares cycled, buys=sells to the hundredth). Fees
$0.25 / 0.87 bps of notional. **The remaining 200 bps is drift between
our buys and our sells on the same book.**

### 24h mute mechanism (ending 2026-10-25 07:47 UTC)

`daily_loss_cap` has aged out of the rolling 24h — no risk_check rejections
in last 24h. The new mute is **`market_type`**:

- 73 leader_fills (52 from 0x511, 21 from 0x9551)
- 70 intent_skipped with `reason=market_type`
- All 70 were HIP-4 outcome markets (#168850 etc.), correctly rejected by
  `config.yaml:992 allowed_market_types: [perp]`
- 0 copy own_fills in window; the 3 own_fills are the handrule maker
  closing an xyz:SPCX round-trip (not copy)

So the live mute **is working as designed on the outcome side**. The leak
is on the side the mute is NOT blocking: perp copy on xyz:BE.

### Why xyz:BE flipped from "uncopyable" to "copying"

The 10-18 strategist report flagged xyz:BE as *"Uncopyable (leader entered
100% maker, our taker clip crosses the spread the leader is capturing)"*.
The 10-19 flow report confirmed 0 own_fills on BE in its 5-day window —
all 65 leader_fills routed to `leader_closing_we_are_flat` (we weren't in
the position, so there was nothing to mirror).

Between 10-19 and 10-21, that changed. The most likely sequence from the
journal:
1. `daily_loss_cap=-120.11` set on 10-18 by the BAL/CLE settlement
   losses, blocked opens for ~48h.
2. The rolling-24h window aged the cap out between 10-20 and 10-21.
3. First leader-BE open after that fired through risk_check on 10-21 —
   seed-opening our position.
4. From then on, every leader-BE adjustment routed to a copy mirror on an
   inventory we actually held — not `leader_closing_we_are_flat`.

I did not instrument this chain directly (no `risk_check` events show the
exact first unblocked order), so the chain above is inference. The
measured facts are: 0 own_fills on BE pre-10-21, 177 since.

## What this costs at scale

Projecting linearly: −$57.78 / 7d × 30 = **−$247 / 30d** of realised bleed
from xyz:BE copy alone. On a $4-6k account the strategist is trying to
grow, that is the hole it is currently patching every month.

The strategist's remedy for 0x9551's prior drift (SKHX → base-dex ONDO)
was a **symbol filter, not a weight cut** (`leader-9551e7d4-ondo-drift`
memory, `leader-9551e7d4-skhx-roundtrip` research). xyz:BE is the same
pattern on a different symbol. **The current fix is the same shape: block
xyz:BE at the symbol level, don't trim weight further.**

A weight cut makes it worse. `weight-scales-clip-size` memory: at
`weight=0.10` our clip is already at the `min_per_trade_usd=10` floor
(mean clip $2871/177 = $16.22). Smaller weight does nothing but reject
more opens; it does not shrink the per-fill clip.

## What I assumed, and what dies if it's wrong

- **Attribution of xyz:BE fills to 0x9551e7d4**: inferred from
  `leader_fill` events — 343 of them on xyz:BE in 7d, 100% from 0x9551.
  No other configured leader (`0x511e60d3`) touches xyz:BE. If BE copy
  were actually routed via a different leader not in `always_follow`, the
  attribution would be wrong. The journal evidence rules this out for
  this window.
- **"The loss is adverse selection, not fees"**: fees reported in the fill
  ledger are 0.25 USDC on $2,871 notional = 0.87 bps. Round-trip burns
  201 bps. If HL under-reports perp fees for the xyz dex (possible — HIP-3
  dexes have independent fee tables), the drift share shrinks. Base case:
  even at 10× under-reporting, fees ≤ 9 bps vs 201 bps drift. The
  conclusion survives.
- **Linear projection to 30d**: assumes BE flow stays comparable. 7d
  included a weekend when BE's underlying (US equities) is closed; the
  leader's BE book moved on 7 fills vs 65-98/day on perp side (see
  `copy-roster-live-flow-2026-10-19.md` daily table). A full equity week
  could 2× the clip volume, worsening the projection, not improving it.

## What I could not determine

- **Direction of the drift**: did we buy ahead of the leader (filled on
  their outgoing taker) or chase them (crossed their outgoing bid)? Would
  need per-fill book snapshot vs our price. `state/book_snapshots/` stops
  2026-09-25; this question is unanswerable from current data.
- **Whether the leader is net-profitable on their own BE book**: not
  measured. If they are losing too, "block BE" is still right. If they
  are winning, the pattern confirms maker-taker asymmetry and still
  points to blocking.
- **Cluster B counterfactual from `outcome-maker-cross-trigger-2026-10-24`**:
  needs the 2026-10-18 07:45 book snapshot. Still unresolvable (same
  reason as above). Flagged for the next cron.

## What to resolve this

1. Strategist proposes a `symbol_filters` config entry for 0x9551:
   `block: [xyz:BE]`. If the config schema does not yet support per-leader
   per-symbol blocklist, this is an engineering ask.
2. Re-measure in 7d. If xyz:SP500 is next in line (115 leader_fills, our
   20 own_fills, +$0.65 — not yet statistically distinguishable from
   zero), extend the filter.
3. Resume `state/book_snapshots/` collection so the next round can measure
   maker-taker asymmetry directly, not just infer from aggregate PnL.

## Reproducer

```python
# From hyper-trader repo root with .venv active.
import sqlite3
c = sqlite3.connect('state/state.db')

# The headline number
for r in c.execute("""
    select count(*), sum(sz*px), sum(closed_pnl), sum(fee)
    from own_fills
    where coin='xyz:BE' and date_utc >= '2026-10-18'"""):
    print(r)  # (177, 2871.23, -57.78, 0.248)

# Round-trip verification: position should be flat
pos = 0.0
for ts, side, sz in c.execute(
    "select ts, side, sz from own_fills where coin='xyz:BE' order by ts"
):
    pos += sz if side == 'B' else -sz
print(f'ending pos: {pos:.3f}')  # ~0.00
```

```python
# Leader attribution — 100% 0x9551e7d4
import json
from collections import Counter
by_leader = Counter()
with open('state/journal.jsonl') as f:
    for L in f:
        try: j = json.loads(L)
        except: continue
        if j.get('event') == 'leader_fill' and j.get('coin') == 'xyz:BE':
            by_leader[j.get('leader','?')[:12]] += 1
print(by_leader)  # Counter({'0x9551e7d4cd': 343})
```

---

## Verdict for `MEASURED.md`

Appending to the running ledger (which lives on `feat/inplay-guard-pair-maker`
— to be grafted on next merge):

### xyz:BE copy — adverse selection (2026-10-25, n=177 own_fills, 7d)

```
Round-trip:  7.01 BE shares cycled, position flat.
Realized:    -$57.78
Notional:    $2,871.23
Fees:        $0.25 (0.87 bps)
Drift:       201.2 bps per $ of notional, net of fees.
Attribution: 100% leader 0x9551e7d4 (343 leader_fills on same book).
```

Verdict: **copy of 0x9551e7d4's xyz:BE book is a reliable loser at
current config.** Projected −$247/30d. Fix shape: symbol-level block on
xyz:BE for 0x9551e7d4 (same pattern as `leader-9551e7d4-ondo-drift`).
Weight cuts do not help — clip already at `min_per_trade_usd=10` floor.
