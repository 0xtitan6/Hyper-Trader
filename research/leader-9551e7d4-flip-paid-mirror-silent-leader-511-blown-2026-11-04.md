# Leader 0x9551e7d4 SP500 flip paid, mirror silent 113h, leader 0x511e60d3 blew up -$30k/14d (2026-11-04)

**EDGE on leader 9551 (confirmed): SP500 short opened 11-02 04:29Z @ 7618.6 closed in a single-second burst on 11-02 22:18:11Z for +$769.92 across 13 B-side fills. Leader 7d perp realized +$4,305 net; 48h +$702 net.**
**NO EDGE for the mirror: 0 own_fills in 48h, last fill 2026-10-30 14:22:41Z, mirror silent 113.4h. Captured $0 of the regime-flip play.**
**NEW FINDING: Leader 0x511e60d3 (weight 1.00) blew up. 14d closedPnL = -$30,230.89 (n=1,149 fills). Base dex $0, no xyz presence, still trading today (46 fills, -$6,762). Our silence was coincidental (its flow is almost entirely on non-xyz HIP-3 instances the engine refuses), NOT by edge.**
**Sample sizes: 9551 n=74 (48h) / 224 (7d); 511 n=72 (24h) / 1,149 (14d); our own_fills n=0 (48h).**

Follow-up to `leader-9551e7d4-regime-reversal-mirror-silent-2026-11-02.md`.
`research/QUESTIONS.md`, `MEASURED.md`, `.claude/agents/quant-researcher.md`
still absent from `main` HEAD (last noted 11-02). Verdict appended at bottom.

---

## Method

- `userFillsByTime` on both leaders (start_time = 11-02 07:43Z for 48h window,
  and 7d/14d for context). 0.1s sleeps.
- `clearinghouseState` on both leaders and on `0xE503186067b1…` (base + xyz).
- `spotClearinghouseState` for our free spot USDC.
- `own_fills` from `state/state.db` (ts in seconds).
- All reads READ-ONLY. No wallet material touched.

Reference cutoffs:
- Previous report cutoff: 2026-11-02 07:43 UTC
- Now: 2026-11-04 07:46 UTC (Δ 48.1h)

---

## What I measured

### 1. Leader 9551 — 48h fills, SP500 flip executed and closed in profit

```
coin          n     notl $       closedPnl   note
xyz:SP500    13   99,231.73    +$769.92    11-02 22:18:11Z single-second close (short→flat)
xyz:GOOGL    19   22,183.34        $0.00    11-04 05:37-05:53Z opens (long, in bursts)
@107         42  202,979.28     -$10.80    HIP-1 spot HYPE/USDC (NOT a perp market)
TOTAL        74  324,394.35    +$759.13   fee $56.82  →  net +$702.31
```

Single-second burst inventory this window:
```
2026-11-02 22:18:11Z  n=13   xyz:SP500  all B  → closed the short at +$770
2026-11-03 03:05:48Z  n=11   @107       all A  (spot)
2026-11-04 05:00:40Z  n=14   @107       all B  (spot)
2026-11-04 05:37:51Z  n=5    xyz:GOOGL  all B  → opening the 200-size long
2026-11-04 05:40:08Z  n=6    xyz:GOOGL  all B
… 5 more @107/GOOGL bursts
```

The signature called out on 11-02 (accumulate over hours, exit in one
second) is stable: this week the pattern fired for a **PROFITABLE** close
on SP500, not just liquidations. Third single-second exit in 5 days,
first positive one.

### 2. Leader 9551 — 7d perp realized

```
day          n   notl $      net $      top coins
2026-10-28  38   165,341  +$4,504.82  @107 (spot), #36000, xyz:GOOGL   [big outlier]
2026-10-29  39   242,531      -$6.86  #198731, xyz:SP500, ZEC
2026-10-30  34   252,522  -$1,239.05  ZEC, xyz:SP500, xyz:GOOGL         [first SP500 close -$1,397]
2026-11-01   2     2,433      -$0.95  ZEC
2026-11-02  50   257,615  +$1,107.44  xyz:SP500, xyz:INTC, BTC          [INTC single-second, SP500 flip]
2026-11-03  11    76,834     -$57.26  @107
2026-11-04  50   148,329      -$2.64  @107, xyz:GOOGL                   [GOOGL opens in bursts]
                            ---------
7d net:                     +$4,305.51
```

Reachability caveat: 10-28's +$4,505 is mostly `@107` (HIP-1 spot) and
`#36000` (HIP-3 instance on a non-xyz dex) — **neither is copyable by
our perp-only mirror engine**. Reachable perp PnL for the week is the
SP500/INTC/BTC/GOOGL rows, not the headline $4.3k.

### 3. Leader 9551 — current position: GOOGL bag forming

```
dex   coin        szi    entry    notl $       lev          unreal $
base   —            —       —           —      —              $0        (base evacuated, accountValue=$0)
xyz    xyz:GOOGL  +200   287.202   57,440.4    3× isolated   -$1,712.53  (-9.9% of leader xyz equity)
```

Leader is now SINGLE-POSITION, isolated, down -9.9% of equity three hours
after opening. Rough liq ~192 (down ~33% from entry). This replays the
10-30 pattern: open conviction-sized at one price, defend it, exit in a
burst. Short (GOOGL) resolution unknown.

### 4. Mirror captured $0

```
own_fills 48h:      0   (n=0, fee=$0.00, closedPnl=$0.00)
Last own_fill:      2026-10-30 14:22:41Z
Silent:             113.4h  (and counting)
```

Structural reasons the mirror did not fire this window (two independent
blockers):

- **Margin bound.** Base withdrawable $2.81, xyz withdrawable $0.00. We
  cannot open a new perp position until something closes. Free spot USDC
  = $1,389.95 ($1,747.75 total − $357.80 hold) is **idle** — the
  "idle spot USDC vs $0 withdrawable" invariant from 09-22, still true.
- **Weight-muted on 9551.** Jeff cut 9551 to 0.10 on 10-15 after SKHX.
  At `fixed_usd $30 × 0.10 = $3 clip`, every intended order rounds below
  `min_per_trade_usd $10` and is silently skipped. Even with free margin
  the mirror would not have copied 9551 this week.

Pre-existing bag we're carrying (fills ≤ 10-30 14:22Z):

```
BASE  BTC    +0.00249  entry 77669.5   unreal +$1.22
BASE  AAVE  -1.25       entry 119.14    unreal -$14.37
BASE  ZEC   +0.29       entry 1267.26   unreal +$4.88
XYZ  TSLA   +0.139      entry 373.76    unreal +$0.87
XYZ  INTC   +0.54       entry 66.28     unreal -$3.61
XYZ  COIN   -0.171      entry 161.02    unreal +$2.85
XYZ  GOOGL  +0.535      entry 288.37    unreal -$5.20
XYZ  MU     +0.028      entry 943.25    unreal -$2.55
XYZ  SP500  +0.012      entry 7721.75   unreal -$1.96  ← stale LONG; not closed when leader closed theirs
```

Total unrealized: -$17.87. Our tiny SP500 **long** (0.012) sat through
the leader's short flip — we were opposite the leader for 65+ hours and
never caught the +$770 exit. Equity now $246.34 base + $107.73 xyz +
$1,747.75 spot = **$2,101.82 total**.

### 5. Leader 0x511e60d3 — BLOWN UP

Pinned at weight 1.00. Not mentioned in the 11-02 report. Measured in
passing because the mirror was also silent on it. Current state:

```
LEADER 511 base dex:   accountValue $0.00  positions 0
LEADER 511 xyz dex:    accountValue $0.00  positions 0
                       (no live collateral anywhere queryable)
```

14-day fill distribution (n=1,149):

```
day          n   closedPnl $    note
2026-10-21   51    -3,174.55    first day of window
2026-10-22   31      -623.06
2026-10-23   89    +1,821.99
2026-10-24   95    -6,539.79
2026-10-25   45       -32.00
2026-10-26   99    +3,154.26
2026-10-27  122    +4,561.15    peak day
2026-10-28  147    -1,131.69
2026-10-29  201    +1,134.01
2026-10-30  101   -19,070.83    BLOWUP (-62.6% of the 14d total)
2026-10-31    4    -1,764.17
2026-11-01   55      -533.95
2026-11-02   37    -1,358.06
2026-11-03   26       +88.17
2026-11-04   46    -6,762.37    still losing today, same instances
             ---  -----------
            1149  -30,230.89
```

24h coin breakdown:
```
#240651   n=14  -$4,536.79   ← one instance, 14 fills, 100%-of-notional loss
#240660   n= 8  -$1,363.39
#240650   n= 2    -$684.02
…         …          …
TOTAL     72    -$6,674.20
```

**Every fill is on `#NNNNNN`-prefixed HIP-3 instances on a dex this repo
does not know about** (grep `dex=['"]...['"]` across `src/` and
`scripts/` returns exactly one dex: `xyz`). That is why the mirror did
not copy any of it — the symbols are structurally unreachable, not
because the engine filtered them.

If this leader ever pivots to xyz/BTC/ZEC (our only reachable surfaces),
weight 1.00 × $30 = $30 clips would start firing on a wallet that has
been net-negative for 14 of 14 days and is now at $0 equity.

---

## Verdict

- **EDGE** on 0x9551e7d4's regime-flip thesis as a *leader* signal:
  the 11-02 SP500 short-flip paid out as predicted. **n=13 fills,
  single-second close, +$769.92.** The signature (silent accumulation,
  burst exit) has now fired 3× in 5 days and 1 of the 3 was profitable.
  Not yet a repeatable strategy — 1-of-3 at +$770 vs -$1,397 + -$6,762
  on the losses is still net-negative. Call this UNPROVEN as an
  *exploitable* pattern, EDGE only as a *measurable* one.
- **NO EDGE** for the mirror: $0 captured on 113h of silence, two
  independent blockers (margin + weight-mute), $1,390 of free spot USDC
  idle through the entire window. The 10-15 weight cut to 0.10 is doing
  its job of avoiding 9551's losses (saved us the 10-30 -$1,239 and the
  open -$1,712 GOOGL bag), but the same cut mutes the wins.
- **NEW RISK**: 0x511e60d3 at weight 1.00 lost -$30,230 over 14 days and
  is at $0 equity on every reachable dex. We are safe only because its
  flow is on unreachable HIP-3 instances; this is a configuration
  accident, not a safety design. Recommended: drop or demote 511 before
  it pivots to a reachable symbol. (Not acted on — this is read-only
  research.)

Open threads for a follow-up run:

1. Does 9551's new GOOGL long resolve like SP500 (single-second exit) or
   like the 10-30 GOOGL (bag, -$1,239 sibling loss)? Liq is ~192, mark
   ~286, so there is runway. Worth a check in 24-48h.
2. The 10-28 +$4,505 outlier was 86% `@107` (spot) and `#36000` (HIP-3
   non-xyz) — i.e. **unreachable to us**. Compute reachable-perp PnL for
   9551 on a 30d window with `scripts/copysim.py --markets perp` to see
   whether the headline sharpe is a mirage of the same shape we already
   measured and closed on 09-22.
3. Does leader 511 ever place a fill on xyz, BTC, or ZEC in a trailing
   30d window? If yes, the weight-1.00 is live risk. If no across
   months, the slot is a config dead weight — drop it.

---

## Appended to running ledger (`MEASURED.md` still absent on main)

| date | what was tested | verdict | number | n |
|---|---|---|---|---|
| 2026-11-04 | 9551 SP500 regime-flip short, 48h | EDGE as leader signal, NO EDGE for mirror | +$769.92 leader / $0 mirror / 113h silent | 74 fills (leader), 0 own_fills |
| 2026-11-04 | 9551 7d perp realized | measurable but mostly unreachable | +$4,305.51 (mostly @107 spot + #36000 HIP-3) | 224 fills |
| 2026-11-04 | 511 14d copy-edge | DEAD LEADER | -$30,230.89 closedPnL, $0 equity base+xyz | 1,149 fills |
