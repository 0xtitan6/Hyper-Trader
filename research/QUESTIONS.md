# Research queue

The `quant-researcher` cron reads this file each run and works the **topmost
unanswered** question. Edit this file to re-prioritise; do not edit the cron.

When a question is answered: move it to ANSWERED with the verdict and the file,
and append the finding to `MEASURED.md`.

---

## OPEN — work the top one

### 1. Is there ANY positive-EV configuration of paired outcome quoting?

This is the question the whole strategy rests on, and both obvious answers have
now failed.

Measured 2026-09-21:
- Quoting one tick BEHIND the touch: **zero fills in 5h** on books doing ~340
  trades/day. $384–$795 of queue ahead of us; flow could not reach us.
- Quoting AT the touch: fills arrive, but adverse. Two completed baskets cost
  1.01056 and 1.00212 — **above par**, so a locked loss regardless of outcome.
  A quoted +1.25% edge realised as **−0.80%**.
- Passive hedging instead of crossing: backtested at **−0.93% vs −0.78%**, i.e.
  worse. Waiting improved the eventual cross price only 29% of the time.

So: quote back and never trade; quote up and get picked off; hedge slow and it
gets worse. **Is there a middle, or is this structurally dead at our size?**

Things worth testing that we have NOT:
- Quote only ONE leg and accept directional exposure sized so the basket
  completes opportunistically rather than on a timer.
- Skew: quote the leg the flow is NOT hitting (we currently quote both equally).
- Size asymmetry vs the incumbent's fixed 1000-share, 1.15c policy.
- Time-of-day or time-to-event windows where fills are less adverse.
- Whether adverse selection is concentrated in a minority of surfaces we could
  simply exclude.

Answer with a number and a sample size. **"Structurally dead, here is the
evidence" is a perfectly good and valuable answer** — it redirects capital to
the crypto-barrier build instead of bleeding 0.8% a basket.

### 2. Do HIP-4 crypto barriers reprice slower than their underlying?

Eight `template:priceTouch` markets out-trade all 28 NFL markets combined
($888,708 vs $600,569 in 24h) and run 24/7 with the underlying fully observable
to us. Blocker is speed: they reprice on every BTC tick, our loop is 20 minutes.

Measure the lag the same way in-play NFL was measured (see `MEASURED.md`):
sample the barrier mid and the HL perp mark together, count which moves first
and by how long. If the barrier lags by seconds, quantify how fast a maker
would have to reprice to be safe. If it leads, it is closed — say so.

### 3. Does HIP-4 oil (`perp:xyz:CL`) lag the oil price?

Same experiment, different surface. Thin (25 trades/24h as of 09-21) — check
flow is real before building anything. Depth is not flow.

---

## ANSWERED

- **In-play market making** — CLOSED. 22 price moves before any score change vs
  2 after; a field goal moved our feed and moved the book zero because it was
  already priced. We are a different speed class. `MEASURED.md`.
- **Deep symmetric bids (the "50c" idea)** — NO EDGE. 91–95% end one-sided,
  EV −0.87%/cycle over 70 markets. `MEASURED.md`.
- **Passive hedging** — WORSE than crossing. −0.93% vs −0.78%, n=2,307.
  `scripts/backtest_passive_hedge.py`, `MEASURED.md`.
