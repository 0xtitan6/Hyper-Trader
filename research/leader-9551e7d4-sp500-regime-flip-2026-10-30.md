# Leader 0x9551e7d4 — xyz:SP500 is replaying xyz:BE (2026-10-30)

**EDGE (as a warning): the leader's native xyz:SP500 book has flipped from +10.5 bps / +$2,147 (10-18 → 10-24, n=115, $2.04M notl) to −31.7 bps / −$2,722 (10-24 → 10-30, n=40, $860k notl). Same sign-flip signature as xyz:BE one regime earlier.**
**UNPROVEN as a kill-signal: 6 days post-BE-silence is thinner than the 10-day sustained bar xyz:BE met before the 10-25 adverse-selection flag; xyz:SP500 round-trip BUY $7,698 / SELL $7,655 looks structural but needs ≥10d of persistence.**
**n = 781 leader fills over 14d (10-18 → 10-30 07:43Z), split 467 pre / 314 post. Our mirror on the same window: n=265 own_fills across 11 perps, net ≈ −$57 (all of it xyz:BE pre-silence; post-silence is −$1.6 fee-neutral noise across the remaining 10 symbols).**

Follow-up to:
- `xyz-sp500-copy-shadow-2026-10-26.md` (SP500 copy UNPROVEN at +$0.59/7d)
- `leader-9551e7d4-be-native-loss-2026-10-27.md` (BE −241 bps on leader side)
- `copy-roster-week-net-2026-10-29.md` (post-BE 5d quiet, +15 bps non-BE null bet)

The 10-26 report's unanswered question — *is xyz:SP500 the next xyz:BE?* — is the one this measurement attacks.

---

## Workspace state (17th consecutive cron run)

`MEASURED.md`, `research/QUESTIONS.md`, `.claude/agents/quant-researcher.md`
still absent from `main` HEAD. 17-day streak. Report grafts to the running
ledger at the bottom; convention unchanged.

## Method

Single read-only `userFillsByTime` on leader
`0x9551e7d4cd963558bb9882aecc74f549262e217f`, `startTime = now − 14d`.
781 fills returned, no pagination needed (< 2,000 cap). 0.5s sleep.
Two follow-up `clearinghouseState` reads (`dex=None`, `dex=xyz`) for current
open positions. No wallet material touched.

Regime cutoff: **2026-10-24 07:39 UTC** = last xyz:BE leader_fill observed
by `state/journal.jsonl` (per 10-29 report).

Cross-check against our fills: `state/state.db::own_fills` filtered by
`ts >= now − 14d`, split on the same cutoff.

## What I measured

### 1. Leader's native perp book, split by regime

| coin        | pre_n | pre_notl $ | pre_net $ | pre bps | post_n | post_notl $ | post_net $ | post bps |
|-------------|------:|-----------:|----------:|--------:|-------:|------------:|-----------:|---------:|
| BTC         |     0 |          0 |     0.00  |    —    |      4 |      27,409 |    −10.66  |   −3.9   |
| ZEC         |     0 |          0 |     0.00  |    —    |     20 |      42,716 |   +171.41  |  +40.1   |
| xyz:BE      |   343 |    262,951 | −6,798.46 | −258.5  |      0 |           0 |      0.00  |    —     |
| xyz:GOOGL   |     0 |          0 |     0.00  |    —    |     13 |      35,257 |     −2.41  |   −0.7   |
| **xyz:SP500** | **115** | **2,038,526** | **+2,147.20** | **+10.5** | **40** | **859,580** | **−2,722.25** | **−31.7** |
| **PRE perp total**  | 458 | 2,301,477 | −4,651.26 | −20.2 | | | | |
| **POST perp total** | | | | | 77 | 964,962 | −2,563.91 | −26.6 |
| ex xyz:BE (pre)     | 115 | 2,038,526 | +2,147.20 | +10.5 | | | | |
| ex xyz:SP500 (post) | | | | | 37 | 105,382 | +158.34 | +15.0 |

Reading across the top block: the leader rotated from "trading one big losing
book + nothing else" (xyz:BE pre-silence) to "trading a new big losing book +
small positive scraps on four symbols" (xyz:SP500 post-silence). The signature
on xyz:SP500 is the **same shape** as xyz:BE one week earlier:

| symbol    | window      | n   | notl $    | net $    | RT bps | buy avg → sell avg |
|-----------|-------------|----:|----------:|---------:|-------:|-------------------|
| xyz:BE    | 10-15..10-24 (10d) | 351 |  281,700 | −6,783.46 | −241  | $209.05 → $200.24 |
| xyz:SP500 | 10-19..10-24 (6d)  | 115 | 2,038,526 |  +2,147  |  +11  | $7,728 → $7,699   |
| xyz:SP500 | 10-24..10-30 (6d)  |  40 |   859,580 | −2,722   |  −32  | $7,698 → $7,655   |

### 2. xyz:SP500 — daily tape

Pre-silence (10-19 → 10-23, 5d):
```
10-19  n=23  $389k  +$622.34  (+16.0 bps)
10-20  n=25  $419k   −$5.01   ( −0.1 bps)
10-21  n=32  $650k  +$1110.59 (+17.1 bps)
10-22  n=13  $210k   −$14.51  ( −0.7 bps)
10-23  n=22  $370k   +$433.79 (+11.7 bps)
```

Post-silence (10-25 → 10-30, 6d):
```
10-25  n=4   $160k  −$358.10  (−22.3 bps)
10-26  n=16  $301k  −$936.63  (−31.1 bps)
10-29  n=11  $200k   −$15.54  ( −0.8 bps)
10-30  n=9   $198k  −$1,411.98 (−71.1 bps) ← today, SELL-only, closing a long
```

The pre window has 4 positive days / 1 flat. The post window has 0 positive
days / 1 flat. The 10-30 session alone (−71 bps in 9 fills) is the largest
single-day loss in the sample and is still open as of 07:43Z — the leader is
closing out a long into weakness.

### 3. Open-position overhang (clearinghouseState snapshot now)

| dex  | accountValue $ | open position              | unreal $ |
|------|---------------:|----------------------------|---------:|
| base |         9,577  | BTC +0.35 @ 78,311         |   −30.75 |
| base |              — | ZEC +10.00 @ 1,257         |   −48.33 |
| xyz  |        10,236  | xyz:GOOGL +120.0 @ 293.81  | −1,478.38 |

The xyz:GOOGL carry is the hidden tail of the post-BE 13 GOOGL fills. In the
realized table above GOOGL reads −$2 (fees). The real post-BE drawdown
including the GOOGL unrealized is −$2,564 − $1,478 = **−$4,042 over 6d** —
larger than xyz:BE's realized loss rate.

### 4. Our mirror, same 14d, same split

| coin        | pre_n | pre_notl $ | pre_net $ | post_n | post_notl $ | post_net $ |
|-------------|------:|-----------:|----------:|-------:|------------:|-----------:|
| BTC         |     0 |      0.0   |     0.00  |     13 |     365.9   |     +5.02  |
| HYPE        |     0 |      0.0   |     0.00  |      6 |     175.8   |     −1.41  |
| ZEC         |     0 |      0.0   |     0.00  |     17 |     212.1   |     −0.09  |
| xyz:AMZN    |     0 |      0.0   |     0.00  |      6 |     175.1   |     −3.45  |
| xyz:BE      |   177 |   2,871.2  |    −58.03 |      0 |       0.0   |      0.00  |
| xyz:COIN    |     0 |      0.0   |     0.00  |      7 |     209.5   |     +2.53  |
| xyz:GOOGL   |     0 |      0.0   |     0.00  |     21 |     391.5   |     −1.12  |
| xyz:MU      |     0 |      0.0   |     0.00  |      7 |     206.2   |     −2.98  |
| xyz:SKHY    |     0 |      0.0   |     0.00  |      4 |     118.2   |     +1.78  |
| xyz:SP500   |    20 |    292.0   |     +0.62 |     15 |     230.9   |     −0.94  |
| xyz:SPCX    |     9 |    260.9   |     +1.81 |      3 |      86.1   |     −0.89  |

Our post-BE 6d net across the 10 non-BE symbols the leader fired is
**≈ −$1.55 on ~$2.17k notional (−7.1 bps)** — fee-neutral noise. Our
largest named loser is xyz:AMZN at −$3.45 on $175, not SP500.

### 5. The structural pattern — leader's one-coin-at-a-time losses

| regime   | "big book" (>$100k leader notl) | pre edge | post edge | reach-adj our net |
|----------|---------------------------------|---------:|----------:|------------------:|
| 10-15..10-24 | xyz:BE                       |      —   |  −242 bps |            −$58   |
| 10-24..10-30 | xyz:SP500                    |  +11 bps |   −32 bps |            −$0.94 |

Two consecutive 6-day windows, each with one big losing book, each a
sign-flipped version of the previous week. The small-notional symbols
(ZEC, SKHY, COIN) net slightly positive in the second window but the dollar
scale is 20x below the big book — they can't offset the SP500 bleed on the
leader's side.

## Interpretation

1. **xyz:SP500 is UNPROVEN as a kill-signal but EDGE as a monitoring one.**
   The 6-day post-BE native loss (−32 bps on $860k) is the single clearest
   mirror of the xyz:BE collapse pattern we've measured. If it holds another
   4 days at this rate, we meet the sustained-span bar BE met before the 10-25
   adverse-selection flag.
2. **Our dollar exposure is not the issue THIS week.** 15 own_fills on $231
   notional / −$0.94 net is the same fee-neutral pattern post-BE's 5-day
   non-BE flow showed in the 10-29 report. The structural reach-gap continues
   to protect us: $30 clips can't absorb $1,368-median leader clips.
3. **The "diversification" story keeps dying.** The 10-28 report showed
   0x511e60d3's HYPE-specialist pitch is 2 months stale; this report shows
   0x9551e7d4's apparent SP500 edge was 5 trading days of positive variance,
   now reversed. Both pins in `always_follow` are empirically riding
   one-coin pulses, not a durable edge.
4. **The hidden +$1,478 xyz:GOOGL carry on the leader side matters.** If
   GOOGL rolls over the way SP500 did, the leader's unrealized becomes
   realized and amplifies the post-BE drawdown. We have 21 GOOGL own_fills
   / $392 notl / −$1.12 net already; a GOOGL round-trip inversion would hit
   us too, though at $0.1-order dollar scale.
5. **Mission read: unchanged.** Copy strategy at current clip + current
   roster is net-negative on 14d (−$57 all-in from this leader, 99% xyz:BE),
   and the "non-BE" fallback is a null bet. The leader's rotation into
   SP500-as-the-new-loser does not change our bottom line this week because
   we can't dollar-reach the loss, but it falsifies the thesis that
   removing BE leaves a positive-edge book behind.

## Concrete asks

1. **Engineering (unchanged, 17th day open):** ship
   `always_follow[0x9551e7d4].block: [xyz:BE]`. New evidence this cycle
   does not add xyz:SP500 to the block — 6 days is too thin and the dollar
   exposure is < $1/day — but **the schema should be scoped so adding
   SP500 is a one-line config change** once the sample reaches 10+ days
   of sustained negative. Design, don't ship, with SP500 in mind.
2. **Strategist:** the SP500 regime flip + 10-30's biggest-single-day
   loss materially weakens the "wait for leader to exit organically"
   position. The leader did drop BE on their own, then rotated into
   another big-notional loser. If the next retest (recommended 2026-11-05)
   confirms SP500 at −30 bps across 10 days, cut 0x9551e7d4 weight
   from 0.10 to 0.05 and start sourcing a replacement leader.
3. **Observability:** on top of the 10-29 `strategy_tag` ask, add a
   daily rollup of "leader native per-symbol realized + unrealized"
   so GOOGL-shape carries don't hide in the realized table. Scope:
   one new nightly job + sqlite table; no live code touched.
4. **Mission (prime directive):** no action lever moves us toward $10k
   from this measurement. Both active leaders are documented as one-coin
   specialists trading losing books at our dollar scale. The highest-leverage
   question remains "do we need a new leader source" — not "do we need
   another block/filter". Flag the strategist re-evaluation accordingly.

## What falsifies this report

- **The 6-day sample on post-BE SP500 is thin.** A single big
  positive-direction session (e.g. SP500 futures rallying 2% intraday with
  the leader long) could reverse the sign. Historical reference: pre-BE
  10-19 showed +$622 on $389k alone, which is a 2% equity-type move. The
  "post-BE −32 bps" number is one such session away from flipping.
- **The 14d window may clip SP500 fills from the week of 10-15..10-18.**
  The Oct 27 report cites SP500 "10-16 → 10-26, 144 fills, +$1,021 / +3 bps".
  My pre-BE slice starts at 10-18 and has 115 fills; the missing 29 fills from
  10-16..10-17 are the small-notl early-position-build. If those are big
  positives, the "pre vs post" sign-flip is sharper than stated here.
  Does not change the post-BE verdict.
- **xyz:GOOGL open −$1,478 could evaporate upward.** If GOOGL rallies and the
  leader closes the long flat, the unrealized reverses. The 13 GOOGL fills in
  realized are already slightly negative, but 120-unit size + $294 entry
  gives ~$7-$9/share leverage either way.
- **Classification: BTC above was counted as BASE (correct), ZEC same**.
  If I miscounted BE as not-perp or SP500 as something else, totals shift.
  Verified: `grep -nE '^(xyz:BE|xyz:SP500|BTC|ZEC|xyz:GOOGL)$' output above` =
  classes `XYZ`/`BASE`, both perp.
- **Open positions snapshot is now (07:43Z 10-30).** If the leader closes
  GOOGL in the next hour, the −$1,478 unrealized becomes realized and shows
  in the next report. Does not change this report's number.

## Reproducer

```python
# From hyper-trader repo root with .venv active. Read-only.
import urllib.request, json, time, datetime as dt, sqlite3
from collections import defaultdict

LEADER = '0x9551e7d4cd963558bb9882aecc74f549262e217f'
BE_SILENT_MS = int(dt.datetime(2026,10,24,7,39,0,tzinfo=dt.UTC).timestamp()*1000)

def fetch(start_ms):
    req = urllib.request.Request("https://api.hyperliquid.xyz/info",
        data=json.dumps({"type":"userFillsByTime","user":LEADER,
                         "startTime":start_ms}).encode(),
        headers={"content-type":"application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())

t0 = int((time.time() - 14*86400)*1000)
fills = fetch(t0); time.sleep(0.5)

pre  = [f for f in fills if f['time'] <  BE_SILENT_MS]
post = [f for f in fills if f['time'] >= BE_SILENT_MS]

def by(fx):
    r = defaultdict(lambda: dict(n=0, notl=0., rp=0., fee=0.))
    for f in fx:
        c = f['coin']
        if ':' in c and not c.startswith('xyz:'): continue
        if c.startswith('#') or c.startswith('@'): continue
        sz=float(f['sz']); px=float(f['px'])
        r[c]['n']+=1; r[c]['notl']+=sz*px
        r[c]['rp']+=float(f.get('closedPnl',0)); r[c]['fee']+=float(f.get('fee',0))
    return r

for lbl, bk in [("PRE",  by(pre)), ("POST", by(post))]:
    tot = sum(d['rp']-d['fee'] for d in bk.values())
    tot_notl = sum(d['notl'] for d in bk.values())
    print(f"\n{lbl} total: ${tot:+.2f} on ${tot_notl:,.0f} "
          f"({tot/tot_notl*1e4 if tot_notl else 0:+.1f} bps)")
    for c,d in sorted(bk.items(), key=lambda x: x[1]['rp']-x[1]['fee']):
        net = d['rp'] - d['fee']
        bps = net/d['notl']*1e4 if d['notl'] else 0
        print(f"  {c:12s} n={d['n']:4d} notl=${d['notl']:,.0f} net=${net:+.2f} ({bps:+.1f} bps)")

# Open positions
for dex in [None, "xyz"]:
    p = {"type":"clearinghouseState","user":LEADER}
    if dex: p["dex"]=dex
    req = urllib.request.Request("https://api.hyperliquid.xyz/info",
        data=json.dumps(p).encode(), headers={"content-type":"application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=20).read()); time.sleep(0.5)
    print(f"\ndex={dex or 'base'}  accountValue=${r['marginSummary']['accountValue']}")
    for ap in r.get('assetPositions', []):
        pos = ap['position']
        if abs(float(pos.get('szi',0))) > 0.001:
            print(f"  {pos['coin']:10s} szi={pos['szi']} unreal=${pos.get('unrealizedPnl','?')}")
```

Expected (abridged):
```
PRE total:  $-4651.26 on $2,301,477 (-20.2 bps)
  xyz:BE       n= 343 notl=$262,951 net=$-6798.46 (-258.5 bps)
  xyz:SP500    n= 115 notl=$2,038,526 net=$+2147.20 (+10.5 bps)
POST total: $-2563.91 on $964,962 (-26.6 bps)
  xyz:SP500    n=  40 notl=$859,580 net=$-2722.25 (-31.7 bps)
  ZEC          n=  20 notl=$42,716  net=$+171.41  (+40.1 bps)
dex=xyz  accountValue=$10236.56
  xyz:GOOGL  szi=120.0 unreal=$-1478.38
```

---

## Verdict for `MEASURED.md`

Appending to the running ledger (same graft convention as the previous 16
reports; final target `MEASURED.md` on `feat/inplay-guard-pair-maker`):

### leader 0x9551e7d4 — SP500 regime flip, 14d native (2026-10-30, n=781 fills)

```
PRE-BE  (10-18..10-24, 6d):    n=458  notl=$2,301,477  net=$-4,651.26  -20.2 bps
  xyz:BE                       n=343  notl=$  262,951  net=$-6,798.46 -258.5 bps  (last fire 10-24 07:39Z)
  xyz:SP500                    n=115  notl=$2,038,526  net=$+2,147.20  +10.5 bps  (ex-BE edge)

POST-BE (10-24..10-30, 6d):    n= 77  notl=$  964,962  net=$-2,563.91  -26.6 bps
  xyz:SP500                    n= 40  notl=$  859,580  net=$-2,722.25  -31.7 bps  <-- new big loss book
  ZEC                          n= 20  notl=$   42,716  net=$+171.41    +40.1 bps
  xyz:GOOGL                    n= 13  notl=$   35,257  net=$   -2.41    -0.7 bps
  BTC                          n=  4  notl=$   27,409  net=$  -10.66    -3.9 bps
  ex-SP500 remainder           n= 37  notl=$  105,382  net=$+158.34    +15.0 bps

Open-position overhang NOW:
  base: BTC +0.35 @ 78,311   unreal -$31
  base: ZEC +10   @ 1,257    unreal -$48
  xyz:  GOOGL +120 @ 293.81  unreal -$1,478   <-- hidden post-BE drawdown

Pattern:  xyz:BE  10-15..10-24: 10d, -258 bps, -$6,783  (closed loss)
          xyz:SP500 10-24..10-30: 6d,  -32 bps, -$2,722  (realized; +$1,478 unreal via GOOGL)

Our mirror same 14d:
  PRE  (pre-BE-silence):  xyz:BE -$58.03 / $2,871 notl   (99% of our 14d loss)
  POST (post-BE-silence): 10 non-BE perps net -$1.55 / $2,171 notl  = fee-neutral
  Our SP500 same 6d post: n=15 / $231 notl / -$0.94 (-41 bps)       = same sign, fee scale
```

Verdict: **EDGE as monitoring signal** on xyz:SP500 (same shape as xyz:BE
one week earlier). **UNPROVEN as a kill-signal** at 6d sample. Our dollar
exposure to the SP500 bleed is < $1/day; no change to the pending xyz:BE
block ask, but the symbol-filter schema should be designed with SP500
addable in one line. Both active leaders in `always_follow` are now
documented one-coin specialists on currently-losing books; the next
tactical lever is sourcing a new leader, not another filter.
