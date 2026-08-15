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

## READY — P1: leader-drop leaves positions orphaned forever

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

## READY — P2: `discovery.min_trades: 50` biases us toward uncopyable leaders

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
