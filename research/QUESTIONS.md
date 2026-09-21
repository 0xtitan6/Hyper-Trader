# Research queue

The `quant-researcher` cron reads this file each run and works the **topmost
unanswered** question. Edit this file to re-prioritise; do not edit the cron.

When a question is answered: move it to ANSWERED with the verdict and the file,
and append the finding to `MEASURED.md`.

---

## OPEN — work the top one

### 1. Do HIP-4 crypto barriers reprice slower than their underlying?

Eight `template:priceTouch` markets out-trade all 28 NFL markets combined
($888,708 vs $600,569 in 24h) and run 24/7 with the underlying fully observable
to us. Blocker is speed: they reprice on every BTC tick, our loop is 20 minutes.

Measure the lag the same way in-play NFL was measured (see `MEASURED.md`):
sample the barrier mid and the HL perp mark together, count which moves first
and by how long. If the barrier lags by seconds, quantify how fast a maker
would have to reprice to be safe. If it leads, it is closed — say so.

### 2. Does HIP-4 oil (`perp:xyz:CL`) lag the oil price?

Same experiment, different surface. Thin (25 trades/24h as of 09-21) — check
flow is real before building anything. Depth is not flow.

### 4. The guard cannot tell a TOURNAMENT market from a MATCH market

`template:sportsTournamentParticipant` carries only `participant:<Team>` — no
fixture, no kickoff, no opponent. `gamestate.is_safe_to_quote` resolves the team
name to their most recent FIXTURE and judges safety from that.

Measured 2026-09-21: it passed `participant:Manchester City` as safe because
City vs Sunderland had just gone Full Time. But the market is a season-long
tournament bet, not that match — right answer, wrong reasoning. And a tournament
market reprices hard on a result, so "the match just ended" is arguably the
*least* safe moment to quote it, not the safest. The book showed a 3.15% paired
edge minutes after full time, which is almost certainly compensation for exactly
that repricing.

Orders were pulled by hand. Needed: decide the correct rule for tournament
markets (they have no single fixture, but move whenever the team plays AND when
results land), and make the guard distinguish the template rather than guessing
from a team name. This is the FOURTH distinct guard hole — after competition-
keyed NFL, the England/New-England collision, and unresolvable UFC.

### 5. Why does equity not reconcile against fills? ($75 unexplained)

`scripts/equity_snapshot.py` computes equity as
`spot USDC + outcome legs + perp(all dexes) + HLP`. Measured 2026-09-21 over a
14.6h window from a 02:14:32Z baseline:

```
equity change              +$93.79
realised (userFillsByTime)  +$10.98
fees                         -$0.12
unrealised (all dexes)       +$7.87
                            --------
explained                   +$18.72
UNEXPLAINED                 +$75.07
```

No matching ledger transfer (`userNonFundingLedgerUpdates` shows only $0.19 of
tiny sends), funding is -$0.52, and the fills endpoint is time-bounded so it is
not truncation.

Component deltas: spot -$280, legs +$285, perp +$87, vault 0. The legs/spot pair
offsets (we bought legs), so the anomaly is **perp +$87 against +$18 of
justified PnL** — base went $0 -> ~$32 and xyz $108 -> $169 when the copy engine
restarted and opened positions.

Leading hypothesis: perp/dex `accountValue` is reported against the SAME unified
spot USDC balance we already count, so summing both double-counts collateral.
If true the tracker overstates equity whenever the engine holds perp positions,
and understated it before (the HIP-3 omission fixed earlier the same night).

Needed: determine authoritatively whether HL perp `accountValue` is additive to
spot USDC or a view on it, per-dex. Until then the tracker prints UNRECONCILED
and tells the operator to trust the flow figure.

---

## ANSWERED

- **Paired outcome quoting** — NO EDGE as built; one configuration UNPROVEN.
  YES and NO are **one book** (807/807 prints sum to exactly 1.000000), so
  "hedging" a one-sided fill is just flattening — **-18.3 bps/basket by
  construction**, -76 bps as realised. Eight peer wallets running it: **-5.31 bps
  on $420k / 17,057 fills**, 1/8 profitable. Fees are charged on EXIT not entry
  (buys 0.00 bps, n=21,515) — the -0.80% we paid was *drift*, not fees.
  Survivor, untested: 100% passive single-leg round-trip, never cross, never
  settle, +3.8 to +15.6 bps of face. Turnover unmeasured (n=2 fills).
  `research/paired-outcome-quoting-2026-09-21.md`, `MEASURED.md`.
- **In-play market making** — CLOSED. 22 price moves before any score change vs
  2 after; a field goal moved our feed and moved the book zero because it was
  already priced. We are a different speed class. `MEASURED.md`.
- **Deep symmetric bids (the "50c" idea)** — NO EDGE. 91–95% end one-sided,
  EV −0.87%/cycle over 70 markets. `MEASURED.md`.
- **Passive hedging** — WORSE than crossing. −0.93% vs −0.78%, n=2,307.
  `scripts/backtest_passive_hedge.py`, `MEASURED.md`.
