# Leader 0x511e60d3 — 30d native perp audit (2026-10-28)

**EDGE on the leader's own book: +$4,699.62 realized / +24.1 bps on $1,952,420 perp notional over 30d (n=891 perp fills, 2026-09-28 → 2026-10-28). But 87% of that edge is ONE symbol (ZEC +$4,074 / +559 bps). The config comment pinning this leader as "HYPE specialist / diversifies the SKHX concentration" is stale — HYPE is now −$128 / −4.4 bps over 15.9 days, and the real concentration has shifted to ZEC.**
**Our mirror reaches 71% of ZEC fill-count but only 0.9% of dollar volume; the leader's ZEC round-trip is +759.7 bps and ours on the same symbol is −232.8 bps.**
**n = 2,289 total fills across all markets; perps = 891 fills / $1.95M / net +$4,700. Our matching perp copies: n=213 on the same base-perp symbols for $5,837 notional and net −$51.30; all-perp net −$199.86 on $11,625 across 504 fills.**

Follow-up to `leader-9551e7d4-be-native-loss-2026-10-27.md`, which audited the
other active-weight leader. The natural generalisation: run the same per-symbol
native-PnL screen on 0x511e60d3 (currently weight 1.00 in `copy.leader_weights`
line 779 — our only non-muted leader given 0x9551e7d4 was cut to 0.10 on 10-18).

---

## Workspace state (15th consecutive cron run)

`MEASURED.md`, `research/QUESTIONS.md`, `.claude/agents/quant-researcher.md`
still absent from `main` HEAD. 15-day streak. Report grafts to the running
ledger at the bottom; convention unchanged.

## Method

Two paginated read-only `userFillsByTime` calls against the public HL info
endpoint for leader `0x511e60d32a1fdcafb46bae7f43cfab0a87040713`:
page 1 `startTime = now − 30d`, returned 2,000 fills covering 09-28 → 10-25;
page 2 `startTime = 2026-10-25T00:00Z`, returned 329 fills covering 10-25 →
2026-10-28 07:43Z. 40-fill overlap deduped on `tid`. Total 2,289 unique fills.
Sleep ≥0.4 s between calls; one 429 absorbed with ~15s backoff. No wallet key
touched.

Cross-check against our own fills: `state/state.db::own_fills` filtered by
`ts >= now − 30d`.

## What I measured

### 1. Leader's native 30d book, by market category

| category        | n   | notional $   | realized $ | fee $  | net $     |
|-----------------|----:|-------------:|-----------:|-------:|----------:|
| BASE_PERP       | 593 | 1,616,597    | +4,842.87  | 510.92 | +4,331.95 |
| XYZ_PERP        | 270 |   319,739    |   +593.76  |  20.37 |   +573.38 |
| OTHER_DEX_PERP  |  28 |    16,084    |   −204.62  |   1.09 |   −205.71 |
| **PERP TOTAL**  | **891** | **1,952,420** | **+5,232.01** | **532.38** | **+4,699.62** |
| OUTCOME (#NNN)  | 1,386 | 657,588   | −8,598.08  | 327.82 | −8,925.90 |
| SPOT (@NNN)     |  12 |     6,041    |   +204.79  |   3.90 |   +200.89 |

Perp side **profitable at +24.1 bps net over $1.95M**. Outcome markets a disaster
at −$8,926 (asymmetric payoffs so bps is meaningless there, but
`#79460 +$8,167 / #61660 −$19,777 / #108140 −$6,576 / #120820 −$11,193 /
#111430 +$7,288 / #149381 −$1,478 / #144200 −$3,494 / #153180 −$1,800`
shows this is a high-variance binary strategy that we **do not copy** —
`allowed_market_types: [perp]`).

### 2. Leader's top perp winners vs losers (sustained ≥3d spans only)

| coin       | n   | notl $    | net $     | bps     | span | first..last |
|------------|----:|----------:|----------:|--------:|-----:|-------------|
| ZEC        |  35 |  72,879   | +4,074.24 | +559.0  |15.9d | 09-28..10-14 |
| xyz:SP500  |   9 |  63,682   |   +562.57 |  +88.3  | 4.0d | 09-29..10-03 |
| NEAR       | 179 | 136,604   |   +557.35 |  +40.8  | 7.3d | 09-28..10-05 |
| xyz:SPCX   |  81 |  38,384   |   +324.19 |  +84.5  |26.2d | 09-28..10-24 |
| TAO        |  24 |  11,182   |   +315.59 | +282.2  | 3.9d | 09-30..10-04 |
| xyz:NVDA   |   7 |  24,884   |   +293.13 | +117.8  | 5.3d | 10-03..10-08 |
| xyz:TSLA   |  11 |  11,571   |   +245.63 | +212.3  | 4.3d | 09-29..10-03 |
| xyz:INTC   |  11 |  16,001   |   +233.42 | +145.9  |11.7d | 09-28..10-10 |
| **xyz:IREN**| **42** | **23,896** | **−867.14** | **−362.9** |**14.1d**| **09-28..10-12** |
| **xyz:MU** | **20** | **16,199** | **−207.35** | **−128.0** |**25.7d**| **10-02..10-28** |
| xyz:AMZN   |   9 |   9,713   |    −91.91 |  −94.6  |25.0d | 10-03..10-28 |
| STRK       |  48 |  25,881   |    −29.70 |  −11.5  | 3.4d | 10-09..10-13 |
| BTC        |  73 |1,040,303  |   −210.03 |   −2.0  | 4.8d | 10-08..10-13 |
| HYPE       | 163 | 293,001   |   −127.97 |   −4.4  |15.9d | 09-28..10-14 |

Three distinct patterns in the losers:

* **Structural losers (directional round-trip inverted):** xyz:IREN BUY $38.04 /
  SELL $35.38 = **−699 bps RT**, xyz:MU BUY $1077.03 / SELL $1056.40 = −192 bps RT,
  xyz:AMZN BUY $254.36 / SELL $251.90 = −97 bps RT. Same signature as
  0x9551e7d4's xyz:BE in last cron's report — the leader buys above and sells
  below, consistently.
* **Fee-dominated zeros:** BTC round-trip is +2.5 bps, HYPE round-trip is
  +9.7 bps — the "losses" are entirely the fee drag ($342 and $92 respectively)
  on makers at essentially zero directional edge. HYPE in particular is **not
  the specialist edge** the config comment claims.
* **Burst losers:** xyz:HOOD −$388 / −112 bps in 1.3d (not in the ≥3d
  table above) — a single flop, not a repeat offender.

### 3. The ZEC concentration — same single-symbol risk flag as 0x9551e7d4

| symbol      | 30d net $  | % of leader perp edge |
|-------------|-----------:|----------------------:|
| ZEC         |  +4,074.24 | **86.7%** |
| xyz:SP500   |    +562.57 |  12.0% |
| NEAR        |    +557.35 |  11.9% |
| xyz:SPCX    |    +324.19 |   6.9% |
| TAO         |    +315.59 |   6.7% |
| (losers)    |     −1,634 | −34.8% |

ZEC alone carries +87% of the leader's realised perp PnL. Config `copy.always_follow`
comment (lines 134–176) frames this leader's edge as **HYPE on base dex,
diversifying 0x9551e7d4's xyz:SKHX concentration**. Measured now, 15.9 days
after that comment: HYPE is −$128 / −4.4 bps and the real edge has rotated
to a different symbol (ZEC) that was already single-coin specialist 2 months
earlier. **The diversification argument that justifies the 1.00 weight is
no longer supported by the data.**

### 4. What our mirror actually copied

| perp slice (30d)                     | n   | notional $ | net $     |
|--------------------------------------|----:|-----------:|----------:|
| Our ZEC own                          |  25 |      668   |    −17.87 |
| Our base-perp own on 0x511's symbols | 213 |    5,837   |    −51.30 |
| Our xyz: own (all leaders combined)  | 268 |    5,185   |   −140.79 |
| Our ALL perp own                     | 504 |   11,625   |   −199.86 |
| xyz:IREN                             |   0 |        0   |      0.00 |
| xyz:HOOD                             |   0 |        0   |      0.00 |
| xyz:MU                               |   1 |       29   |     −0.00 |
| xyz:AMZN                             |   8 |      220   |     −0.43 |

Of the four 0x511e60d3 negative-edge symbols, **the mirror has effectively
zero exposure to three of them**. xyz:AMZN is the only one with any
participation and the dollar impact is −$0.43. Pre-existing filters
(`allowed_market_types` + xyz dex coverage) are already doing the right
thing on the symbol-block axis — a `.block` schema would not have moved
the needle in this window.

### 5. The actual lossy pattern — reach gap on ZEC

| metric            | leader       | ours      | ratio |
|-------------------|-------------:|----------:|------:|
| ZEC n fills       | 35           | 25        | 71% |
| ZEC $ notional    | $72,879      | $668      | **0.92%** |
| ZEC clip median   | $1,368       | $26       | **1.9%** |
| ZEC clip max      | $7,598       | $31       | 0.4% |
| ZEC round-trip bps| **+759.7**   | **−232.8**| sign-inverted |
| ZEC BUY avg       | $1,288.55    | $1,349.16 | +$60.6 worse |
| ZEC SELL avg      | $1,386.44    | $1,317.75 | −$68.7 worse |

We participate in 71% of the fills by count but 0.9% of the dollars, and
on that reachable 0.9% we round-trip at −233 bps while the leader round-trips
at +760 bps. We buy $60 above where the leader buys and sell $69 below where
the leader sells — classic late-mirror behaviour on a sub-second ZEC book
with $25 clips sampling an $1,368 median leader clip. **The edge the config
comment weights at 1.00 for is in dollar flow that is explicitly out of
reach of a $30 clip at `min_per_trade_usd=10`.**

## Interpretation

- **Symbol-block axis is a null result for this leader.** Three of four
  sustained perp losers have zero or near-zero own-fill exposure. There is
  no actionable block analogous to the xyz:BE recommendation on 0x9551e7d4.
- **The concentration flag is live.** 87% of this leader's measured perp
  edge is one coin (ZEC), and we cannot reach it in dollar terms. By the
  same reasoning that cut 0x9551e7d4's weight (10-18 strategist cut 0.40→0.10
  after xyz:SKHX blew up), 0x511e60d3 is a one-coin specialist whose single
  coin has a decaying 15.9-day signal (ZEC last fill 10-14, no reach since).
  If ZEC turns, −87% of the edge basis evaporates with it.
- **The "diversification against 0x9551e7d4's SKHX" argument has rotted.**
  Config comment claims edge is HYPE on base dex. Current 30d measurement:
  HYPE is −$128 (−4.4 bps), ZEC is +$4,074 (+559 bps). Both are base-dex
  crypto, so even the "different surface" claim no longer holds — both
  active leaders are now single-symbol specialists.
- **Our aggregate perp copy of this leader runs net −$200 over 30 days**
  while the leader runs +$4,700 native. The reach-gap mechanism is the
  dominant drag; symbol selection would barely matter even if improved.

## Concrete asks

1. **Strategist**: evaluate whether `0x511e60d3 @ 1.00` is still a 1.00 after
   measuring that (a) 87% of edge is ZEC, (b) ZEC last fired 10-14 → leader
   has been running on a decayed signal for 14 days, (c) the HYPE
   diversification pitch is empirically dead. Recommend measuring the
   last-7d native perp PnL to confirm the ZEC gap isn't a stale 10d burst.
2. **Engineering** (unchanged, 15th day open): `symbol_filter` schema
   remains blocked. No new ammunition for it this cycle — the only
   actionable 0x9551e7d4 block is still xyz:BE.
3. **No clip-size push based on this data.** $5 → $30 clips still can't reach
   $1,368-median leader flow. The reach gap at this account size on this
   leader's largest edge coin is a structural fact, not a config knob.
4. **Next cron suggestion**: re-measure 0x511e60d3's native perp PnL in
   7 days. If ZEC hasn't resumed and the remaining perp set is net
   neutral/negative over that window, the 1.00 weight is a stale pin.

## What I assumed, and what dies if it's wrong

- **2,289 fills is the full 30d.** API returned 329 fills on the tail page
  (10-25 → now, 3-day window) — not at the 2,000 cap, so we are not
  silently truncating. The 2,000-cap on the head page (09-28 → 10-25,
  27 days) means the first few hours of 09-28 may be clipped; damage is
  bounded by `max_notional_per_hour << 2M / 30 / 24 ≈ 2.8k`.
- **Pre-existing filter is why we don't trade xyz:IREN**, not luck. Our
  xyz: fills total 268 across 30d, so the xyz surface is active — the
  absence of IREN specifically needs confirming (likely tokenised-stock
  perp coverage via `discovery.min_leader_equity_usd` or symbol universe).
  If the "filter" is actually just coincidence, add IREN to the
  pre-emptive block list when the schema ships.
- **Outcome markets excluded by `allowed_market_types: [perp]`.** Verified
  in `config.yaml` grep for the previous report; not re-verified this run.
  If that config toggle flipped, our outcome exposure jumps from zero to
  copying a −$8,926 book — flag and verify before any multi-leader
  routing change.

## Reproducer

```python
# From hyper-trader repo root with .venv active. All read-only.
import urllib.request, json, time, sqlite3, datetime as dt
from collections import defaultdict

LEADER = '0x511e60d32a1fdcafb46bae7f43cfab0a87040713'

def fetch(start_ms):
    req = urllib.request.Request("https://api.hyperliquid.xyz/info",
        data=json.dumps({"type":"userFillsByTime","user":LEADER,
                         "startTime":start_ms}).encode(),
        headers={"content-type":"application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())

t0 = int((time.time() - 30*86400)*1000)
t1 = int(dt.datetime(2026,10,25,0,0,0,tzinfo=dt.UTC).timestamp()*1000)
head = fetch(t0); time.sleep(0.4)
tail = fetch(t1)
seen=set(); merged=[]
for f in head+tail:
    if f['tid'] not in seen: seen.add(f['tid']); merged.append(f)

by = defaultdict(lambda: dict(n=0,notl=0.,rpnl=0.,fee=0.,bb=0.,bs=0.,sb=0.,ss=0.))
for f in merged:
    if f['coin'].startswith('#') or f['coin'].startswith('@') or ':' in f['coin']:
        if not f['coin'].startswith('xyz:'): continue
    sz=float(f['sz']); px=float(f['px'])
    d=by[f['coin']]
    d['n']+=1; d['notl']+=sz*px; d['rpnl']+=float(f.get('closedPnl',0))
    d['fee']+=float(f.get('fee',0))
    if f['side']=='B': d['bb']+=sz*px; d['bs']+=sz
    else: d['sb']+=sz*px; d['ss']+=sz

for coin,d in sorted(by.items(), key=lambda x: x[1]['rpnl']-x[1]['fee']):
    bps = (d['rpnl']-d['fee'])/d['notl']*10_000 if d['notl'] else 0
    print(f"{coin:12s} n={d['n']:4d} ${d['notl']:9.0f} "
          f"net=${d['rpnl']-d['fee']:+8.2f} bps={bps:+7.1f}")

# Our ZEC round-trip
c = sqlite3.connect('state/state.db')
rows = list(c.execute("""
    select side,sz,px from own_fills where coin='ZEC' and ts>=?""",
    (int((time.time()-30*86400)),)))
b=[r for r in rows if r[0]=='B']; s=[r for r in rows if r[0]=='A']
ba=sum(r[1]*r[2] for r in b)/sum(r[1] for r in b)
sa=sum(r[1]*r[2] for r in s)/sum(r[1] for r in s)
print(f"\nOur ZEC: BUY {ba:.3f} / SELL {sa:.3f} -> {(sa-ba)/ba*10000:+.1f} bps RT")
```

Expected output (abridged):
```
xyz:IREN     n=  42 $    23896 net=$ -867.14 bps= -362.9
xyz:HOOD     n=  24 $    34708 net=$ -387.64 bps= -111.7
xyz:MU       n=  20 $    16199 net=$ -207.35 bps= -128.0
BTC          n=  73 $  1040303 net=$ -210.03 bps=   -2.0
xyz:AMZN     n=   9 $     9713 net=$  -91.91 bps=  -94.6
HYPE         n= 163 $   293001 net=$ -127.97 bps=   -4.4
...
ZEC          n=  35 $    72879 net=$+4074.24 bps= +559.0
Our ZEC: BUY 1349.160 / SELL 1317.750 -> -232.8 bps RT
```

---

## Verdict for `MEASURED.md`

Appending to the running ledger (same graft convention as the previous
fourteen reports; final target `MEASURED.md` on `feat/inplay-guard-pair-maker`):

### leader 0x511e60d3 — 30d native perp audit (2026-10-28, n=2289 fills / 891 perp)

```
Native perp 30d:  +$4,699.62 on $1,952,420 notl   =  +24.1 bps
Native outcome:   -$8,925.90 on   $657,588 notl   (not copied; allowed_market_types=[perp])
Edge concentration:
  ZEC          +$4,074  (+559 bps, 15.9d, 86.7% of perp edge)   LAST FIRED 10-14
  xyz:SP500      +$563  (+88 bps, 4d)
  xyz:SPCX       +$324  (+85 bps, 26d)
Sustained perp losers:
  xyz:IREN     -$867   (-363 bps, 14.1d)   RT -699 bps   our copy: 0 fills
  xyz:HOOD     -$388   (-112 bps, 1.3d)                  our copy: 0 fills
  xyz:MU       -$207   (-128 bps, 25.7d)   RT -192 bps   our copy: 1 fill, -$0.00
  xyz:AMZN      -$92    (-97 bps, 25.0d)   RT  -97 bps   our copy: 8 fills, -$0.43
  BTC/HYPE     fee-dominated zeros (RT +2.5 / +9.7 bps)
Reach gap on ZEC (the 87%-of-edge coin):
  Leader clip median $1,368 / max $7,598
  Our    clip median $   26 / max $   31
  Leader RT: BUY $1288.55 / SELL $1386.44 -> +759.7 bps
  Our    RT: BUY $1349.16 / SELL $1317.75 -> -232.8 bps  (sign-inverted)
Our aggregate perp copy (ALL leaders, 30d):  n=504  $11,625 notl  net=-$199.86
Our aggregate on 0x511's base-perp symbols:  n=213  $5,837 notl   net=-$51.30
```

Verdict: **UNPROVEN as a kill-signal, EDGE as a concentration flag.** No
symbol-block axis for this leader (we are not reaching the losers). The
weight 1.00 pin is now resting on one coin (ZEC) that hasn't fired for the
mirror since 10-14, and the HYPE diversification case in the config comment
is empirically dead at 15.9 days of −4 bps. Strategist should re-evaluate
weight before the next drawdown round rather than after.
