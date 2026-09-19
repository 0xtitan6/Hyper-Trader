# New listing / first-days behaviour on Hyperliquid perps
Agent slug: new-listing. Date 2026-09-19. All data from https://api.hyperliquid.xyz/info (public, no auth).
Cost bar: 9bp taker round trip (0.045% x2). Maker rebate dependence is disallowed.

## Step 1 — enumerate coins and date each listing
`{"type":"meta"}` -> 234 coins in the base perp universe (incl. isDelisted ones).
For each coin: `{"type":"candleSnapshot","req":{"coin":C,"interval":"1d","startTime":1600000000000,"endTime":now}}`
The first returned candle dates the listing. Sanity checks:
 - BTC/ETH first candle = 2020-09-13 (2198 daily candles) -> HL BACKFILLS majors from pre-launch
   CEX data, so the first candle is NOT the listing for old majors. Irrelevant for the recent cohort.
 - HYPE first candle 2024-12-05 = real HYPE launch. JELLY 2025-01-30 with only 56 candles
   (delisted after the March-2025 squeeze) = correct. So first-candle dating is reliable for
   post-2024 listings, and delisted coins are still visible (no survivorship gap in the cohort).

### PROBLEM FOUND IMMEDIATELY: the requested 6-month window is underpowered by construction.
Coins first listed on/after 2026-03-19 (last 6 months): CHIP(2026-04-22), GRAM(2026-07-02),
CASHCAT(2026-07-11), PONS(2026-08-31), USELESS(2026-09-08) = **5 listings**.
HL's listing cadence collapsed in 2026 (2025 ran ~3-5 new perps/month; 2026 has run ~1/month).
n=5 is worthless. I widen the cohort to every listing since 2024-11-01 (70 coins) and report
sub-period breakdowns so the reader can see whether the effect is regime-specific.
