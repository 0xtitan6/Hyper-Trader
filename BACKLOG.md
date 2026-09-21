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

## Rules for this file (added 2026-09-11, after it went wrong)

1. **A DONE item MUST carry the merge SHA that closed it.** Prose is not proof.
   Items marked DONE without one are treated as unverified.
2. **The executor runs an idempotency gate before implementing.** If the
   acceptance criteria already pass on `main`, it stops and reports
   `ALREADY DONE` instead of building. That check exists because three finished
   items were left marked READY, so the executor rebuilt the topmost one ~25
   times across 6 duplicate branches over a month while the item below it never
   started. Every run looked successful, so nothing alerted.
3. **The PM marks DONE at merge time, not later.** Merging without updating this
   file is what caused (2).
4. Before any deploy: `./scripts/preflight_deploy.sh` — asserts main, in sync,
   clean tree, exactly one engine.

---

## DONE 2026-08-15 — we mirrored a leader's EXITS as new ENTRIES

> Merged as `classify_leader_fill` in `src/mirror.py`. Left marked READY by mistake,
> which made the executor re-implement it ~25 times (4 duplicate branches) and never
> reach the item below. Process bug, not an agent bug.

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

## READY — P0 (TOP, START HERE): maker shadow harness — prove the edge BEFORE it touches money

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

**PRIORITY SURFACE — measured 2026-08-17, top-of-book from `l2Book` (NOT
`impactPxs`; impact prices are the cost to move size and overstate the quotable
spread ~4x, e.g. para:IREN reads 58.0 impact vs 58.0 TOB but xyz:GIGADEV reads
125.3 impact vs 3.2 TOB):**

```
coin            TOB spread   depth bid/ask     net vs 2x fee
para:SMCI          58.1 bps   $148k / $152k       +56.3
para:IREN          58.0 bps    $42k /  $97k       +56.3
xyz:SOFTBANK       27.4 bps    $146 / $5,134      +25.7
para:UNITREE       26.7 bps    $927 / $1,895      +25.0
PURR (base)        22.2 bps    $131 /   $240      +13.5
```

Quote `para:SMCI` and `para:IREN` FIRST — real two-sided depth, and a gross
spread ~34x our 1.72 bps HIP-3 round trip. For contrast, base perps cost 8.64
bps round trip and are frequently tighter than that.

**The thing that decides it:** these are tokenized equities. The spread may be
wide precisely BECAUSE the flow is toxic — someone arbing the real stock against
a stale perp oracle picks us off exactly when we are wrong, and 58 bps does not
cover that. Mark-outs are the only test that distinguishes "wide spread" from
"wide spread for a reason". Do not skip to a fee-vs-spread conclusion.

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

## DONE 2026-08-15 — P0c: solvency gate read base-dex equity only (INV 1)

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

## DONE 2026-08-17 — P3: realized PnL by surface (`scripts/realized_pnl.py`)

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

---

## DONE 2026-08-21 — P2: leader scoring + backtest are truncated to 2,000 fills (oldest-first)

Fixed on `fix/paginate-leader-fills`. One shared pager (`src/hl_fills.py`) now
backs `leader_score.load_metrics`, `backtest.fetch_fills` and
`scripts/realized_pnl.fetch_fills`. Verified live 2026-08-21:
`0x7177edd4` 2,000 -> **13,004** fills over 30d, both `#NNNNN` and `xyz:*`
present, 0 duplicate `tid`s; `0x9551e7d4` on an unchanged window is identical
old-vs-new (868 trades / 215 closes / net $52.85 — the $59.91 in the original
item was a 30d window that has since rolled forward, not a change from this
fix). Screen effect: `0x7177edd4` goes from the FALSE `trades=0 < 50` to the
true `holding_p50=1s < 60s` (1,832 perp trades, -$226,473 realized).

Follow-up worth an item: discovery pays up to 20 pages on ultra-HFT wallets it
will always reject. Pre-filtering on the leaderboard's own `trades` field
before scoring would drop that to near zero.

<details><summary>original item</summary>


**Problem.** `leader_score._fetch_fills` calls `userFillsByTime` with only
`startTime` and no pagination. HL caps that response at **2,000 fills and
returns them oldest-first**. For a high-frequency wallet the "30-day" scoring
window therefore only ever sees the first ~2 days of the window, and the rest
of the month is invisible.

Measured 2026-08-21 on `0x7177edd4` (leaderboard rank 2, $48,496 PnL, 30,127
trades, $4.38M volume, and genuinely funded: **$776,961 on xyz across 5
positions + $1.18M spot USDC**):

```
userFillsByTime(startTime = now-30d) -> 2000 fills, ALL of them #NNNNN
  coins: {'#10411': 475, '#10410': 398, '#10331': 351, '#10330': 311, ...}
userFills (most recent 2000)         -> xyz:UNITREE 798, xyz:CXMT 186, ...
```

`_is_perp_coin` classifies `#NNNNN` as non-perp, so with `score_perp_only:
true` the perp count is 0 and the quality filter rejects it as
`trades=0 < 50` — a wallet with 30k trades. The two windows do not even
overlap: the oldest-2000 slice and the newest-2000 slice share no coins.

**This affects the backtest too**, which is the part that matters. `src.backtest`
scored the same wallet at **0 trades / 0 closes / $0.00 net**. So we cannot
currently tell the difference between "this leader has no copyable edge" and
"we truncated the window before reaching their copyable fills". Every
`trades=0` and every low-trade-count backtest on a high-frequency wallet is
currently unfalsifiable.

**Not a claim of missed edge.** The visible slice of `0x7177edd4` is outcome
markets we do not copy; it may well be a genuine dead slot. The defect is that
the measurement cannot answer the question either way.

**Fix.** Paginate: loop `userFillsByTime` advancing `startTime` past the last
returned `time` until a page returns < 2,000 rows or the window is covered
(cap total pages, and de-dupe on `tid` — page boundaries repeat fills that
share a millisecond). Apply to `leader_score._fetch_fills` and to whatever
`src/backtest.py` uses to pull leader history — they must use the same helper,
or discovery and the backtest will disagree about what a leader did.

**Acceptance.** For `0x7177edd4` over 30d, the fill count exceeds 2,000 and
the returned coin distribution contains both `#NNNNN` and `xyz:*` fills;
`0x9551e7d4`'s existing backtest numbers (868 trades / 215 closes / +$59.91 @
$226.75 proxy) change by no more than rounding when the window is unchanged;
no fill appears twice by `tid`.

</details>

## Jev classifier for the in-play guard (proposed 2026-09-21)

`src/gamestate.is_safe_to_quote` classifies market descriptions with keyword
matching (`EVENT_TOKENS`, token-overlap on team names). It has returned a
confidently wrong answer three times:

| date | failure | consequence |
|---|---|---|
| 09-20 | `competition:`-keyed NFL waved through as "not an event market" | 8 live games quotable |
| 09-20 | "England" token-matched "New England Patriots" | reported IN PLAY at 7-0 |
| 09-20 | UFC 331 unresolvable, guard allowed it | both legs resting on finished fights |

Each was a clean-looking wrong answer, not an error — the failure mode of a bad
schema, not of a bad model.

This fits the classifier band: bounded answer space
(`quotable / in-play / unresolved`), unstructured text input, called on every
market every cycle. `TYPESAFE_API_KEY` is already in the env.

**Keep from the current design:** default to REFUSE when uncertain, and route
below-threshold cases to refusal rather than to a guess. The guard's value is
that it is wrong in the safe direction.

**Do NOT extend this to the operator health check.** That path is already a
zero-token shell script (`scripts/operator_tier1.sh`); its inputs are structured
numbers and a threshold beats a classifier there. Adding a model would be a
regression — see the 991k-tokens/day note in that file.

Blocked on: nothing. Sized: half a day. Priority: below the barrier maker and
below measuring fill rate, since the guard currently fails safe.

## Oil outcome markets — does HIP-4 lag the oil price? (proposed 2026-09-21)

Operator's idea: trade oil outcomes on Gulf/geopolitical flow. The tradeable
version drops the news half and keeps the measurable half.

`perp:xyz:CL` exists and trades (5.2% spread, 25 trades, $3,150 in 24h as of
2026-09-21). Unlike sports, oil has a **continuously observable reference** —
Brent/WTI print in real time and HL runs its own oil perp — so the question is
testable rather than speculative:

**Does the HIP-4 oil outcome market reprice BEFORE or AFTER the underlying?**

Run the same experiment that closed in-play sports (see MEASURED.md): sample the
outcome mid and the reference price together every few seconds and count which
moves first. In-play NFL came back 22 price-moves-before-score to 2 after, which
killed it. If oil comes back the other way, it is a real edge on a surface where
we can actually see the input.

Why the news angle is the weaker half: Reuters/Bloomberg latency is where
professional desks spend millions and we would be seconds behind. But we may not
need the news — if the oil PRICE moves first and the outcome market follows, the
signal is free and public.

Prerequisite: 25 trades/24h is thin. Check whether flow is real before building;
depth is not flow (see the Kosovo/Greece finding).

Blocked on: nothing. Sized: 1h to measure, then decide. Priority: after the
fill-rate read, alongside the crypto-barrier maker — both are "observable
underlying" plays and share the same repricing machinery.
