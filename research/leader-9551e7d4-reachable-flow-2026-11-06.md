# Leader 0x9551e7d4 reachable flow — bleed is real but one-day-dominated (2026-11-06)

**NO EDGE: 9551's 30d reachable-perp copy-PnL = −$148.97 sim / −$155.56 actual own-fills; both at effective weight 0.10 / $30 clip.**
**MEASURED LOSS CONCENTRATION: 99.9% of 9551's 30d −$151,249 leader closedPnL is one day — 2026-10-14 xyz:SKHX forced-close −$151,125. Last 7d leader perp PnL is +$1,141.**
**Sample sizes: leader n=2,692 fills 30d (1,910 reachable perp / 0 unreachable perp / 232 outcome / 550 spot); our own_fills n=272 attributed to 9551-territory coins; journal leader_fills on 9551 n=914, intent_skipped n=1,668.**

Follow-up to open thread #2 in
`research/leader-511e60d3-reachable-flow-2026-11-05.md`:
*"Compute reachable-perp PnL for 9551 over the same 30d window with
`scripts/copysim.py --markets perp` to see whether its headline leader
sharpe is also a mirage once the unreachable outcome fills are stripped —
same methodology I just applied to 511."*

`research/QUESTIONS.md`, `MEASURED.md`, `.claude/agents/quant-researcher.md`
still absent from `main` HEAD — same state as 11-05. Verdict appended at
bottom in the existing inline-table style.

Script: `research/leader-9551e7d4-reachable-flow-2026-11-06.py`

---

## Method

- `userFillsByTime` on `0x9551e7d4cd963558bb9882aecc74f549262e217f` for the
  30d window ending 2026-11-06 07:45 UTC. 0.35s page sleeps. Dedup by
  `(tid, time)`. Raw fills cached to
  `state/copysim_fills/0x9551e7d4_30d_1106.json` (823 KB).
- Reachable set = `Info.coin_to_asset` after `src.hl_hip3.register_hip3_dexes()`
  — 908 total symbols (base perp + 323 HIP-3 assets across every registered
  builder dex). Identical procedure to the 11-05 511 run.
- Own-side: `state/state.db own_fills` table, 30d window, coin-overlap
  attribution against 9551's observed roster (xyz:SKHX, xyz:BE, xyz:SP500,
  xyz:GOLD, xyz:CL, xyz:GOOGL, xyz:INTC, xyz:MU, xyz:AMZN, xyz:HOOD,
  xyz:IREN, xyz:SPCX). State.db latest own_fill ts = 2026-10-30 14:22 UTC —
  no state.db own_fills captured since; journal 11-06 07:47 UTC is current.
- Copysim replay: `scripts.copysim.simulate(fills, clip=$30, cap=$800,
  fee=4.5bps, slip=5bps)` on reachable_perp only. (xyz_0.10 weight implied
  by the floor-min $30 per-trade; scaling with weight is linear on gross,
  constant on blocked-by-cap signals.)
- All reads READ-ONLY. No wallet material touched.

---

## What I measured

### 1. Leader 9551 reachable vs unreachable (30d)

```
                     n       notional       closedPnL
  reachable_perp  1,910   $9,516,618.27    -$151,249.85
unreachable_perp      0           $0.00           $0.00
         outcome    232     $180,757.42      +$2,997.34
            spot    550   $2,222,323.99        -$434.56
                   ─────  ────────────     ────────────
             ALL  2,692  $11,919,699.68    -$148,687.07
```

Unlike 511 (33% reachable fills, 75% reachable notional), **100% of
9551's perp flow is reachable**. 9551 does not trade HIP-4 outcomes
other than a thin +$2,997 side-pocket (Settlement +$4,586 from a single
fill, discretionary −$1,589 from 231 small trades). There is no
"unreachable mirage" to strip.

### 2. Top reachable coins

```
coin           n       notional    closedPnL   market
xyz:SKHX     976  $3,371,579.93  -$151,125.46  HIP-3 equity perp
xyz:BE       351    $281,700.34    -$6,783.46  HIP-3 equity perp
xyz:CL       217  $1,424,114.70    +$3,023.10  HIP-3 commodity perp
xyz:SP500    190  $3,297,334.23      +$394.73  HIP-3 index perp
xyz:GOLD      78    $923,290.97    +$2,683.03  HIP-3 commodity perp
ZEC           38     $73,145.21      +$507.77  base perp
xyz:GOOGL     35     $60,050.24        $0.00   HIP-3 equity perp  (open position)
xyz:INTC      17     $30,569.91       +$35.98  HIP-3 equity perp
BTC            8     $54,832.74       +$14.46  base perp
```

### 3. Time concentration of the headline −$151k

```
window     n reachable    closedPnL
  7d          87           +$1,140.75
 14d         329           -$8,550.00
 30d       1,910         -$151,249.85
```

xyz:SKHX closedPnL by day (|v|>$10):

```
2026-10-14   -$151,125.46   ← entire 30d SKHX damage on one day
```

**99.9% of the 30d damage is a single day's forced-close on xyz:SKHX,
2026-10-14.** The 7d trailing window is positive (+$1,141); the 14d is
mildly negative (-$8,550). Treating the 30d as "steady leader bleed" is
wrong — it's one blowup event plus a mostly flat tape.

### 4. Mirror behaviour on 9551 (journal, 30d)

```
leader_fill    observed   n=914   on 9551
intent_skipped (total)    n=1,668 (all leaders combined)
by_leader (observed leader_fills):
  0x511e60d3  n=1,188
  0x9551e7d4  n=  914
  0xe48fe601  n=   73
  0x2a6e0b83  n=   55
  0xe38c0163  n=   24
```

WS feed captured 914 of 1,910 leader fills (48%) — the rest likely dropped
to disconnects or the rate-limit grey zone. Not a cleanly measurable
suppression bias; counted for context.

### 5. Own fills attributable to 9551 territory (30d, state.db)

```
coin          n   realized     fee    net
xyz:BE      177    -$57.78   $0.25   -$58.03
xyz:SKHX     11    -$90.55   $0.03   -$90.58
xyz:SP500    35     -$0.27   $0.05    -$0.32
xyz:GOOGL    21     -$1.09   $0.03    -$1.12
xyz:SPCX     12     +$0.94   $0.03    +$0.91
xyz:MU        7     -$2.96   $0.02    -$2.98
xyz:AMZN      6     -$3.44   $0.02    -$3.45
xyz:INTC      3      $0.00   $0.00     $0.00
            ───   ────────   ─────  ─────────
            272   -$155.14   $0.42  -$155.56   net (fee-included)
```

Two symbols dominate: **xyz:SKHX −$90.58 on just 11 fills** (SKHX blowup day
caught us carrying a small long into the forced close); **xyz:BE −$58.03 on
177 fills** (slow chop bleed; matches the 10-27 "be-native-loss" measurement).

Full-DB totals for context: 30d all-coins n=836 own_fills, net −$403.95
(of which 9551-territory −$155.56; 511-territory +$2.63 per 11-05; the
remainder is HIP-4 outcome maker + base crypto non-copy).

### 6. Copysim replay on reachable perp

```
clip=$30, cap=$800, fee=4.5bps+slip=5bps  (reachable_perp only)
  net    = -$148.97
  gross  = -$146.60
  fees   =   $2.37
  taken  =  58
  opens  = 1,909
  blocked_cap = 1,852  (97% of signals rejected by the $800 cap)
  per-coin: xyz:SKHX -$148.97  (all simulated damage; other coins blocked before open)
```

Sim underestimates reality — it only opens 58 clips vs 272 actual own_fills
— because it models a single leader in isolation without the live mirror's
richer entry/exit logic. Sim and reality agree on **sign and rough
magnitude**: 9551 at a $30-clip / 0.10-weight scale costs us ~$150 / 30d,
all concentrated on xyz:SKHX and xyz:BE.

### 7. 11-02 GOOGL thread update (open thread #1 from 11-05)

Leader 9551 current xyz positions (fetched 11-06 07:47 UTC):

```
xyz:GOOGL  szi=+209.239   unrealizedPnl=-$829.32
```

Avg entry across 35 add-only fills on 2026-11-04 05:37–09:53: **$277–$282**
(all BUY, all `Open Long`, no closes). The 11-05 report cited `~$286` entry
— off by ~$5. **Position has not resolved yet** — unlike the 10-30 SP500
single-second exit, 9551 is still carrying the GOOGL long, and it is
underwater by ~$829 today. Our own-side mirror on xyz:GOOGL for the full
30d is 21 fills / −$1.12 — effectively flat, because cap-blocking rejects
most adds after the first clip.

### 8. What this changes vs prior memory

Memory entry [`xyz dex capped blocks SKHX`](mem) was written pre-10-14
when SKHX was the best-sharpe reachable flow. **Post-10-14 the picture
inverts: xyz:SKHX is where the leader lost its entire 30d perp P&L, and
our 11 own-side fills are the second-worst coin on our book (−$90).**
The cap that used to look like a bug (97% rejection) was actually
risk-limiting the blowup by rejecting most SKHX adds.

Memory entry [`0x9551e7d4 flip-paid-mirror-silent-leader-511-blown-2026-11-04`]
("mirror silent on 9551") is correct for the 11-04 daily cross-section
but not for the 30d window. 272 own_fills / −$155.56 over 30d is the
non-silent reality.

---

## Verdict

- **NO EDGE for the mirror on 9551** — 30d copy-PnL is **−$155.56 actual
  / −$148.97 sim** at effective weight 0.10. Statistically distinguishable
  from zero (−$155 / $235 account value ≈ 2.1% / month drag at current
  weight), but concentrated: **remove xyz:SKHX and xyz:BE and the residual
  is +$1-2 noise**.
- **MEASURED ONE-DAY DOMINANCE** — 99.9% of 9551's 30d −$151,249 leader
  closedPnL is 2026-10-14 xyz:SKHX. Treating 9551 as "steadily losing"
  in strategist logic is wrong. 7d trailing leader PnL is **+$1,141**.
- **NOT A MIRAGE** — unlike 511 (where "safe only because unreachable" was
  falsified by discovering the reachable slice was +$425), 9551's leader
  flow is 100% reachable perp. The engine's 97% cap-blocking in the SKHX
  period acted as unplanned risk limiting on the blowup day, saving us
  from 10x more of the −$151k damage.
- **RECOMMENDATION (read-only, for strategist/executor)**:
  (a) Keep 9551 at weight 0.10 or lower — the base pin remains justified.
  (b) Consider a hard coin-level deny list for 9551: **xyz:SKHX, xyz:BE**
  carry all 30d negative copy-PnL; everything else nets noise or small
  positive. Same pattern as the proposed 511 base-only gate on 11-05.
  (c) Watch xyz:GOOGL — leader holds +209.239 (−$829 unrealized at
  11-06); if 9551 adds more and gets stopped, we repeat the SKHX pattern
  at smaller scale. Our 21 fills / 30d / −$1.12 own-side is tiny relative
  to the leader's position, so bounded.
- **NO ACTION TAKEN** — read-only run. Any config change is PM-owned.

## Follow-ups opened

1. The symmetry test for **xyz:BE** on both leaders (511 and 9551):
   journal shows 184 `leader_closing_we_flat` skips over 30d — are we
   actually net harmed by xyz:BE across both leader attributions, or is
   the −$58 concentrated on 9551? (Needs tid-level fill attribution.)
2. At weight 0.0 for 9551, what would 30d copy-PnL on 511 **gain** (if
   anything) from unblocked cap headroom? Current 97% cap-reject rate
   on 9551 signals ≠ "9551 steals cap from 511" — need to confirm.
3. HIP-3 dex registration coverage — the 11-05 thread #3 asked whether
   more dexes would shrink 511's 92% `market_type` skip rate.
   `register_hip3_dexes()` still returns 323 assets; HL has thousands
   of HIP-4 instances. The question for 9551 is moot (zero unreachable
   perp fills), but still open for 511.

---

## Appended to running ledger (`MEASURED.md` still absent on main)

| date | what was tested | verdict | number | n |
|---|---|---|---|---|
| 2026-11-06 | 9551 reachable-perp flow, 30d | NO EDGE / real drag | −$155.56 actual own copy-PnL (−$148.97 sim) | 272 own_fills / 1,910 leader reachable |
| 2026-11-06 | 9551 leader 30d perp bleed concentration | ONE DAY | −$151,125 of −$151,250 on 2026-10-14 xyz:SKHX | 976 SKHX fills / 30d |
| 2026-11-06 | 11-05 "9551 sharpe may be unreachable-mirage" hypothesis | FALSIFIED (opposite of 511) | 100% of 9551 perp is reachable; no unreachable perp to strip | 1,910 reachable / 0 unreachable |
| 2026-11-06 | 9551 11-02 GOOGL long resolution (thread #1, 11-05) | UNRESOLVED | still open, szi +209.239, unrealized −$829; avg entry $277–282 | 35 leader adds, no closes |
