# BACKLOG.md — executor work queue

Owned by the PM (Quorra, main session). The **executor** cron picks the topmost
`READY` item, implements it on a branch, and reports. The executor **never
merges and never deploys** — the PM reviews the branch and does the cutover.

Every item must carry acceptance criteria concrete enough to be checked without
asking a question. If an item is ambiguous, the executor must stop and report
the ambiguity rather than guess: guessing on a live money system is how you get
a fix that passes tests and loses money.

**Read `INVARIANTS.md` before any change.** A change that violates an invariant
is wrong even when the tests are green.

---

## READY — P0 (TOP): we mirror a leader's EXITS as new ENTRIES

**Problem.** `_build_intent` copies the leader's fill *side* and never asks
whether that fill OPENED or CLOSED their position. When a leader buys to cover
a short, we buy and open a long — the exact opposite of what copying them means.

Verified live 2026-08-15. Leader `0x819d06c0` covering a short in `xyz:SP500`:

```
side=B  dir=Close Short  startPosition=-3.384
side=B  dir=Close Short  startPosition=-3.467
side=B  dir=Close Short  startPosition=-3.521
```

We mirrored 13 of those as BUYs and ended up **long +0.035 against the leader's
−2.801 short**. It was closed by hand at 15:56 and rebuilt itself by 18:56,
larger. Across that leader's ~1,400 recent fills: **216 `Close Short` + 253
`Close Long`** — roughly a third of everything we copy is a leader EXITING.
This is a strong candidate for the xyz realized −$87.03 (INV 10 measurement).

`grep -n 'dir' src/mirror.py` returns nothing: the field is never read.

**Acceptance criteria**
1. Classify every leader fill as OPEN / CLOSE / FLIP. **Derive it from
   `startPosition` + `side` + `sz` — arithmetic, not the `dir` string** — and
   use `dir` only as a cross-check. `startPosition` is authoritative and does
   not depend on HL's labelling staying stable.
2. Behaviour:
   - OPEN → mirror as today.
   - CLOSE → **reduce only**. If we hold nothing in that direction, SKIP with a
     distinct journal reason (e.g. `leader_closing_we_are_flat`). Never open
     the opposite side. This single rule is the fix.
   - FLIP (`Short > Long`) → close ours fully, then open the new direction.
3. Never let a CLOSE mirror increase our absolute exposure on that coin.
4. INV 4: if `startPosition` is missing AND `dir` is absent, the fill is
   UNKNOWN — skip it with its own reason rather than guessing. Do not fall back
   to today's behaviour, which is the bug.
5. Tests, each asserting order side AND `reduce_only`:
   - leader closes a short, we are flat → **no order** (the headline regression)
   - leader closes a short, we are long → reduce, never flip through zero
   - leader opens a short, we are flat → mirror short
   - leader flips short→long → close then open
   - `startPosition` absent, `dir` present → uses dir
   - both absent → skipped as unknown
6. Full suite green (currently 639). Report the count.

**Do NOT attempt target-position mirroring in this item** — that is the next
item and needs a scale definition first. Keep this surgical.

---

## READY — P0: maker shadow harness — prove the edge BEFORE it touches money

The maker on `wip/maker-hip4` has never run live. Before it does, it must be
measured — and **a naive market-maker backtest is worse than no backtest**,
because it flatters itself in three specific ways:

1. **It assumes fills.** Price touching your quote does not mean you traded —
   you are behind a queue you cannot see. A replay that fills you on touch
   invents PnL.
2. **It ignores adverse selection**, which is the entire risk of making. You
   get filled precisely when the market is about to move against you. A backtest
   that books the spread and stops has measured the good half of the trade.
3. **It ignores our own impact.** Our quote changes the book we are quoting into.

So: shadow mode against LIVE data, not a historical replay.

**Acceptance criteria**
1. Shadow runner: the maker's real quoting logic (`src/maker.py`, `dry_run=True`)
   against the live feed, submitting NOTHING. Log every intended quote with
   timestamp, side, price, size, and the book at that moment.
2. Subscribe to the venue's public trades. For each shadowed quote, decide
   whether it would plausibly have filled — and be **pessimistic**: require the
   trade to cross our price, and assume we are last in queue at that level.
   State the queue assumption explicitly in the output; it is the single
   biggest source of self-flattery.
3. **Mark-outs — this is the headline number.** For every simulated fill, record
   mid-price move at **t+1s, +10s, +60s**, signed so positive = the market moved
   our way. Persistently negative mark-outs mean we are being picked off, and
   that is a NO-GO however good the gross spread capture looks.
4. Net edge per fill = spread captured − adverse selection (markout) − fees.
   Use the REAL fee for the surface: HIP-3 measured at **0.86 bps**, base at
   **4.32 bps**. Do not assume a rebate — we are tier 0 and rebates need >0.5%
   of 14D maker volume share, which we will never have.
5. Inventory: report max and time-weighted absolute inventory, and how often it
   would have hit the configured cap. A maker that is always one-sided is a
   directional bet wearing a maker's clothes.
6. Report REALIZED terms only (INV 10), with a significance test like
   `scripts/realized_pnl.py` — n, mean, standard error, and a plain
   YES/NO on whether the sample supports a conclusion.
7. Full suite green.

**Go-live gate (PM decision, not the executor's):** positive net edge per fill
AND non-negative mark-outs at 10s AND inventory staying inside caps, over a
sample the harness itself calls sufficient. Anything less and it does not trade.

---

## READY — P0b: mirror target POSITION, not deltas (needs shadow test)

The deeper flaw behind P0. We copy *changes* when we should track *state*:
`target = leader_position_after × scale`, `order = target − ours`. That is
self-correcting — a missed WS fill, a rejected order or a reconcile hiccup gets
pulled back on the next fill instead of compounding forever.

**Blocked on a decision, not on code:** we size with a fixed $30 clip, not
proportionally, so `scale` has no natural definition yet. Getting it wrong means
fighting leaders on ENTRIES, which is worse than the current bug.

Must ship behind a shadow mode that logs intended vs actual orders against live
fills for a full session before it is allowed to trade. PM reviews the shadow
log before it goes live.

---

## READY — P0c: the solvency gate reads base-dex equity only (INV 1, 4th time)

**Problem.** `src/leaders._perp_equity_usd` calls `info.user_state()`, which
returns BASE-dex equity only. A leader whose collateral sits on a HIP-3 dex
reads **$0** and is rejected as insolvent. Verified 2026-08-15:

```
0x819d06c0   base $0.00  ->  $514 on xyz     <- our PINNED incumbent
0x9551e7d4   base $0.00  ->  $8,104 on xyz   <- the wallet the gate was built for
0x810b41bd   base $0.00  ->  $62,955 on xyz
0x2649bb08   base $0.00  ->  $15,109 on xyz
```

18–21 of 60 candidates are rejected this way. Our own pinned leader would be
rejected if it were ever unpinned — `config.yaml` warns about that, and this is
the mechanism.

**This invalidates two earlier claims** made to the PM, both from the same
misread: that `0x9551e7d4` was a "$0 equity dead slot" (it holds $8,104), and
that "44 of the top 60 have zero perp equity" (unverified — likely a base-dex
artifact). Do not cite either as established.

The gate is not useless: `0x166866a2` is genuinely empty on every dex despite
1,375 recent fills. False positives are the problem, not the idea.

**Acceptance criteria**
1. `_perp_equity_usd` sums/checks equity **per dex** via `perpDexs` +
   `clearinghouseState{user, dex}`.
2. Per INV 2, collateral is per-clearinghouse — the gate passes if **ANY** dex
   clears the threshold. Never compare a sum-across-dexes to the threshold.
3. INV 4: an unreadable dex leaves the candidate UNKNOWN → do not reject.
   Currently `None` already means "don't judge"; preserve that.
4. Re-run the 60-wallet screen and report how the selected set changes.
5. Tests: base-only equity, dex-only equity, both, unreadable dex, genuinely
   empty everywhere.
6. Full suite green (currently 639).

---

## DONE 2026-08-15 — P1: leader-drop leaves positions orphaned forever

**Problem.** `leader_exit_auto_close` fires only when a *leader exits their
position*. Removing a leader from `config.yaml` leaves everything they opened
stranded. Four such positions (JUP, JTO, AR, XMR from two dropped leaders)
accumulated since ~July and consumed **100% of base margin** — $67.64 initial,
$344 gross — blocking every signal from our *current* leaders until they were
closed by hand on 2026-08-15.

**Acceptance criteria**
1. On startup and on each leader refresh, detect open positions whose
   originator is no longer in the followed set.
2. Report them distinctly — a new journal reason (e.g. `dropped_leader_orphan`)
   and one throttled alert per coin. Do NOT auto-close: closing is a money
   action and stays with the PM/operator.
3. Positions in `risk.manual_holdings` are exempt (`xyz:SPCX`, `#1420`, `#1430`).
4. Must respect INV 4: an unreadable originator or an incomplete leader set is
   UNKNOWN, never "dropped". Test both directions.
5. Unit tests for: originator dropped, originator still followed, manual
   holding, unknown originator, empty leader set.
6. Full suite green. Report the count.

---

## DONE 2026-08-15 — P2: `discovery.min_trades: 50` analysis (verdict: leave it at 50; not the binding constraint)

**Problem.** The filter selects for trade *frequency*, which is precisely the
property that makes a wallet unprofitable to copy at our base fee tier (4.5 bps
taker). We screened 466 wallets and every high-PnL name failed on turnover or
fee-tier edge. Meanwhile a genuine low-frequency candidate at 43 trades/30d was
auto-rejected for being under 50.

**Acceptance criteria**
1. Do NOT just lower the number. Add a `--dry-run` analysis mode to leader
   discovery (or a script) that reports, for the current leaderboard, how the
   selected set changes across `min_trades` ∈ {20, 30, 50} — showing each
   candidate's turnover/mo, effective bps, p50 fill gap and perp fraction.
2. Output is a written recommendation with numbers. **Change no config.**
3. Must apply the existing screens: solvency (INV 9 / `min_leader_equity_usd`),
   fee-tier, turnover.
4. Full suite green.

---

## READY — P3: measure realized base vs xyz on a clean post-fix window

**Problem.** Judgements have been made on *unrealized* PnL (INV 10). Realized
over the full history: base **+$96.73 net**, xyz **−$89.54 net**, outcomes
**−$370.39**. But xyz only became correctly tradeable on 2026-08-15 (szDecimals,
per-dex cap, reconcile), so its history is contaminated by the broken period.

**Acceptance criteria**
1. Script that reports REALIZED PnL net of fees, split by surface (base perp /
   xyz HIP-3 / outcome), for an arbitrary `--since` timestamp.
2. Report the post-fix window (from 2026-08-15 13:47 UTC, the reconcile fix)
   separately from history.
3. Include fills count, notional, fees, effective bps per surface.
4. State plainly whether the sample is large enough to conclude anything. If it
   is not, say so — do not recommend a weight change on thin data.
5. Full suite green.

---

## BLOCKED — `_fetch_mid` has no price for HIP-3 coins

Auto-close cannot price `xyz:*` because `all_mids()` covers the base dex only.

**Do not fix this in isolation.** Until 2026-08-15 this failure was the only
thing preventing `leader_reconcile` from force-closing our entire xyz book after
it wrongly classified every position as an orphan. That misclassification is now
fixed, so this is *safe to fix* — but it must ship with proof that no live
position is currently classified `orphan` or `closed` in error. Needs a PM
decision before it moves to READY.

---

## DONE (2026-08-15)

- exposure cap blocking best leader (0 orders in 30d, $96,595 missed notional)
- sub-minimum rounding mute (leader silenced 24 days)
- HIP-3 szDecimals guess → poison cascade (5,366 blocked opens)
- startup zombie (aborted process kept PID, faked healthy to every check)
- per-dex exposure cap (40/40 blocked opens were xyz)
- leader solvency gate (44 of top-60 leaderboard wallets have $0 equity)
- reconcile zeroing HIP-3 positions (27 in one day; disabled the per-dex cap)
- unified-margin free collateral (base `withdrawable` read $0 vs $151.78 real)
- `leader_reconcile` HIP-3 blindness (tried to auto-close 6 live positions)
- dropped-leader orphan detection (P1, detect-only)
- min_trades analysis (P2 — verdict: NOT the binding constraint, leave at 50)
- WS health false-positive (P2) — all 3 subs are `userFills`, which only push on fills, so quiet leaders trip the 630s staleness threshold. 82 rebuilds on 08-15 vs ~9/day on 08-13/14. Self-heals (replays 3/3 subs), but each rebuild logs "Marked 30 snapshot fills as seen" — a leader fill landing inside the reconnect gap could be marked seen and never copied. Investigate: gate staleness on a heartbeat/allMids sub instead of fills, and verify the snapshot-seen path can't swallow an uncopied fill.
