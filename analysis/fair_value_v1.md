# Fair-value v1 — HL outcome barrier-touch model
_Generated: 2026-09-25T01:26:07.459178+00:00_
## Method
For each active `template:priceTouch` or `template:binaryPrice` outcome:
1. Parse (perp_underlying, target/threshold, expiry) from description.
2. Compute annualized realized vol from 1m candles (last 7d).
3. Get live spot from HL `allMids` (falls back to last candle close).
4. Under driftless GBM on log-price (r=0, mu=0):
   - `binaryPrice`: model_fv = P(S_T >= K) = N(d2),
     d2 = (log(S/K) - 0.5 sigma^2 T)/(sigma sqrt(T)).
   - `priceTouch`: reflection principle for driftless BM on log-price,
     model_fv = 2 N(-|log(B/S)| / (sigma sqrt(T))). Validated vs 40k-path MC.
5. Get HL mid+spread for the 'Yes' leg (side=0) — local snapshot if we log it, else one live l2Book fetch throttled 0.6s.
6. Divergence bps = (model_fv_yes - hl_mid) * 10000 (mid space is 0..1 prob).
   Tradeable = |div_bps| > 500 AND hl_spread_bps < 500.
## Sample
- outcomes in feed: **242**
- priceTouch + binaryPrice: **103**
- future (unexpired) at run time: **101**
- scored (candles + spot available): **59**
- with HL mid (local or live l2Book): **51**
- tradeable candidates (|div|>500bps AND spread<500bps): **0**

## Divergence distribution (|bps|)
- p5=40  p25=553  median=1294  p75=2228  p95=3811

## HL spread distribution (bps) — tradeability
- p5=707  p25=6256  median=19996  p75=19996  p95=19996
- no-book (spread > 5000bps, i.e. 0.01/0.99-style quoting): **39/59**

## Top 15 by |divergence| — where tradeable (|div|>500bps AND spread<500bps)
_No tradeable candidates in current window._

## Top 15 by |divergence| — all scored (context; wide-spread rows not tradeable now)
| outcome_id | template | underlying | level | expiry | T_hrs | sigma | spot | model_fv | hl_mid | div_bps | spread_bps |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 3988 | binaryPrice | HYPE | 82.4 | 2026-09-25T20:00 | 18.6 | 75.8% | 91.5935 | 0.999 | 0.500 | +4987 | 19996 |
| 4101 | binaryPrice | ZEC | 1323 | 2026-09-25T20:00 | 18.6 | 124.8% | 1543.85 | 0.996 | 0.500 | +4961 | 19996 |
| 4726 | binaryPrice | BTC | 88935 | 2026-09-28T20:00 | 90.6 | 41.3% | 84514.5 | 0.108 | 0.500 | -3916 | 19996 |
| 4104 | binaryPrice | ZEC | 1445 | 2026-09-25T20:00 | 18.6 | 124.8% | 1543.85 | 0.869 | 0.499 | +3705 | 19996 |
| 3991 | binaryPrice | HYPE | 88 | 2026-09-25T20:00 | 18.6 | 75.8% | 91.5935 | 0.871 | 0.501 | +3695 | 19701 |
| 5405 | binaryPrice | HYPE | 94.5 | 2026-09-25T13:35 | 12.1 | 75.8% | 91.5935 | 0.131 | 0.500 | -3689 | 19996 |
| 4729 | binaryPrice | HYPE | 98.6 | 2026-09-28T20:00 | 90.6 | 75.8% | 91.5935 | 0.160 | 0.500 | -3402 | 19996 |
| 4734 | binaryPrice | ZEC | 1353 | 2026-09-28T20:00 | 90.6 | 124.8% | 1543.85 | 0.836 | 0.500 | +3355 | 19996 |
| 5379 | binaryPrice | BTC | 88713 | 2026-10-02T08:00 | 174.6 | 41.3% | 84514.5 | 0.195 | 0.520 | -3252 | 18461 |
| 5169 | binaryPrice | HYPE | 98.6 | 2026-09-30T20:00 | 138.6 | 75.8% | 91.5935 | 0.206 | 0.500 | -2942 | 19996 |
| 5380 | binaryPrice | BTC | 88713 | 2026-10-05T08:00 | 246.6 | 41.3% | 84514.5 | 0.231 | 0.500 | -2687 | 19996 |
| 3994 | binaryPrice | HYPE | 93.6 | 2026-09-25T20:00 | 18.6 | 75.8% | 91.5935 | 0.262 | 0.500 | -2384 | 19996 |
| 4725 | binaryPrice | BTC | 86630 | 2026-09-28T20:00 | 90.6 | 41.3% | 84514.5 | 0.271 | 0.499 | -2278 | 19996 |
| 5176 | binaryPrice | ZEC | 1393 | 2026-09-30T20:00 | 138.6 | 124.8% | 1543.85 | 0.718 | 0.500 | +2178 | 19996 |
| 4727 | binaryPrice | HYPE | 87.4 | 2026-09-28T20:00 | 90.6 | 75.8% | 91.5935 | 0.716 | 0.500 | +2155 | 19996 |

## Vol per underlying (annualized, 7d 1m realized)
| underlying | sigma_ann | spot | notes |
|---|---|---|---|
| BTC | 41.29% | 84514.5 |  |
| HYPE | 75.79% | 91.5935 |  |
| NEAR |  | 4.57885 | no local candles |
| TAO | 148.62% | 297.81 |  |
| ZEC | 124.83% | 1543.85 |  |
| xyz:CL |  |  | no local candles |
| xyz:COIN |  |  | no local candles |
| xyz:CRCL |  |  | no local candles |
| xyz:GOLD |  |  | no local candles |
| xyz:INTC |  |  | no local candles |
| xyz:META |  |  | no local candles |
| xyz:MU |  |  | no local candles |
| xyz:OURA |  |  | no local candles |
| xyz:SILVER |  |  | no local candles |
| xyz:SKHY |  |  | no local candles |
| xyz:SNDK |  |  | no local candles |
| xyz:SP500 |  |  | no local candles |
| xyz:SPCX |  |  | no local candles |
| xyz:XYZ100 |  |  | no local candles |

### Vol sanity check
- BTC 7d ann vol = 41.3% (literature: 40-80% is normal regime)
- HYPE 7d ann vol = 75.8% (young perp, expect >BTC)

## Failure modes / unscored
- 42 outcomes unscored:
  - xyz:XYZ100: 9 outcomes (no local candles)
  - xyz:SP500: 9 outcomes (no local candles)
  - xyz:CL: 6 outcomes (no local candles)
  - xyz:SPCX: 4 outcomes (no local candles)
  - xyz:GOLD: 3 outcomes (no local candles)
  - xyz:MU: 2 outcomes (no local candles)
  - NEAR: 1 outcomes (no local candles)
  - xyz:META: 1 outcomes (no local candles)
  - xyz:INTC: 1 outcomes (no local candles)
  - xyz:CRCL: 1 outcomes (no local candles)
  - xyz:COIN: 1 outcomes (no local candles)
  - xyz:SKHY: 1 outcomes (no local candles)
  - xyz:SILVER: 1 outcomes (no local candles)
  - xyz:OURA: 1 outcomes (no local candles)
  - xyz:SNDK: 1 outcomes (no local candles)

No HIP-3 xyz:* underlyings have local candle files, so all xyz:CL / xyz:SP500 / xyz:XYZ100 / etc barrier outcomes are unscored in v1. To score them we would need to run `candle_backfill.py` against the correct HIP-3 dex — a separate ticket.

HL mid gap: our `book_logger` currently logs sports outcomes only (participant:* and NFL winners). For scored barrier coins we fetch l2Book live at 0.6s cadence. Empty books get `hl_mid=None`.

**Price-source basis**: description `priceDescription` shows the settlement source.
In this meta, sources include `HL perp mark` (~15 outcomes), `Pyth XYZ/USD` (~50), `1-minute candle` (~25). We use HL perp candles as the underlying for ALL of them; BTC/HYPE HL-vs-Pyth basis is typically <10bps intraday, but any thin oracle divergence would show up as spurious model edge. Before quoting, either (a) match candles to the cited source, or (b) restrict to `HL perp mark` outcomes.

## Verdict
**Ship v0 as a monitor, not yet as a quoter** — model produces prices for 59/101 unexpired barriers, median |div| vs HL mid = 1294bps. But **39/59 books are dead** (spread > 5000bps, i.e. 0.01/0.99-style placeholder quotes). Of the **3 tight-spread rows (<500bps)**, none diverge >500bps — so the model and the small population of real-quoter books agree.

Two paths from here:
- **Passive maker on the dead books**: place our own two-sided quotes at model_fv ±spread/2 to see who lifts. This IS the market-making thesis; the wide books ARE the opportunity. Requires the maker.py stack to know these coin names; verify.
- **Term-structure vol fix**: 7d realized may undershoot at 5-15d expiries where most barriers live. Cross-check with a short-window (24h) realized and see if the model_fv on the tight-spread rows moves.
