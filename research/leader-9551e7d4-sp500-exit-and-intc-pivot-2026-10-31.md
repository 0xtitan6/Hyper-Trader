# Leader 0x9551e7d4 — SP500 voluntary exit, INTC pivot (2026-10-31)

**FALSIFIED. The 10-30 "xyz:SP500 is replaying xyz:BE" thesis does not hold at a 10-day bar. The leader closed the entire xyz:SP500 long in a single-second 9-fill burst on 2026-10-30 00:15:15Z at $7,667-$7,668, realizing −$1,396.55 (fees $15.43) in that one burst and −$1,427.52 over the full 2d active-trading window. No SP500 fills in the 32h since. The leader rotated to xyz:INTC on 10-30 14:20Z (230 long @ $66.38, $15.3k notl), now −$395 unrealized at 17.4h. The BE-shaped slow-accumulation pattern did not recur: SP500 active life was 2 days, not 10.**
**UNPROVEN as a going-forward kill signal: xyz:INTC is 17h old, n=3 leader fills, $15.3k notl. Too thin to call anything.**
**n = 786 leader fills over 14d (10-18 → 10-31 07:43Z). Incremental delta since the 10-30 07:43Z report cutoff: 5 leader fills (3 symbols: INTC/@166/@107, −$1.21 net on $15.7k notl); our mirror delta: 3 own_fills, all xyz:INTC, $35.79 notl, −$0.0031 net.**

Follow-up to:
- `leader-9551e7d4-sp500-regime-flip-2026-10-30.md` (SP500 "regime flip" EDGE-as-warning, UNPROVEN-as-kill-signal at 6d)
- `leader-9551e7d4-be-native-loss-2026-10-27.md` (BE −241 bps native)
- `copy-roster-week-net-2026-10-29.md` (post-BE 7d, perp copy fee-neutral)

---

## Workspace state (18th consecutive cron run)

`MEASURED.md`, `research/QUESTIONS.md`, `.claude/agents/quant-researcher.md`
still absent from `main` HEAD. The brief references them; they don't exist.
The 17 prior runs appended their verdicts to the running ledger at the
bottom of each report. Convention preserved below.

## Method

Single `userFillsByTime` on leader
`0x9551e7d4cd963558bb9882aecc74f549262e217f`, `startTime = now − 14d`
(and a 72h sub-pull for the SP500 close burst). 0.5-0.6s sleeps between
requests. Two `clearinghouseState` reads (base + xyz dex). Our mirror
side via `state/state.db::own_fills`. No wallet material touched, no
log line contains anything derived from the key.

Reference cutoffs:
- Regime cutoff: `2026-10-24 07:39 UTC` (last xyz:BE fill — same cutoff
  used by the 10-29 and 10-30 reports)
- Yesterday's report cutoff: `2026-10-30 07:43 UTC`
- Now: `2026-10-31 07:43 UTC`

---

## What I measured

### 1. SP500 exit — the single-second close burst

```
2026-10-30 00:15:15Z   A 0.922  @ 7668.0   Close Long   rp=$   -49.56  fee=$0.55
2026-10-30 00:15:15Z   A 0.018  @ 7668.0   Close Long   rp=$    -0.97  fee=$0.01
2026-10-30 00:15:15Z   A 13.041 @ 7668.0   Close Long   rp=$  -701.06  fee=$7.78
2026-10-30 00:15:15Z   A 0.658  @ 7668.0   Close Long   rp=$   -35.37  fee=$0.39
2026-10-30 00:15:15Z   A 0.607  @ 7667.9   Close Long   rp=$   -32.69  fee=$0.36
2026-10-30 00:15:15Z   A 0.002  @ 7667.8   Close Long   rp=$    -0.11  fee=$0.00
2026-10-30 00:15:15Z   A 0.903  @ 7667.7   Close Long   rp=$   -48.81  fee=$0.54
2026-10-30 00:15:15Z   A 0.13   @ 7667.6   Close Long   rp=$    -7.04  fee=$0.08
2026-10-30 00:15:15Z   A 9.601  @ 7667.5   Close Long   rp=$  -520.93  fee=$5.72
                                                        -------- -----
                                                        $-1,396.55 $15.43     net $-1,411.98
```

Fully-closed in one timestamp. Leader has not touched SP500 since. The
10-30 report's `n=9 / $198k / -$1,411.98 / -71.1 bps` line is this exact
burst.

### 2. Rotation timeline across tokenized-stock books

| coin       | first fill         | last fill          | active window | n fills | realized |
|------------|--------------------|--------------------|--------------:|--------:|---------:|
| xyz:BE     | 10-18 13:47        | 10-24 07:38        |         5.7 d |     343 | −$6,798  |
| xyz:SP500  | 10-19 03:08        | 10-30 00:15        |        10.9 d |     155 | −$575 realized through 10-23 + −$1,428 10-29/30 burst (= cycle −$2,003 by my split; the 10-30 report had −$2,722 using a wider pre/post boundary) |
| xyz:GOOGL  | 10-28 20:22        | 10-30 03:28        |         1.3 d |      13 | −$2 realized + still −$1,507 unreal (120 long @ $293.81) |
| **xyz:INTC** | **10-30 14:20**  | **10-30 14:22**    |     **2 min** |   **3** | **−$1 realized + −$395 unreal (230 long @ $66.38)** |

The rotation cadence is tightening: BE was 10 days of accumulation into
one book, SP500 was 2 days of active trading inside a wider "I'm in this
name" window, GOOGL/INTC are shorter still. The 10-30 report framed
SP500 as the "next BE". It isn't — it's the midpoint of a decay in
hold-time, not a repeat.

### 3. Leader 14d PnL — reframed on all markets, not just perps

Yesterday's report split only `assetPositions` perps. The leader's
`userFillsByTime` for the same 14d includes outcome markets (`#...`) and
spot (`@...`), which were silently excluded. Adding them back:

```
POST (10-24 07:39Z → now, 7d) across all markets:
                               n=319    notl=$1,257,227    net=$+1,214.71 (+9.7 bps)

  xyz:SP500     n=  40   $859,580   $-2,722.25   -31.7 bps
  #173460       n=  37   $  5,829   $  -675.80  -1159.3 bps
  #165380       n=  10   $    172   $  -144.44  -8381.6 bps
  @107          n=  46   $113,770   $   -37.72    -3.3 bps
  BTC           n=   4   $ 27,409   $   -10.66    -3.9 bps
  xyz:GOOGL     n=  13   $ 35,257   $    -2.41    -0.7 bps
  xyz:INTC      n=   3   $ 15,267   $    -1.19    -0.8 bps
  #198731       n=  17   $  5,125   $   +22.44   +43.8 bps
  #165381       n=  14   $  2,738   $  +142.35  +520.0 bps
  ZEC           n=  20   $ 42,716   $  +171.41   +40.1 bps
  #36000        n= 110   $148,779   $+4,507.23  +302.9 bps  ← ignored by yesterday's framing
```

Perp subset (what we can copy) was −$2,564 / 77 fills. Outcome + spot
subset (what we structurally can't copy via mirror) was +$3,779 / 242
fills. The leader is NET POSITIVE in the post-regime 7d — the "losing
book" narrative only holds on the subset we read.

**This does not change our mirror math.** Mirror runs on perps only and
mirrors nothing on binary outcomes or spot. Our 7d perp copy was still
−$0.12 on $2,474 notl (fee-neutral) with xyz:BE excluded. But it does
change the "the leader is bleeding, should we drop them?" answer:
**the leader is making money, we just can't follow where**.

### 4. Our mirror — 24h delta

Only 3 own_fills since the 10-30 07:43Z report cutoff, all
xyz:INTC entry at 10-30 14:20Z through our follower:

```
coin         n   notl $   net $
xyz:INTC     3   35.79    -0.0031   (-0.9 bps)
```

Position: 0.54 long xyz:INTC @ $66.37, −$0.08 unrealized. Current cap
state unchanged.

7-day post-regime cumulative (same window as yesterday + today):

```
                       n fills   notl $     net $
Our perp (10-24..now)   112      2,474     -0.12   (-0.5 bps, fee-neutral)
Our PRE  (10-17..10-24) 203      3,338    -56.04   (xyz:BE drove 99%)
```

The post-regime fee-neutrality holds for the 7th consecutive day with
one more day of evidence. 112 perp copies, 7 days, net −12 cents. The
mirror is no longer leaking on this leader; it is also doing nothing.

### 5. Open positions on leader (now)

```
base dex (accountValue $9,400.71):
  BTC   +0.35   @ 78,311.8    unreal $-357.3
  ZEC   +10     @ 1,257.3     unreal $+113.7

xyz dex (accountValue $14,882.13):
  xyz:INTC  +230   @ 66.38    unreal $-395.6   <-- new (10-30 14:20Z)
  xyz:GOOGL +120   @ 293.81   unreal $-1,507.2 <-- yesterday was -$1,478
```

Leader has moved more capital into xyz dex since yesterday ($10,236 →
$14,882, +$4,646). The GOOGL overhang grew. INTC is the only new perp
position opened in 24h.

---

## Reproduction

```python
import urllib.request, json, time
LEADER = "0x9551e7d4cd963558bb9882aecc74f549262e217f"
start = int(time.time()*1000) - 14*86400*1000
req = urllib.request.Request("https://api.hyperliquid.xyz/info",
    data=json.dumps({"type":"userFillsByTime","user":LEADER,"startTime":start}).encode(),
    headers={"content-type":"application/json"})
fills = json.loads(urllib.request.urlopen(req, timeout=20).read())
# Split pre/post 2026-10-24 07:39Z and sum closedPnl - fee per coin.
```

---

## Verdict for `MEASURED.md`

Appending to the running ledger (18th consecutive run with no central
file; same graft convention):

### leader 0x9551e7d4 — SP500 voluntary exit + INTC pivot (2026-10-31, n=786 fills / 14d)

```
PRIOR THESIS (from leader-9551e7d4-sp500-regime-flip-2026-10-30):
  "xyz:SP500 is replaying xyz:BE one week earlier — monitor for 10d sustained."

OUTCOME 24h later:
  SP500 fully closed 10-30 00:15:15Z in a single-timestamp 9-fill burst.
  SP500 cycle: 2d active trading, -$1,428 realized. No further SP500 fills.
  Leader rotated to xyz:INTC (10-30 14:20Z, 230 long @ $66.38, -$395 unreal at 17h).

VERDICT: FALSIFIED on the 10d-sustained-loss replay. Leader rotates faster now;
         BE's 10d accumulation signature is not generalizing.

Rotation hold-time trend:
  xyz:BE     10-18..10-24 → 5.7d → -$6,798 realized → voluntary silence
  xyz:SP500  10-19..10-30 → 10.9d  (2d active trade, 6d accumulation,
                                     1-second exit) → -$2,003 cycle PnL
  xyz:GOOGL  10-28..10-30 → 1.3d → -$2 realized + -$1,507 unreal (held)
  xyz:INTC   10-30 14:20..now → 17h open → -$395 unreal (held)

Leader 7d POST-regime (10-24..now, all markets):
  n=319  notl=$1.26M  net=+$1,215  (+9.7 bps)
  Perp subset:  n= 77  notl=$965k  net=-$2,564  (-26.6 bps)
  Outcome+spot: n=242  notl=$290k  net=+$3,779  (+130 bps)
  <-- yesterday's report framed only the perp subset; the leader is net
      profitable on the full book, we just can't copy where the gain is.

Our mirror same 7d (perp only):
  n=112  notl=$2,474  net=-$0.12  (fee-neutral, 7th consecutive day of this)

Our mirror 24h delta (since 10-30 07:43Z):
  n=3   notl=$36    net=-$0.00   (all xyz:INTC entry @ $66.37)

Open leader positions NOW:
  base: BTC +0.35 @ 78,311 unreal -$357   (yesterday was -$31; BTC dropped)
  base: ZEC +10   @ 1,257  unreal +$114   (yesterday was -$48; ZEC up)
  xyz:  INTC +230 @ 66.38  unreal -$396   NEW
  xyz:  GOOGL +120 @ 293.81 unreal -$1,507 (yesterday -$1,478; still bleeding)
```

Operational implications (unchanged from yesterday; no new asks):
1. The pending xyz:BE symbol-filter block ask is still correct — BE is the
   only one of these books where leader-side bleed survived at scale on
   the subset we actually copy. Adding SP500 to the block list is now
   unnecessary; it is gone.
2. The symbol-filter should still be designed to accept new entries in
   one line (xyz:INTC may qualify after 5-7 more days of our-side
   fills; too early at n=3).
3. The 10-30 "the next tactical lever is sourcing a new leader" remains
   open. The leader's net-positive 7d (hidden on the outcome/spot side)
   makes "drop them" a weaker call than it looked yesterday, but it
   doesn't make our perp mirror profitable either — fee-neutral is the
   ceiling until a profitable perp book emerges on their side.
