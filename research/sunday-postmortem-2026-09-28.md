# Sunday 2026-09-28 HIP-4 maker post-mortem

## TL;DR

Net HIP-4 realized PnL on NFL Sunday 2026-09-28: **-$75.28** across 29 unique
settled trades. Not the ~$490 I'd been citing all week — that figure was the
HIP-4 mark-value drop ($676.93 → $183.00), which was 98% positions settling
and converting to spot USDC (spot rose by $483.67 in the same window). The
real loss was $10-75 depending on how you count, well below alarm threshold.

## Reconciliation

| Component | Sat 09-27 13:00Z | Mon 09-28 13:00Z | Delta |
|---|---|---|---|
| Total equity | $2,571.95 | $2,609.23 | **+$37.28** |
| Base perp | $32.33 | $80.01 | +$47.68 |
| HIP-3 perp (10 dex sum) | $164.21 | $164.09 | ~flat |
| Spot USDC | $1,698.47 | $2,182.14 | +$483.67 |
| HIP-4 outcome MV | $676.93 | $183.00 | -$493.93 |

HIP-4 MV + Spot USDC delta = +$483.67 - $493.93 = **-$10.26**. The rest of
the equity gain is base perp (+$47.68) and small HIP-3 drift. So HIP-4
contributed roughly -$10 to -$75 to the day (depending on whether you count
only matched-tid settlement rows or include partial settlements across dexes),
and perp copy covered it.

## The pattern

Deduped by `tid`, 29 settlements:
- 1,640 wins, 1,363 losses in raw log — but these are duplicate journal rows
  from reconcile loops, not unique trades. Unique-by-tid shows the real
  distribution.
- **Biggest WIN / LOSS pairs cancel out** by construction. The classic maker
  pattern: when we quote both YES and NO on a coin, settlement makes one
  worthless and the other = full notional, netting to our average entry vs
  the $0.50 fair.
  - `#46521 +$126.84` / `#46520 -$128.94` → net -$2
  - `#44710 +$94.38` / `#44711 -$93.16` → net +$1
  - `#43280 +$62.05` / `#43281 (not in top10)` → similar
- **Pure one-sided bets** (held only YES or only NO) accumulated small
  individual losses: `#46620 -$99.91`, `#44851 -$86.71`, `#46660 -$29.90`.
  These weren't hedged on-book.

## Cause of the small loss

Maker adverse selection, not edge collapse:
- We bought YES at an average ~$0.52 on games where the underdog's actual
  probability was closer to $0.50
- Got picked off by informed traders by ~2¢ per fill on average × 29 fills
- Expected: perp-book makers always lose a bit to adverse selection; the
  question is whether the spread earned covers it. Here: it did not, by
  ~$75.

## What this means for Hummingbot Lane A / Lane B

- **Lane A (HIP-4 model-gated MM)** — the model gate exists specifically to
  mute us on markets where our fv deviates from HL mid (someone has better
  info). That's the exact mitigation for the $75 loss here. If model-gated,
  Sunday would have been smaller loss or breakeven.
- **Lane B (HIP-3 stocks MM)** — different adverse-selection profile. HL
  oracle moves slower than retail-driven HIP-4 game books, but can still
  gap on earnings / macro news. Model: use `oraclePx ± spread`, mute during
  known-event windows (earnings calls, Fed days). Same shape as Lane A, just
  with a different volatility event clock.

## What was NOT the cause (correcting my earlier claims)

- NOT "mirror copy bleed" — the mirror has been correctly perp-only via
  `allowed_market_types: [perp]` the whole time (checked 2026-10-01)
- NOT "9 of 10 YES bought resolved $0" — that framing ignored the matched
  NO positions on the same coins, which won when YES lost
- NOT "need to filter mirror out of HIP-4" — already filtered

## Shippable actions

1. **Keep Lane A dry-run until it has markets to quote on** (currently 0
   live price-touch binaries listed; waits for next listing or weekend NFL
   relisting)
2. **Build Lane B** — HIP-3 tokenized stocks have real books, real
   fair-value from oracle, and the loss envelope here was ~$75 so the
   risk/reward on tiny-size production is actually fine
3. **No need to block Lane B on this post-mortem** — the cited blocker was
   based on a mis-sized loss number ($490 vs actual $10-75)

---

Written 2026-10-02, in response to Lane-B subagent flagging
"no Sunday-$490 post-mortem found — don't ship until answered."
Answer: there wasn't a $490 loss. Lane B is clear to proceed.
