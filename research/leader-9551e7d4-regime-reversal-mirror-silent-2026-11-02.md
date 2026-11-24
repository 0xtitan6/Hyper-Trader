# Leader 0x9551e7d4 — base-dex liquidation + SP500 long→short flip, mirror silent for 65h (2026-11-02)

**NO EDGE for the mirror. Leader realized +$344.29 net in 24h (39 fills, 5 symbols); our mirror fired 0 own_fills in the same window, 65.4h since the last fill at 2026-10-30 14:22Z. Captured: $0.**
**UNPROVEN as a sustained reversal: SP500 flip-short is 3h old at +18 bps unreal on $100k leader notional (n=13 open fills). Too young.**
**n = 747 leader fills over 14d (10-19 → 11-02 07:43Z). 24h delta: 39 leader fills across BTC, ZEC, xyz:INTC, xyz:SP500, @107 totalling $160,816 notl / +$344.29 net. Mirror delta: 0 own_fills, 0 notl, $0 realized.**

Follow-up to:
- `leader-9551e7d4-sp500-exit-and-intc-pivot-2026-10-31.md` (SP500 single-second close FALSIFIED the "replay BE" thesis; INTC pivot UNPROVEN at n=3)
- `leader-9551e7d4-sp500-regime-flip-2026-10-30.md`
- `copy-roster-week-net-2026-10-29.md`

---

## Workspace state (19th consecutive cron run)

`MEASURED.md`, `research/QUESTIONS.md`, `.claude/agents/quant-researcher.md`
still absent from `main` HEAD. Convention preserved: verdict appended to
the running ledger at the bottom of this report.

## Method

- `userFillsByTime` on `0x9551e7d4…` with `startTime = now − 14d`
  (747 fills).
- `clearinghouseState` on leader (base + xyz) and on our account
  `0xE5031860…` (base + xyz + spot). 0.5s sleeps.
- Our own_fills from `state/state.db` (ts in seconds, not ms —
  caught the first conversion error).
- No wallet material touched.

Reference cutoffs:
- Yesterday's report cutoff: `2026-10-31 07:43 UTC`
- Now: `2026-11-02 07:43 UTC`

---

## What I measured

### 1. Leader 24h fills — a full regime cycle in one window

```
coin        n    notl $        net $        bps     action
xyz:SP500  13   100,001.65    -7.78      -0.78    OPEN SHORT (new, 11-02 04:29Z)
BTC         4    27,423.59    +3.79      +1.38    CLOSE LONG (fully flat 11-02 01:09Z)
ZEC         6    17,758.92  +313.49    +176.52    OPEN+CLOSE LONG (closed 03:48Z)
xyz:INTC   14    15,302.94   +34.79     +22.73    CLOSE LONG (fully flat 11-02 06:38:53Z, single-second burst)
@107        2       328.56    -0.00      -0.07    spot
                            --------
                            +$344.29
```

The INTC close at 06:38:53Z is the *second* single-second liquidation
burst in 3 days (SP500 closed the same way at 10-30 00:15:15Z,
-$1,428). Signature is stable: accumulate over hours/days, exit in one
timestamp.

### 2. SP500 flipped: long → short in 54 hours

| event               | time                | side  | avg px   | notl        | realized |
|---------------------|---------------------|-------|----------|-------------|----------|
| First SP500 close   | 2026-10-30 00:15:15Z | long→flat | 7667.7 | $198k | −$1,397 |
| Second SP500 open   | 2026-11-02 04:29:42Z | flat→short | 7618.6 | $100k | — |
| Mark now (xyz)      | 2026-11-02 07:40Z   | short | 7604.5   | $100k open | **+$184.99 unreal** (+18.1 bps in 3h) |

Yesterday's report said "SP500 is gone." It's back on the opposite side.
The leader is now expressing bearish SP500 on a lower cost basis than
their first (losing) long.

### 3. Base-dex evacuation

Leader `clearinghouseState` on BASE now returns `accountValue = $0`.
24h ago it held BTC +0.35, ZEC +10, totalling $9,401. Today both
positions are closed and the proceeds are not sitting on base — they
either moved to xyz dex (which grew from $14,882 → $20,507, +$5,625)
or to spot USDC. Base is empty.

The copyable surface for this leader is now **100% xyz dex**.

### 4. Leader open positions now

```
base: (empty)
xyz:  xyz:GOOGL  +120    @ 293.81  unreal -$1,370  (yesterday -$1,507, mark drift)
xyz:  xyz:SP500  -13.126 @ 7618.6  unreal +$185   (NEW SHORT, 3h old)
```

GOOGL is the only continuous overhang. Everything else from yesterday
is closed.

### 5. Our mirror — silent

```
own_fills since 2026-10-31 07:43Z: n=0
last own_fill:                     2026-10-30 14:22:41Z (xyz:INTC entry)
gap:                               65.4 hours
```

Zero fills across BTC exit, ZEC exit, INTC exit, SP500 flip. Four leader
signals, four misses. The engine IS alive — `state/main.log` tail shows
WS rebuild #1873 at 07:42:18, "Selected 3/50 leaders" at 07:42:45, and
at 07:43:07 `leader_reconcile` fired 11 "Leader exit detected" ERROR
alerts (BTC, ZEC, xyz:TSLA, xyz:SP500=**flipped**, 4 outcome orphans,
xyz:MU, xyz:COIN, AAVE, xyz:INTC). The alerts fire, the trades don't.
`config.yaml: leader_exit_auto_close: false` is the gate — unchanged from
the KILL-doesn't-gate-leader_reconcile mitigation.

### 6. Our account mark-to-market (both dexes)

```
BASE  acctValue=$235.36   unreal=−$19.42
  BTC    +0.0025  @ 77,669.5   unreal $+0.77   (orig: 0x511e60d3)
  AAVE   −1.25    @   119.14   unreal $−18.20  (orig: 0x511e60d3, biggest bleed)
  ZEC    +0.29    @ 1,267.26   unreal $−1.99   (orig: 0x9551e7d4, stale after exit)

XYZ   acctValue=$118.59   unreal=+$1.11
  xyz:TSLA  +0.139    @ 373.76    unreal $+3.71   (orig: 0x511e60d3)
  xyz:INTC  +0.54     @  66.28    unreal $−0.08   (orig: 0x9551e7d4, stale after exit)
  xyz:COIN  −0.171    @ 161.02    unreal $+3.09   (orig: 0x511e60d3)
  xyz:GOOGL +0.535    @ 288.37    unreal $−3.19   (orig: 0x9551e7d4, co-held)
  xyz:MU    +0.028    @ 943.25    unreal $−1.02   (orig: 0x511e60d3)
  xyz:SP500 +0.012    @ 7,721.75  unreal $−1.40   (orig: 0x9551e7d4, WRONG SIDE of flip)

SPOT  USDC $1,748.35 (hold $359.55)

TOTAL unreal: −$18.31
  9551e7d4 lineage (4 coins):  −$6.65
  511e60d3 lineage (5 coins):  −$11.65
```

### 7. 24h regime-lag counterfactual (perp mirror hypothetical)

If our mirror had followed the leader's exit prices on 9551e7d4-origin
positions:

| coin | our size | leader exit avg | our entry | counterfactual realized | current unreal | lag cost |
|------|---------:|----------------:|----------:|------------------------:|---------------:|---------:|
| ZEC  | 0.29     | $1,277.20       | $1,267.26 | +$2.88                  | −$1.99         | **$4.87** |
| xyz:INTC | 0.54 | $66.54          | $66.28    | +$0.14                  | −$0.08         | $0.22   |
| xyz:SP500 (flip) | 0.012 → −0.012 | $7,668 close + $7,618 reopen short | $7,721.75 long | −$0.49 net (close −$0.65 + flip +$0.16) | −$1.40 long | $0.91 |

Total 24h regime-lag cost on 9551e7d4 lineage: **~$6.00**. Small in
absolute dollars because our clip is $30 and the lineage is only ~$280
notional, but **100% of the leader's +$344.29 realized ran past us**.

---

## Reproduction

```python
import urllib.request, json, time, datetime
LEADER = "0x9551e7d4cd963558bb9882aecc74f549262e217f"
start = int(time.time()*1000) - 14*86400*1000
req = urllib.request.Request("https://api.hyperliquid.xyz/info",
    data=json.dumps({"type":"userFillsByTime","user":LEADER,"startTime":start}).encode(),
    headers={"content-type":"application/json"})
fills = json.loads(urllib.request.urlopen(req, timeout=20).read())
# Split by 2026-10-31 07:43Z and sum closedPnl - fee per coin.
# Then clearinghouseState (base + xyz) on leader and on our account.
# own_fills ts is in SECONDS, not milliseconds — do not re-use the ms cutoff.
```

---

## Verdict for `MEASURED.md`

Appending to the running ledger (19th consecutive run with no central
file; same graft convention):

### leader 0x9551e7d4 — regime reversal + mirror silence (2026-11-02, n=747 leader fills / 14d, mirror n=0 own_fills / 24h)

```
PRIOR THESIS (from leader-9551e7d4-sp500-exit-and-intc-pivot-2026-10-31):
  "The post-regime fee-neutrality holds for the 7th consecutive day…
   112 perp copies, 7 days, net −12 cents. The mirror is no longer
   leaking on this leader; it is also doing nothing."

OUTCOME 24h later:
  Mirror did nothing again — EXACTLY nothing: zero own_fills for 65.4h.
  Leader meanwhile closed BTC/ZEC/INTC for +$352 realized, then flipped
  SP500 (long → short) at $7618.6 after exiting long at $7668 54h earlier.
  Base dex now empty on leader; xyz grew to $20.5k.
  leader_reconcile at 07:43:07 fired 11 "Leader exit detected" ERROR
  alerts (BTC, ZEC, TSLA, SP500=flipped, MU, COIN, AAVE, INTC + 4 outcome
  orphans). Alerts fire, trades don't — leader_exit_auto_close:false is
  still gating per the known mitigation.

VERDICT: 
  EDGE at the LEADER level — +$344.29 net on $160,816 notl in 24h.
  NO EDGE at the MIRROR level — we captured $0.00 of it.
  UNPROVEN whether the SP500 short will hold a trend; 3h, +18 bps unreal,
  n=13 open fills.

The gap between the two lines is the headline. The leader is tradeable;
our copy is not reacting at the pace the leader is trading at. 65h with
zero own_fills includes four actionable leader events plus a reversal.

Leader 24h closed PnL by coin:
  BTC         n= 4   $27,424    +$3.79    +1.4 bps     (closed long)
  ZEC         n= 6   $17,759  +$313.49   +176.5 bps    (open+close long, big win)
  xyz:INTC    n=14   $15,303   +$34.79   +22.7 bps     (closed long, single-sec burst)
  xyz:SP500   n=13  $100,002    -$7.78    -0.8 bps     (opened short, young)
  @107        n= 2      $329    -$0.00    -0.1 bps     (spot)
  TOTAL       n=39  $160,817  +$344.29   +21.4 bps

Our mirror 24h (perp only):
  n=0  notl=$0  net=$0.00  (65.4h silent gap)

Our mirror mark-to-market NOW (both dexes):
  9551e7d4 lineage perps: ZEC/INTC/SP500/GOOGL  unreal -$6.65
  511e60d3 lineage perps: BTC/AAVE/TSLA/COIN/MU/… unreal -$11.65
  TOTAL account perp unreal: -$18.31  (BASE $235 + XYZ $119 = $354 perp eq + $1,748 spot USDC)
  AAVE short is 70% of the drag; it predates this window.

Regime-lag cost (if we had closed at leader's exit prices on our 9551 positions):
  ZEC   lag ~$4.87    INTC lag ~$0.22    SP500 lag ~$0.91    total ~$6.00/24h
  Trivial in dollars (clip is $30, lineage is $280 notional) but the
  mechanism — alert without execution — is the structural cap on this
  copy strategy's ceiling.
```

Operational implications (unchanged flavor, newly sharpened):
1. The pending xyz:BE symbol-filter block is still correct, and the
   leader has not re-engaged BE in 9 days — so the ask has no live
   relief value for the next few days but the engineering stays valid.
2. **The leader_exit_auto_close gate is the knob that keeps the mirror
   silent on exits.** It was turned off deliberately (KILL doesn't gate
   leader_reconcile, see memory). Flipping it back on without the
   `_risk_check` guard reintroduces the earlier failure mode. The right
   next move is `_risk_check`-gated auto-close on confirmed leader
   exits, not a blanket flag flip — tracked in BACKLOG as "LeaderReconciler
   auto-close with risk check".
3. The SP500 flip (short at $7618.6) is tactically interesting as a
   fresh entry, but n=1 regime change on this leader isn't a signal to
   front-run. Wait for either (a) the short to close with realized
   gain or (b) a second flip in a different name before treating this
   as a repeated pattern.
4. "Source a new leader" (open since 10-30) is still open. 0x9551e7d4's
   24h shows the leader IS tradeable — our copy path is not. Either
   fix the copy path (auto-close + possibly auto-flip) or move capital
   to a leader whose fills we actually mirror within seconds.
