# Strategist weight review — 2026-10-18

**Recommendation: cut `0x9551e7d4` from 0.40 → 0.10 (floor-adjacent). Hold `0x511e60d3` at 1.00. No new leaders proposed.**

Config diff:
```yaml
discovery:
  leader_weights:
-   0x9551e7d4cd963558bb9882aecc74f549262e217f: 0.4
+   0x9551e7d4cd963558bb9882aecc74f549262e217f: 0.1   # down from 0.40; see §1
    0x511e60d32a1fdcafb46bae7f43cfab0a87040713: 1.0   # unchanged; see §2
```

Note the −0.30 move is inside the ±0.5/run cap (per the strategist mandate).

---

## 0 — Setup

Live config parsed fresh (not from prompt — the prompt roster was stale at 1.25/1.10, real values are 0.40/1.00):
```
discovery.leader_weights = {0x9551e7d4: 0.4, 0x511e60d3: 1.0}
discovery.always_follow  = [0x9551e7d4, 0x511e60d3]
```
Engine `Selected 2/50 leaders` confirms the live roster. 4 discovery slots sit empty — not capacity-limited; nothing clears the bar.

Journal window: 2026-09-28 → now (20 days). Caches `state/copysim_fills/*` frozen at 10-15/10-16; `scripts/copysim.py` still missing on branch so no fresh sim run — fell back to raw `userFillsByTime` + journal replay.

Gate: `work_check.py strategist` → `WORK: 162 fills in 24h, exit 1`. The 162 fills are **all outcome-maker fills** (`#118050`-style) — the strategist's leader-weight remit saw **3 perp own_fills** (yesterday's SPCX round-trip, already covered in `[[leader-511e60d3-spcx-24h-2026-10-17]]`).

---

## 1 — `0x9551e7d4` — cut to 0.10

### Live state
Base dex: flat. All equity on xyz.
```
dex=xyz   acctVal=$26,592.50   totalNtlPos=$215,742.59   (8.1× gross)
  xyz:SP500: szi=-25.830   val=$197,090.65   upnl=+$2,904.48
  xyz:BE   : szi=+86.180   val=$ 18,651.94   upnl=  -$97.38
```
Current position entries:
- `xyz:SP500` short entered 2026-10-16 03:40 UTC — 9 taker sells, 100% crossed. **Copyable in principle but entry was 2.5 days ago.**
- `xyz:BE` long entered 2026-10-15 13:59 UTC — 8 maker buys, **100% maker**. **Uncopyable** (`[[leader-511e60d3-not-perp-native]]` pattern — our taker clip crosses the spread the leader is capturing).

24h fills on xyz: **0**. Leader is sitting on the SP500/BE bag — no fresh signal flow.

### Reachable 30d/14d/7d (perp only, outcomes+spot stripped)
```
7d : reachable_n=2076/3042  closedPnl=-$290,838  fees=+$2,152  net=-$292,990   maker_frac=0.20
14d: reachable_n=2798/3780  closedPnl=-$290,838  fees=+$2,228  net=-$293,066   maker_frac=0.17
30d: reachable_n=3186/4000  closedPnl=-$283,100  fees=+$860    net=-$283,960   maker_frac=0.09
```

7d/30d dominated by **xyz:SKHX ‑$141k realized loss** when the leader finally capitulated 10-14 (same event our 10-15 report caught — leader's full bag closed for ~$144k realized vs our ‑$90.62 round-trip). The 7d figure is worse than 30d because the SKHX cascade concentrates there.

### Signal flow in our window
20-day journal has **zero reachable leader_fills attributed to `0x9551e7d4`**. The engine logs "Marked 30 snapshot fills as seen for 0x9551e7d4" every cycle — it's correctly suppressing historical cascades it would have missed anyway. In 20 days of live engine coverage, this leader has produced **no copyable signals we actually mirrored**. The one audited round-trip pre-journal (SKHX, in `[[leader-9551e7d4-skhx-roundtrip-2026-10-15]]`) cost us **‑$90.62 on a ~$230 account** — about 40%.

### Why cut, not drop
- 0.0 weight → `SystemExit` per `[[dead-leaders-at-stale-weights]]`. Minimum live weight is 0.1.
- The 10-15 report recommended *either* symbol-filter SKHX *or* floor-weight. Config was never patched, so SKHX remained enabled. We can't symbol-filter from the strategist cron (that's engine code).
- Cutting to 0.10 keeps the leader observable for shadow signal (we still get leader_fills in the journal when they move) but shrinks the clip size by 4× — per `[[weight-scales-clip-size]]`, a next SKHX-style cascade costs us at most 1/4 of what the last one did, before cap-pin blocks the rest.

### What this does NOT claim
- Not calling the leader *dead* — they hold $26.6k xyz equity and the SP500 short is in the money.
- Not claiming the edge is gone forever — the pre-SKHX windows (per cache 09-15 onward) show real activity on `@107` and `SKHX`. But the symbol concentration is the risk, and we have no evidence it's resolved.
- Not touching `always_follow` list — removing from `always_follow` lets auto-discovery re-add them at a higher default. Keep pinned, lower weight.

---

## 2 — `0x511e60d3` — hold at 1.00

### Live state
Base dex: flat. xyz: `acctVal=$33.60   totalNtlPos=$0.00` (flat).
All other HIP-3 dexes (flx, vntl, hyna, km, abcd, cash, para, mkts, io): flat.

**This leader has decapitalized.** Per `[[strategist-cron-prompt-stale]]` the config comment showed $20.5k on xyz as of some prior snapshot. Current state is $33.60. Either withdrew $20k+ or lost it off-strategy (binary outcomes — see below).

### Reachable 30d/14d/7d
```
7d : reachable_n=568/866    closedPnl=-$3,221   fees=+$819   net=-$4,040    maker_frac=0.37
14d: reachable_n=1316/2180  closedPnl=-$3,867   fees=+$995   net=-$4,862    maker_frac=0.45
30d: reachable_n=1922/4000  closedPnl=+$18,602  fees=+$591   net=+$18,011   maker_frac=0.48
```
Perp 30d is positive but all edge is in the first 2/3 of the window; 14d and 7d both net negative. Maker frac rising to 0.48 recent = even larger taker/maker gap on copy.

### Journal check (10-16 recommendation still valid)
Only reachable leader_fills from this leader in the entire 20d journal are the 10-16/10-17 SPCX round-trip:
```
10-16 19:04 B 0.32 @ $143.48
10-16 19:05 B 2.46 @ $143.48
10-17 04:24 A 1.86 @ $145.70
10-17 04:24 A 0.92 @ $145.69
```
Our copy = **+$0.44 realized + ~$0.39 unrealized on 0.2 residual** (`[[leader-511e60d3-spcx-24h-2026-10-17]]`). n=1, below the noise floor.

### Why no change
- 30d net is still positive on reachable.
- 10-16 report recommended hold 1.00 — no fresh evidence against. The one new SPCX round-trip was a clean cycle, not a cap-pin disaster.
- 10-16 also recommended symbol-filter `xyz:SPCX`; still not shipped (engine work). Not strategist's lever.
- Decapitalization to $33.60 is *concerning* but not strategist-actionable this run. If the leader stays sub-$100 next cycle, drop to 0.5 (one further step inside the ±0.5 cap).

**Decision item for executor/engine side (not for this diff):**
- Symbol filters for `xyz:SKHX` on 9551e7d4 and `xyz:SPCX`/`xyz:HOOD`/`xyz:IREN` on 511e60d3 remain unshipped from the 10-15/10-16 reports.
- 511e60d3's $33.60 xyz equity means the per-dex cap is irrelevant for them; our cap-pin failure mode is less likely to repeat on this leader until they refill.

---

## 3 — No new leaders

- 4 auto-discovery slots sit empty — same as all prior strategist runs since the pool exhaustion (`[[leader-pool-exhausted-aug16]]`). No fresh screen done this run; prior conclusions still stand (`[[low-turnover-candidates-failed]]`, `[[vault-candidates-rejected]]`, `[[hl-vaults-as-leader-source]]`).
- 24h journal shows 24 `intent_skipped` reasons from `0xe38c0163` on binary outcome markets (`#71811`/`#71801`/`#79491`/`#71751`) — correctly skipped (`market_type`). Not a candidate: outcome markets are structurally unreachable per `[[copysim-counted-unreachable-flow]]`.

---

## 4 — Guards against known traps

- **Backtest blind to unrealized** (`[[backtest-blind-to-unrealized]]`): checked. 9551e7d4 live has +$2.9k unrealized on SP500; 511e60d3 live is flat. No DailyTradeAI-style martingale bags hiding.
- **Base-dex $0 ≠ dead** (`[[reconcile-blind-to-hip3]]` et al): per-dex probed. 9551e7d4's base-dex returns $0 but xyz has $26.6k. Not treated as dead.
- **Symbol concentration**: 9551e7d4's 30d is 100% dominated by SKHX. Flagged, acted on (floor cut).
- **Maker-vs-taker edge**: 9551e7d4 BE position is 100% maker-entry (uncopyable). 511e60d3 maker_frac 0.48 recent (`[[leader-511e60d3-not-perp-native]]` pattern persists). Factored into decision (cut 9551 heavy; hold 511 at existing weight because 30d net is still positive on reachable).
- **Drawdown ≠ bag-holding**: not relying on drawdown alone — 9551e7d4 cut is driven by the realized SKHX cascade **plus** zero copy flow in 20 days, not just DD.
- **Weight scaling** (`[[weight-scales-clip-size]]`): at 0.10 instead of 0.40, the clip is $7.50 instead of $30 — right at the `min_per_trade_usd=10` floor, so some signals will skip entirely rather than fire tiny. That's acceptable for a leader we're trying to de-emphasize.
- **Clip floor interaction**: 0.10 × $30 base = $3, below the $10 min. Verify engine behavior: if `min_per_trade_usd` rejects the signal, 9551e7d4 becomes de-facto muted (same effect as dropping, without SystemExit). Acceptable outcome either way.

---

## 5 — Reproducer

Live state probes (used throughout):
```python
# Per-dex clearinghouseState
import urllib.request, json
def post(payload):
    r = urllib.request.Request("https://api.hyperliquid.xyz/info",
        data=json.dumps(payload).encode(),
        headers={"content-type":"application/json"})
    return json.load(urllib.request.urlopen(r, timeout=20))

for ldr in ("0x9551e7d4cd963558bb9882aecc74f549262e217f",
            "0x511e60d32a1fdcafb46bae7f43cfab0a87040713"):
    for dex in ["", "xyz"]:
        s = post({"type":"clearinghouseState","user":ldr,"dex":dex})
        print(ldr[:10], dex or "base", s["marginSummary"])

# Reachable-only 30d PnL
import time
now_ms = int(time.time()*1000); start = now_ms - 30*86400_000
fills = []
for dex in ["", "xyz"]:
    fills += post({"type":"userFillsByTime","user":ldr,"startTime":start,"endTime":now_ms,"dex":dex})
reachable = [f for f in fills if not str(f.get("coin","")).startswith(("#","@"))]
closed = sum(float(f.get("closedPnl") or 0) for f in reachable)
fees   = sum(float(f.get("fee") or 0) for f in reachable)
print(f"reachable 30d: n={len(reachable)} closed=${closed:+.2f} fees=${fees:+.2f} net=${closed-fees:+.2f}")
```

Journal replay (own_fills + leader_fills, perp only):
```python
import json
with open("state/journal.jsonl") as f:
    for line in f:
        e = json.loads(line)
        if e.get("event") in ("own_fill","leader_fill"):
            coin = str(e.get("coin",""))
            if coin.startswith(("#","@")): continue  # non-perp
            # ... group by (leader, coin) and sum closed_pnl/fee
```

---

## 6 — Verdict

**Cut 0x9551e7d4 weight 0.40 → 0.10.** Primary evidence: ‑$284k reachable-perp 30d PnL, zero copy signals in 20 days of live engine coverage, prior cycle cost ~40% of the account on SKHX, current live BE leg is 100%-maker and uncopyable. ±0.30 inside the ±0.5 cap.

**Hold 0x511e60d3 at 1.00.** Primary evidence: 30d reachable +$18k, 10-16 call stands, one fresh +$0.44 round-trip is noise. Decapitalization to $33.60 xyz is flagged for next run.

**No new auto-discovery leaders.** Pool exhausted; no fresh screen justified this cycle.

Quorra owns merge/deploy. 0.10 may push some signals below `min_per_trade_usd=$10` and effectively mute the leader entirely — acceptable second-order outcome.
