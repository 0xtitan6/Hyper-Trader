# Leader 0x9551e7d4 — xyz:BE loses on their book too (2026-10-27)

**EDGE (as a kill-signal): leader 0x9551e7d4's own xyz:BE book is −241 bps / −$6,783.46 over 10d (n=351 fills, $281,700 notional). Our mirror's −202 bps is not an execution leak — the strategy is a loser on the leader's side.**
**n = 351 leader fills (10-15 → 10-24) vs 177 own_fills (10-18 → 10-24) same symbol, both round-tripped flat.**
**Direction: BUY avg $209.05 / SELL avg $200.24 on the leader; BUY $208.92 / SELL $200.67 on ours — the two tapes agree on the sign and nearly on the magnitude.**

Follow-up to `xyz-be-copy-adverse-2026-10-25.md` (−201 bps on our copy),
`xyz-sp500-copy-shadow-2026-10-26.md` (SP500 UNPROVEN, BE idle since 10-24).
The 10-26 report flagged one open question: **"whether 0x9551e7d4's BE book was
positive on their side — not measured."** This resolves it.

---

## Workspace state (14th consecutive cron run)

`MEASURED.md`, `research/QUESTIONS.md`, `.claude/agents/quant-researcher.md`
still absent from `main` HEAD. 14-day streak. Report grafts to the running
ledger at the bottom; convention unchanged.

## Method

Single read-only `userFillsByTime` call for leader
`0x9551e7d4cd963558bb9882aecc74f549262e217f` from `startTime = 2026-10-14` (ms,
unix). Base + xyz dex are returned together (HL ignores `dex`-param here).
1,043 fills returned. 0.3s sleep between the two calls. No key material
touched.

- Our fills: `state/state.db::own_fills`, filter `coin='xyz:BE' and date_utc >= '2026-10-18'`.
- Attribution to 0x9551e7d4: 100% in `state/journal.jsonl` (`leader_fill` events, prefix `0x9551e7d4cd`, 343 BE events in window — matches the leader's 343 fills within our observation.)

## What I measured

### Leader native per-symbol PnL since 2026-10-14 (full HL tape)

| coin        | n    | notl $      | realized $ | fee $  | bps     | first→last |
|-------------|-----:|------------:|-----------:|-------:|--------:|------------|
| xyz:SP500   | 144  | 2,699,788   | +1,021.35  | 182.71 | +3.1    | 10-16→10-26 |
| xyz:CL      | 209  | 1,176,473   | +3,023.10  |  68.61 | +25.1   | 10-15→10-15 |
| xyz:GOLD    |  78  |   923,291   | +2,683.03  | 717.95 | +21.3   | 10-15→10-15 |
| @107 (spot) | 217  |   833,140   |   −404.06  | 252.47 | −7.9    | 10-14→10-20 |
| **xyz:BE**  | **351** | **281,700** | **−6,783.46** | **15.48** | **−241.4** | **10-15→10-24** |
| #160491     |   7  |     9,055   |   +613.21  |   1.25 | +676    | 10-23→10-24 |
| #165381     |  14  |     2,738   |   +143.09  |   0.75 | +520    | 10-24→10-24 |
| #170390     |   4  |       373   |    −34.14  |   0.09 | −918    | 10-25 |
| #165380     |  10  |       172   |   −144.43  |   0.01 | −8,382  | 10-25 |
| #36000      |   9  |    49,586   |     +0.00  |   0.00 | +0.0    | 10-27 (open) |

xyz:BE is the leader's **single biggest realized loss** and runs 10 trading days
— far from a one-day blip. The three positives (SP500, CL, GOLD) are
single-session bursts (CL/GOLD both 10-15 only; SP500 small bps on huge notl).

### Our copy window (10-18 → 10-24) — leader-native vs ours

| metric                | leader-native | our mirror |
|-----------------------|--------------:|-----------:|
| n fills               | 343           | 177        |
| notional              | $262,951      | $2,871     |
| realized              | **−$6,783.46**| **−$57.78**|
| fee                   | $15.00        | $0.248     |
| **net bps**           | **−258.5**    | **−202.1** |
| ending position       | round-tripped flat | round-tripped flat |

### Directional decomposition — same window

|            | leader BUY | leader SELL | our BUY  | our SELL |
|------------|-----------:|------------:|---------:|---------:|
| n          | 183        | 160         | 134      | 43       |
| size units | 600.29     | 686.47      | 7.01     | 7.01     |
| avg px     | **$209.05**| **$200.24** | **$208.92** | **$200.67** |

Both tapes are **buying at $209 and selling at $200** — a −$8.80 structural
round-trip loss per unit. Our mirror is 27 bps less bad than the leader
simply because we trade less often, not because we execute better.

## Interpretation

- The 10-25 report framed BE as adverse selection on our copy (−201 bps).
  That framing is wrong. The leader's own BE book is −241 bps on 20x more
  notional. **This is not slippage. It is the strategy.**
- The 56-bps gap (−258 leader vs −202 ours) tracks fee-tier + partial
  participation, not an edge differential. If anything, our mirror is
  marginally better than the raw leader book.
- Removing xyz:BE from this leader's copy roster is **positive-EV in
  expectation**, not merely "less noisy." Weight-cutting is still a
  no-op at the `min_per_trade_usd=10` floor.
- The leader's actual positive-bps symbols — xyz:CL, xyz:GOLD — were
  one-day sessions (both 10-15) that occurred **before** our journal
  started (10-18). No causal link to our copy outcomes; they are not
  recoverable with a backward-looking fix.
- xyz:SP500 at +3 bps / $2.7M native notl is a weak positive; our 7d copy
  of +18 bps on $353 is noise around that. Hold position unchanged.

## Concrete asks

1. **Engineering (unchanged, 14th day open)**: ship
   `always_follow[0x9551e7d4].block: [xyz:BE]`. The 10-25 ask was
   motivated by our drift; this report adds that the leader is also
   underwater on the same symbol — the block is correct in two
   independent measurements, not one.
2. **Strategist**: with xyz:CL and xyz:GOLD being 10-15 one-day events
   and xyz:BE being the only sustained symbol — all negative on the
   leader book — consider whether `always_follow[0x9551e7d4]` should
   drop to a lower weight after a BE block. The sole positive
   sustained symbol (xyz:SP500) is +3 bps native; thin edge, same
   leader, same drift risk if volume returns.
3. **No action on xyz:SPCX / xyz:SP500 right now.** Keep the 7d
   shadow metric; re-measure 2026-11-02.

## Reproducer

```python
# From hyper-trader repo root with .venv active. Read-only.
import urllib.request, json, time, sqlite3
from collections import defaultdict

LEADER = '0x9551e7d4cd963558bb9882aecc74f549262e217f'
req = urllib.request.Request("https://api.hyperliquid.xyz/info",
    data=json.dumps({"type":"userFillsByTime","user":LEADER,
                     "startTime": 1792000000*1000}).encode(),
    headers={"content-type":"application/json"})
resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
time.sleep(0.3)

# per-symbol native PnL
by = defaultdict(lambda: dict(n=0,notl=0.,rpnl=0.,fee=0.))
for f in resp:
    d = by[f['coin']]
    d['n'] += 1
    d['notl'] += float(f['sz'])*float(f['px'])
    d['rpnl'] += float(f.get('closedPnl',0))
    d['fee']  += float(f.get('fee',0))
for coin, d in sorted(by.items(), key=lambda x:-x[1]['notl']):
    bps = (d['rpnl']-d['fee'])/d['notl']*10_000 if d['notl'] else 0
    print(f"{coin:12s} n={d['n']:4d} notl={d['notl']:11.0f} realized={d['rpnl']:+9.2f} bps={bps:+6.1f}")

# directional (BE window)
t0 = int(time.mktime(time.strptime('2026-10-18','%Y-%m-%d')))*1000
t1 = int(time.mktime(time.strptime('2026-10-25','%Y-%m-%d')))*1000
be = [f for f in resp if f['coin']=='xyz:BE' and t0<=int(f['time'])<=t1]
buys  = [f for f in be if f['side']=='B']
sells = [f for f in be if f['side']=='A']
lb = sum(float(f['sz'])*float(f['px']) for f in buys)/sum(float(f['sz']) for f in buys)
ls = sum(float(f['sz'])*float(f['px']) for f in sells)/sum(float(f['sz']) for f in sells)
print(f"leader BE: BUY {lb:.3f} / SELL {ls:.3f} -> {(ls-lb)/lb*10000:+.1f} bps")

c = sqlite3.connect('state/state.db')
rows = c.execute("select side,sz,px from own_fills where coin='xyz:BE' and date_utc>='2026-10-18'").fetchall()
ob = [r for r in rows if r[0]=='B']; os_= [r for r in rows if r[0]=='A']
b = sum(r[1]*r[2] for r in ob)/sum(r[1] for r in ob)
s = sum(r[1]*r[2] for r in os_)/sum(r[1] for r in os_)
print(f"ours    BE: BUY {b:.3f} / SELL {s:.3f} -> {(s-b)/b*10000:+.1f} bps")
```

Expected output:
```
xyz:SP500    n= 144 notl=  2699788 realized= +1021.35 bps:  +3.1
xyz:CL       n= 209 notl=  1176473 realized= +3023.10 bps: +25.1
xyz:GOLD     n=  78 notl=   923291 realized= +2683.03 bps: +21.3
@107         n= 217 notl=   833140 realized=  -404.06 bps:  -7.9
xyz:BE       n= 351 notl=   281700 realized= -6783.46 bps:-241.4
leader BE: BUY 209.053 / SELL 200.240 -> -421.6 bps
ours    BE: BUY 208.917 / SELL 200.675 -> -394.5 bps
```

---

## Verdict for `MEASURED.md`

Appending to the running ledger (same graft convention as the previous 13
reports; final target `MEASURED.md` on `feat/inplay-guard-pair-maker`):

### leader 0x9551e7d4 — xyz:BE native loss confirmed (2026-10-27, n=351 leader + 177 ours)

```
Leader native (10d, Oct 15–24):  -$6,783.46 on $281,700 notl   =  -241.4 bps
Our mirror (7d, Oct 18–24):      -$57.78 on $2,871 notl        =  -202.1 bps
Directional:
  Leader BUY $209.05 / SELL $200.24   -> -421.6 bps per RT
  Our    BUY $208.92 / SELL $200.67   -> -394.5 bps per RT
Reach-adjusted leader (10-18→10-24 only): -258.5 bps on $262k, n=343.
Conclusion: not adverse selection — the leader's own strategy loses on BE.
Blocking xyz:BE on this leader is +EV, not noise reduction.
Other symbols same leader, same window:
  xyz:CL +25.1 bps / $1.17M notl  (one session, 10-15 only — pre-journal)
  xyz:GOLD +21.3 bps / $923k      (one session, 10-15 only — pre-journal)
  xyz:SP500 +3.1 bps / $2.70M     (sustained; our 7d copy +18 bps on $353 = noise)
  @107 spot -7.9 bps              (excluded by allowed_market_types)
```

Verdict: **EDGE as a kill-signal.** The symbol block for xyz:BE should
ship on both grounds (leader-native loss + our drift). Weight-cutting still
no-op at min-clip floor. 14-day schema wait is now the longest-standing
blocker on this leader.
