# audit_pnl.py — ops readme

Persistent, no-double-count PnL snapshot for the Hyperliquid account. Built after 2026-09-24 incident where three different totals were reported within an hour due to (a) summing the unified spot pool per-dex and (b) valuing HIP-4 outcome tokens at $1.

## Run

```
cd /home/ec2-user/.openclaw/workspace/hyper-trader
.venv/bin/python scripts/audit_pnl.py                       # snapshot
.venv/bin/python scripts/audit_pnl.py --diff state/pnl_audit_<PREV>.json   # + reconciliation vs previous
```

Exit code 0 = `verified: true`. Exit code 2 = at least one component was unavailable or an outcome token had no mid; the snapshot is still emitted, but the grand total is a lower bound.

Output goes to stdout AND `state/pnl_audit_<UTC-timestamp>.json`.

## What each field means

- `verified`: `true` only if every one of the 12 perp surfaces (1 base + 10 HIP-3) plus base spot plus `allMids` fetched cleanly AND every non-zero outcome token has a mid. Anything else -> `false`.
- `sources_queried`: which HL endpoints actually returned data. Cross-check against expected 12 perp calls + 1 spot + 1 verify + 1 mids.
- `components.base_perp` / `hip3_perps.<dex>`: `clearinghouseState` for each surface. `equity_usd = marginSummary.accountValue`. `unrealized_pnl_usd = sum(assetPositions[].position.unrealizedPnl)`.
- `components.spot_usdc`: the UNIFIED USDC pool. Base spot and every HIP-3 dex spot return the same balances — this is one pool viewed from N contexts. The script verifies this by re-querying under `dex=xyz` and comparing; it then counts USDC exactly once. NEVER add per-dex spot views.
- `components.hip4_outcome_tokens`: every non-zero HIP-4 outcome balance (`coin` starts with `+`), priced from `allMids` where `+XXXXY` in the balance maps to `#XXXXY` in mids. YES/NO pairs like `+42950` / `+42951` are on the same event; their mids sum to ~1.00 at any time, and to exactly $1.00 at resolution.
- `totals.grand_total_usd`: `base_perp_equity + sum(hip3_perp_equity) + spot_usdc + sum(outcome_mv)`. Unpriced outcomes are EXCLUDED (they contribute entry notional to a side-channel field so their size is visible but not double-counted).
- `issues[]`: every anomaly encountered — rate limits, unpriced outcome tokens, unknown coins. If this list is empty AND `verified: true`, trust the grand total.
- `reconciliation`: only populated when `--diff` is passed. Delta vs previous snapshot broken down by component so a $X change is attributable to base-perp / hip3 / spot / outcome.

## When to trust the number

- `verified: true` and `issues: []`: this is the number. Use it.
- `verified: true` and issues names benign coins (`unknown spot coin USDE (0 units)` etc.): trust the number.
- `verified: false` because ONE HIP-3 dex 429'd: rerun in 60s; single-dex misses are usually rate-limit, not real. `grand_total_usd` is a lower bound short one dex's equity.
- `verified: false` because outcome tokens are unpriced: the mid is missing on `allMids`. Grand total excludes them; `hip4_outcome_unpriced_entry_ntl_usd` shows how much sunk cost is unpriced. This is the "worst case underreport"; the real mark is usually close to entry unless the market resolved.
- If you see the grand total change by >$50 with no trading activity, run `--diff` against the previous snapshot and read `delta_by_component_usd` — one line will explain it.

## Outcome token pairs

HIP-4 outcome markets are binaries: for every event, HL mints a YES token (`+XXXX0`) and a NO token (`+XXXX1`). At resolution the winner pays $1 and the loser pays $0, so YES_mid + NO_mid ~= 1.00 at all times. If we hold both sides of the same event in equal size, that leg is worth ~ (size * $1.00) regardless of the mid ratio — this script does NOT net paired outcomes automatically; it just marks each side at its own mid. A neutralized YES+NO position will therefore show the correct total value (because the two mids sum to 1), but any drift due to slippage on entry stays visible in the per-token view.

## Bugs the script actively prevents

1. **Double-counting the spot pool.** The `verify_spot_is_unified` step compares base spot balances to the `xyz` spot view; equal -> summed once. If they diverge, an issue is flagged and the script still refuses to sum per-dex.
2. **Outcome tokens at $1.** Every non-USDC, non-stablecoin spot balance is priced from `allMids` (mapping `+` -> `#`). If a mid is missing, the token is labeled `unpriced` and left OUT of the grand total.
3. **Silent partial reports.** Every failed component is emitted with `confidence: unavailable` and appended to `issues`; `verified` flips to `false`. No component is ever silently omitted.

## Files

- Script: `scripts/audit_pnl.py`
- Snapshots: `state/pnl_audit_<UTC-timestamp>.json`
- Env source: `~/.config/hyper-trader/copytrader.env` (`HL_ACCOUNT_ADDRESS=`)
