# HIP-3 cross-dex price dislocation — working notes
Agent slug: hip3-dislocation. Started 2026-09-19.
Hypothesis: same underlying quoted on 2+ HL perp dexes => persistent, tradeable basis.

## Step 0: enumerate dexes (`{"type":"perpDexs"}` then `{"type":"meta","dex":N}`)
Script: /tmp/enum_dex.py  (sleep 0.4s between calls; got 3x HTTP 429 on first perpDexs, retried OK)

11 venues (base + 10 HIP-3). Asset counts:
  (base) 234 | xyz 123 | para 35 | hyna 25 | mkts 24 | km 23 | cash 17 | flx 16 | vntl 15 | io 10 | abcd 1

Raw universes dumped to /tmp/dex_universes.json.

Immediate observations:
- `km` and `mkts` have IDENTICAL 23-asset universes (mkts has +1 BVIV). Same operator, two deployments.
- hyna is 25 crypto perps that are ALL duplicates of base-dex listings (BTC/ETH/SOL/XRP/DOGE/...).
  This is the cleanest possible two-venue test: same underlying, deep base leg.
- GOLD appears on xyz/flx/hyna/km/mkts/cash (6 venues). SILVER on 5. NVDA on 4-5. TSLA on 4.
- S&P proxy: xyz:SP500, flx:USA500, cash:USA500, abcd:USA500, km:US500, mkts:US500 (6 venues).

## Step 1: KILL SHOT #1 — most HIP-3 dexes are dead books
`{"type":"metaAndAssetCtxs","dex":N}` for all 11 venues (523 assets total). Script /tmp/ctx.py.

dex      assets        24h vlm $           OI $
(base)      234    9,106,273,753   12,605,892,847
xyz         123    2,035,189,756    3,738,348,920
io           10       24,798,335       56,613,076
mkts         24       11,687,263        7,512,518
para         35        5,743,257       16,294,228
flx          16                0                0
vntl         15                0                0
hyna         25                0                0
km           23                0                0
abcd          1                0                0
cash         17                0                0

=> flx / vntl / hyna / km / abcd / cash are ZERO-volume, ZERO-OI deployments.
Their allMids quotes are phantom. e.g. `cash:BTC = 70000.0` vs `flx:BTC = 91470.2`
vs real base BTC ~91.4k — a 23% "dislocation" that is just a stale/empty book.
ANY basis computed against these venues is untradeable by construction: nothing to trade against.

This also kills the headline hypothesis for the crypto duplicates: hyna is the only dex that
mirrors base-dex crypto (BTC/ETH/SOL/XRP/DOGE/ZEC/HYPE...) and hyna has $0 volume / $0 OI.
There is NO live venue duplicating a base-dex crypto perp.

Live venues: base, xyz, io, mkts, para. Overlaps therefore only exist xyz<->{mkts,para,io} and para<->io.
