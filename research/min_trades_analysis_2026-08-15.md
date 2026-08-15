# `discovery.min_trades` dry-run analysis — 2026-08-15

BACKLOG P2. **No config was changed.** Reproduce with:

```
.venv/bin/python -m scripts.min_trades_analysis --limit 60 --json out.json
```

Raw output: `research/min_trades_2026-08-15.txt` (report), `research/min_trades_2026-08-15.json`
(every candidate's metrics + per-threshold rejection reason).

Snapshot: 60 leaderboard wallets, `period=30d`, `score_lookback_hours=720`, our taker fee
4.5 bps, fee-tier floor `net_edge >= 0.0 bps`.

---

## Recommendation: leave `min_trades` at 50.

Not because 50 is right, but because **the threshold is not binding and moving it changes
nothing**. Across `min_trades` ∈ {20, 30, 50} the selected set is identical — empty:

| `min_trades` | passes all screens | taken (`top_n=4`) |
|---|---|---|
| 20 | 0 | 0 |
| 30 | 0 | 0 |
| 50 | 0 | 0 |

Lowering a filter that is not the constraint buys nothing today and quietly widens the
intake the moment the leaderboard rotates. Two other things are doing the actual rejecting,
and both are worth a backlog item. **Neither is trade frequency.**

Rejection reasons, per threshold (60 candidates each):

| reason | mt=20 | mt=30 | mt=50 |
|---|---|---|---|
| `coarse_trades` (leaderboard count) | 21 | 26 | 28 |
| `equity` (solvency gate) | 21 | 18 | 18 |
| `trades` (HL fill count, quality pass) | 6 | 7 | 6 |
| `holding_p50` (turnover screen) | 6 | 5 | 5 |
| `metrics_unavailable` | 3 | 2 | 2 |
| `perp_frac` | 2 | 1 | 1 |
| `sharpe` | 1 | 1 | 0 |

---

## Finding 1 — the solvency gate is INV 1 all over again, and it is rejecting live wallets

`src/leaders._perp_equity_usd` reads `info.user_state()`, which per **INV 1** returns
**base-dex positions only**. A leader whose collateral sits on a HIP-3 builder dex therefore
reads `$0.00` and is rejected as insolvent. 18–21 of 60 candidates were dropped this way.

Verified directly, enumerating `perpDexs` and pulling `clearinghouseState` per dex:

| wallet | gate reads | actually holds | 30d perp flow | net edge at our tier |
|---|---|---|---|---|
| `0x819d06c03a` | $0 | **$626 on `xyz`** | 1,886 fills, 94% perp, $3.57M/mo | −5.68 bps |
| `0x810b41bd22` | $0 | **$62,955 on `xyz`** | 1,990 fills, 100% perp, $5.74M/mo | +51.11 bps |
| `0x2649bb0865` | $0 | **$15,109 on `xyz`** | 410 fills, 97% perp, $1.47M/mo | +296.22 bps |
| `0x9551e7d4cd` | $0 | **$8,100 on `xyz`** | (fills fetch failed) | unknown |
| `0x166866a284` | $0 | $0 everywhere — genuinely empty | 1,375 fills, 93% perp, $5.25M/mo | +147.95 bps |

Three points, in descending order of how much they should worry us:

1. **`0x819d06c03a` is our own pinned incumbent.** `config.yaml` already carries the warning
   that it "survives solely because it is pinned in `always_follow`, which bypasses every
   filter. If anyone ever unpins it, this gate will silently drop the best-evidenced leader
   we have." This run shows the mechanism: it is not marginal on equity, it reads **zero**,
   because its money is on `xyz`. It clears $500 by $126 once you look at the right dex.
2. **`0x9551e7d4cd` is the wallet the gate was built for.** `src/leaders.py` and
   `INVARIANTS.md` record it as the motivating incident — "$0 equity, 0 positions, last fill
   19.4h old", and a sweep finding "44 of the top 60 at zero perp equity". It holds **$8,100
   on `xyz`**. The original diagnosis was itself a base-dex misread, so the "44 of 60" figure
   should be treated as unverified, not as an established fact.
3. **The gate is not useless.** `0x166866a284` really is empty on every dex despite 1,375
   recent fills, so genuinely-dead wallets do exist and the gate does catch them. The problem
   is the false positives, not the idea.

**Not fixed here** — this is P2, an analysis item, and changing leader selection on a live
account is the PM's call. Suggested backlog item: make `_perp_equity_usd` dex-aware.

Design note for whoever picks it up: **do not sum across dexes.** INV 2 says each dex settles
against its own collateral. The question the gate asks is "can this wallet trade at all", so
the correct read is per-dex — pass if **any** dex clears `min_leader_equity_usd`, since a
leader trading `xyz` needs `xyz` collateral and their base balance is irrelevant to that.
Summing would reproduce exactly the mistake INV 2 records.

## Finding 2 — the 43-trade candidate is real, and lowering `min_trades` would still not admit it

`0x27388d079c` is the wallet the backlog item was written about: 43 trades/30d, rejected at
`min_trades=50` with `coarse_trades=43 < 50`. Confirmed. But dropping the threshold does not
help — at 20 and at 30 it is then rejected on `sharpe=0.00 < 0.10`.

And it should not be admitted anyway. Its economics:

```
lb_trades 43   fills 109   turn/mo $1.64M   p50 gap 157s   perp 72%   taker 100%
leader fee 4.50 bps   gross edge 4.50 bps   net edge -0.00 bps   equity $168.7k   unreal +$6.0k
```

It pays **exactly 4.50 bps** — the same undiscounted base taker tier we pay — and its gross
edge is **exactly 4.50 bps**. Its entire realized edge is consumed by its own fees, before we
pay ours. Copying it is a coin flip minus our crossing cost. The premise that a good
low-frequency candidate is being locked out by `min_trades` does not survive contact with the
numbers: the candidate exists, and it has no edge to copy.

## Finding 3 — the leaderboard itself is thin, which is the real ceiling

Of 60 wallets: **27 have zero readable perp fills in 30d** (leaderboard rank earned on HIP-4
outcomes or long stale), 5 more failed the fills fetch entirely, and only **33 have
measurable perp economics** at all. Of those 33, **12 clear `net_edge >= 0`** at our fee
tier. Every one of the 12 is then rejected by something else — mostly the equity gate
(Finding 1) or the leaderboard trade count.

This is the honest headline: we are not selecting badly from a good pool, we are screening a
pool that is mostly empty. Adjusting `min_trades` is rearranging a filter downstream of that.

## Finding 4 — our incumbent's realized 30d edge is negative before our fees

`0x819d06c03a`, weight-pinned at 2.0, over 1,886 fills and $3.57M/mo turnover: **gross edge
−1.18 bps**, leader fee 5.37 bps, **net edge at our tier −5.68 bps** (−$2.0k on that
turnover). This is realized (INV 10), not a marked opinion.

Flagging, not recommending. One 30d window on one snapshot is not grounds to unpin the
leader with our best backtested Sharpe, and the backtest and this metric measure different
things (per-trade PnL distribution vs PnL per dollar of turnover). But it is a direct
measurement that disagrees with the pin, so the PM should see it.

---

## Caveats

- Every PnL figure is **realized** (INV 10). The `unreal` column is shown per INV 9 but not
  screened on.
- `equity`/`unreal` in the main table are **base-dex only** (INV 1) — that is the bug in
  Finding 1, deliberately reproduced there so the table shows what the live gate sees. The
  per-dex figures in Finding 1 were fetched separately.
- **One snapshot, 60 wallets, one day.** A single leaderboard read is not a distribution.
  "`min_trades` is not binding" is a statement about 2026-08-15; re-run across several days
  before treating it as structural.
- `net_edge` assumes **we fill at the leader's price**. We do not — we cross the spread after
  them. Real copy edge is strictly worse, so treat `net_edge` as an upper bound and a
  marginal pass as a fail.
- The fee-tier screen (`src/copy_econ.passes_fee_tier`) is **new and not wired into
  `src/leaders.py`**. It exists in this analysis only. Adopting it is a separate decision.
