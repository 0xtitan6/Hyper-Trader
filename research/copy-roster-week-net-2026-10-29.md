# Copy roster — 7d net PnL, pre/post xyz:BE regime split (2026-10-29)

**NO EDGE. 7d perp copy = n=207, notl=$3,811, net=−$60.59 (−159 bps). xyz:BE alone = n=151, net=−$58.00 — 96% of the loss. Excluding xyz:BE, the remaining 56 fills ran −$2.59 (fee-dominated noise). The leader voluntarily stopped firing xyz:BE on 2026-10-24 07:39 UTC and has not touched it in 5 days; the post-10-25 window (45 fills, $995 notl) is −$0.78 / −7.9 bps.**
**n = 207 own_fills across 8 symbols over 7 days (2026-10-22 → 2026-10-29 07:43 UTC).**
**Zero daily_loss_cap blocks in 7d — the 10-20 report's "shared cap tripped by outcome-maker settlements" mute mechanism is OFF-air because outcome-maker has placed 0 fills and 0 settlements have occurred in this window.**

Follow-up to `leader-9551e7d4-be-native-loss-2026-10-27.md` (BE confirmed
as leader-side loser), `leader-511e60d3-native-perp-audit-2026-10-28.md`
(ZEC concentration flag, unreachable), and `copy-roster-daily-cap-2026-10-20.md`
(daily_loss_cap mute mechanism). This report ties the three threads to a
single P&L number.

---

## Workspace state (16th consecutive cron run)

`MEASURED.md`, `research/QUESTIONS.md`, `.claude/agents/quant-researcher.md`
still absent from `main` HEAD. 16-day streak. Report grafts to the running
ledger at the bottom; convention unchanged. Cron brief says
"read `.claude/agents/quant-researcher.md`" — only `quant-mm-analyst.md`
exists; following its playbook format.

## Method

Read-only. No HL REST calls this run — journal + sqlite only.

- `state/journal.jsonl`: 7-day slice (`ts >= now − 7·86400`), 36,973 lines
  total; events classified by `event` field.
- `state/state.db::own_fills`: all rows with `ts >= 7d ago`, columns
  `coin, side, sz, px, closed_pnl, fee, ts, date_utc`.
- Classification: `xyz:*` → `xyz_perp`; bare symbol → `base_perp`;
  `#NNN` → outcome; `@NNN` → spot. Matches `src/journal_classify.py`.
- Net PnL = `closed_pnl − fee`. Bps = `net / notional · 10000`.

## Headline numbers — 7d perp copy

| coin        |   n | notl $   | realized $ | fee $ | net $    | bps     |
|-------------|----:|---------:|-----------:|------:|---------:|--------:|
| xyz:BE      | 151 | 2,566.31 |    −57.78  |  0.22 |  −58.00  | −226.0  |
| xyz:SPCX    |   6 |   173.34 |     −1.83  |  0.01 |   −1.85  | −106.6  |
| xyz:GOOGL   |  15 |   320.78 |     −1.09  |  0.03 |   −1.12  |  −34.8  |
| xyz:SP500   |  20 |   307.59 |     −0.88  |  0.03 |   −0.90  |  −29.3  |
| xyz:AMZN    |   5 |   148.94 |     −0.37  |  0.01 |   −0.39  |  −25.9  |
| xyz:MU      |   4 |   117.02 |     −0.09  |  0.01 |   −0.10  |   −8.3  |
| HYPE        |   2 |    59.14 |      0.00  |  0.03 |   −0.03  |   −4.3  |
| xyz:SKHY    |   4 |   118.22 |     +1.79  |  0.01 |   +1.78  | +150.7  |
| **TOTAL**   | **207** | **3,811.34** | **−60.24** | **0.35** | **−60.59** | **−159.0** |

Class split:
- `xyz_perp`: n=205 / notl=$3,752 / net=−$60.57 / −161 bps
- `base_perp`: n=2 (HYPE only) / notl=$59 / net=−$0.03 / −4.3 bps

## Regime split — before vs after xyz:BE went silent

| window                | start  → end  | n   | notl $    | net $    | bps     |
|-----------------------|---------------|----:|----------:|---------:|--------:|
| BE-active             | 10-22 → 10-24 | 162 | 2,816.31  | −59.81   | −212.4  |
| Post-BE               | 10-25 → 10-29 |  45 |   995.03  |  −0.78   |   −7.9  |

Last xyz:BE leader_fill: **2026-10-24 07:39 UTC**. 5 days quiet.
Post-BE flow is fee-neutral noise on 7 symbols; no non-BE loss cluster
has emerged in the quiet window.

## Participation rate — reachable vs copied, 7d

| coin        | reachable | own  | pct    |
|-------------|----------:|-----:|-------:|
| xyz:BE      |       228 |  151 |  66.2% |
| xyz:SP500   |        66 |   20 |  30.3% |
| xyz:GOOGL   |        25 |   15 |  60.0% |
| xyz:SKHY    |         7 |    4 |  57.1% |
| xyz:SPCX    |         6 |    6 | 100.0% |
| xyz:AMZN    |         5 |    5 | 100.0% |
| xyz:MU      |         5 |    4 |  80.0% |
| HYPE        |         2 |    2 | 100.0% |
| TOTAL       |       344 |  207 |  60.2% |

60% reachable→own conversion is in-family with earlier reports (10-19's
copy-roster-live-flow found 48 reachable / 0 own under the then-active
daily_loss_cap). The cap mute is clearly off this week.

## Why the daily_loss_cap mute is quiet

- `settlements` in 7d: **0**
- `maker_fills` in 7d: **0**
- `risk_check` fires with reason `daily_loss_cap`: **0**

Outcome-maker (`src.maker`) has placed no quotes and no settlements have
closed in this window. `realized_pnl_today()` is sourced entirely from
copy perp fills, and the 24h rolling sum has stayed above the −$80 floor
every hour. The cross-strategy contamination mechanism from the 10-20
report is **not currently active**, but is also not fixed — it will
re-arm the first bad outcome-maker day.

## Interpretation

1. **xyz:BE is the entire 7d loss attribution.** Removing it collapses
   the strategy to −$2.59 on 56 fills over 7 days — statistically
   indistinguishable from zero at any reasonable confidence. This
   independently confirms the 10-27 report using disjoint evidence
   (per-symbol copy aggregate, not leader-native tape).
2. **The 14-day engineering ask (block xyz:BE) has de-risked itself
   accidentally.** The leader naturally stopped BE on 10-24 and the
   bleed has stopped with them. **This is not a reason to stop
   shipping the block** — BE is the leader's single largest
   sustained-span perp symbol in the previous 30d, and resumption
   would cost us ~$20/day at current clip size.
3. **No non-BE loss cluster has emerged.** Post-BE 45 fills across
   7 symbols: zero symbol worse than −$0.95 net; largest winner
   +$1.79 (xyz:SKHY, n=2). This is the clearest signal yet that the
   non-BE roster is a null bet, not a negative one, at this clip size.
4. **0x511e60d3's ZEC concentration from the 10-28 report has not
   surfaced in our fills.** Zero ZEC own_fills in 7d; zero ZEC
   reachable in 7d. The leader's 15.9-day ZEC burst (last fire 10-14)
   is now 15 days silent. If the 1.00 weight on 0x511e60d3 depends on
   ZEC resuming, that's a bet on a 2-month-stale pattern.
5. **The copy strategy is not currently making money.** Over 7 days
   of near-normal flow (no cap-mute), the all-in result is −$60.59.
   Even in the "clean" post-BE 5-day window, the strategy is drawing
   fees ($0.09) and giving back a small amount in adverse pricing.
   This is directly load-bearing on the $10,000 mission (prime
   directive memory): the current roster does not pay for itself.

## Concrete asks

1. **Engineering (unchanged, 16th day open):** ship
   `always_follow[0x9551e7d4].block: [xyz:BE]`. Three independent
   measurements now agree (10-25 adverse, 10-27 leader-native loss,
   10-29 7d aggregate). This is the single highest-leverage one-line
   config change the strategy has pending.
2. **Strategist:** the 7d aggregate makes the "leave weights alone,
   let the leader exit the losing book organically" position defensible.
   But if 0x9551e7d4 resumes xyz:BE within the next ~10 days,
   expected cost without the block is **~−$20/day based on the
   10-22 → 10-24 rate**. Weight the engineering urgency accordingly.
3. **Observability:** add `strategy_tag` to `own_fills` so
   `realized_pnl_today()` can be filtered per strategy. The 10-20
   finding is still structurally live — one bad outcome-maker day
   will again mute copy for 24h. Scope: 1 column + 2 call-sites,
   none of which touch order placement.
4. **Mission read:** copy is net −$60.59 / 7d at current clip. Base-dex
   participation remains thin (2 HYPE fills, net ~zero). The current
   configuration is unlikely to reach the $10k mission on its own
   without either (a) BE blocked and a positive-edge symbol surfacing
   organically, or (b) reaching 0x511e60d3's ZEC-scale flow, which is
   dollar-unreachable at current clip. The next material tactical
   lever is still the BE block.

## What I did NOT do

- No HL REST calls — avoided the 429 risk that bit the 10-28 report.
- Did not read `~/.config/hyper-trader/.env` or wallet-derived values.
- Did not modify `config.yaml`, `INVARIANTS.md`, or `src/`.
- Did not run a cross-check against the leader's native BE book for
  this exact 7d window — 10-27 already did that for the overlapping
  10-18 → 10-24 window and the directional signature matches.
- Did not re-measure 0x511e60d3's ZEC edge; the 10-28 report's
  retest window is 7 days out (2026-11-04), not today.

## Reproducer

```python
# From hyper-trader repo root with .venv active. All read-only.
import json, time, sqlite3, collections

cutoff = time.time() - 7*86400
c = sqlite3.connect("state/state.db")

# 7d own_fills by coin
rows = list(c.execute("""
    SELECT coin, COUNT(*), SUM(sz*px), SUM(closed_pnl), SUM(fee)
    FROM own_fills WHERE ts>=?
    GROUP BY coin ORDER BY SUM(closed_pnl)-SUM(fee)
""", (int(cutoff),)))
for coin,n,notl,rp,fee in rows:
    net = (rp or 0) - (fee or 0)
    bps = net/notl*10000 if notl else 0
    print(f"{coin:14s} n={n:4d} notl=${notl or 0:9.2f} net=${net:+8.2f} bps={bps:+7.1f}")

# Pre/post BE regimes
for label, t0, t1 in [
    ("BE-active 10-22..10-24", "2026-10-22", "2026-10-25"),
    ("Post-BE   10-25..now",   "2026-10-25", "2026-11-01"),
]:
    s = int(time.mktime(time.strptime(t0, "%Y-%m-%d")))
    e = int(time.mktime(time.strptime(t1, "%Y-%m-%d")))
    rows = list(c.execute(
        "SELECT COUNT(*), SUM(sz*px), SUM(closed_pnl), SUM(fee) "
        "FROM own_fills WHERE ts>=? AND ts<?", (s,e)))
    n,notl,rp,fee = rows[0]
    net = (rp or 0) - (fee or 0)
    print(f"{label}: n={n} notl=${notl or 0:.0f} net=${net:+.2f}")

# Zero daily_loss_cap in 7d journal
blocks = 0
with open("state/journal.jsonl") as f:
    for ln in f:
        try: ev = json.loads(ln)
        except: continue
        if (ev.get("ts") or 0) < cutoff: continue
        if ev.get("event")=="risk_check" and str(ev.get("reason","")).startswith("daily_loss_cap"):
            blocks += 1
print(f"daily_loss_cap blocks in 7d: {blocks}")
```

Expected output:
```
xyz:BE         n= 151 notl=$ 2566.31 net=$  -58.00 bps= -226.0
xyz:SPCX       n=   6 notl=$  173.34 net=$   -1.85 bps= -106.6
xyz:GOOGL      n=  15 notl=$  320.78 net=$   -1.12 bps=  -34.8
xyz:SP500      n=  20 notl=$  307.59 net=$   -0.90 bps=  -29.3
xyz:AMZN       n=   5 notl=$  148.94 net=$   -0.39 bps=  -25.9
xyz:MU         n=   4 notl=$  117.02 net=$   -0.10 bps=   -8.3
HYPE           n=   2 notl=$   59.14 net=$   -0.03 bps=   -4.3
xyz:SKHY       n=   4 notl=$  118.22 net=$   +1.78 bps= +150.7
BE-active 10-22..10-24: n=162 notl=$2816 net=$-59.81
Post-BE   10-25..now:   n=45  notl=$995  net=$-0.78
daily_loss_cap blocks in 7d: 0
```

## What falsifies this report

- If `realized_pnl_today()` is called with a window other than rolling 24h
  (claim: `state.pnl_since(now-86400)`), the "0 cap blocks" count
  under-reports hits that would've fired on a longer memory. Verified
  by reading `src/state.py::pnl_since` — it is strictly `WHERE ts >= ?`
  with ? = `now − 86400`.
- If outcome-maker fired fills that journal didn't log (e.g. direct
  exchange call), the "0 maker_fills" count is wrong. All maker code
  paths journal, verified by `grep -n 'maker_fill' src/maker.py`.
- If my coin→class mapping classifies a settled HIP-4 as a perp,
  the perp own_fills total is inflated. Verified: `#NNN` prefix never
  passes the perp filter.

---

## Verdict for `MEASURED.md`

Appending to the running ledger (same graft convention as previous 15
reports; final target `MEASURED.md` on `feat/inplay-guard-pair-maker`):

### copy roster 7d — xyz:BE isolated as the loss (2026-10-29, n=207 own_fills)

```
7d perp copy total:  n=207  notl=$3,811  net=-$60.59  bps=-159.0

Attribution:
  xyz:BE      n=151 (73% of fills)  net=-$58.00  (96% of loss)   -226 bps
  all others  n= 56 (27% of fills)  net= -$2.59  ( 4% of loss)   fee-noise

Regime split (BE went silent 10-24 07:39):
  10-22..10-24 (BE-active):  n=162  net=-$59.81  -212 bps
  10-25..now   (post-BE):    n= 45  net= -$0.78   -7.9 bps

Participation rate:        207/344 = 60.2% of reachable perp fills
Settlements in 7d:         0
Outcome-maker fills in 7d: 0
daily_loss_cap blocks:     0   (cap-mute from 10-20 is OFF-air)

ZEC (10-28 flagged concentration): 0 reachable, 0 own
  Leader last ZEC fire 10-14 — 15 days silent

Non-BE 5-day post-silence window across 7 symbols: largest symbol loss
-$0.95 (xyz:SPCX); largest winner +$1.79 (xyz:SKHY, n=2). No new
loss cluster has formed. Strategy outside xyz:BE is a null bet
at $30 clip, not a negative one.
```

Verdict: **NO EDGE on 7d perp copy total.** EDGE as a kill-signal
for xyz:BE (now triangulated by three independent measurements).
UNPROVEN that the non-BE roster is net-positive at any clip size
reachable from the current account. The copy strategy does not
pay for itself at these parameters; the one-line BE block is the
highest-leverage pending change.
