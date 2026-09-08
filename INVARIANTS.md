# INVARIANTS.md — rules that cost us real money to learn

Hard rules for anything touching this bot. Every one of these is here because
it broke in production, with the date and the damage. If a change violates one,
it is wrong even when the tests are green.

---

## 1. `user_state` returns BASE-dex positions ONLY

HIP-3 builder dexes (`xyz:`, `flx:`, …) are **separate clearinghouses**. They do
not appear in `info.user_state()`. Any code that reads positions from
`user_state` alone is wrong on this account.

Broke three separate modules on 2026-08-15, same root cause each time:

| module | symptom | damage |
|---|---|---|
| `risk_snapshot` / `derisk` | xyz positions invisible | risk reported on a partial book |
| `positions.reconcile` | zeroed all xyz every cycle (27x in a day) | sizing broke, SP500 stacked to 7x; per-dex cap read $0 vs $339 real |
| `leader_reconcile` | every xyz mirror classified `orphan` | tried to auto-close 6 live positions |

**Rule:** enumerate dexes via `perpDexs`, then
`clearinghouseState{user, dex}` per dex, and merge. Do NOT special-case `xyz`.

## 2. Each dex settles against its OWN collateral — never sum across them

Verified 2026-08-15: base at 2.4x maintenance coverage while xyz sat at 14.6x.
A single shared exposure cap blocked **40 of 40** opens, 39 of them `xyz:SP500`
— 64% of our best leader's flow. Cap **per clearinghouse** (`risk.max_dex_exposure_usd`).

## 3. Free collateral is unencumbered SPOT USDC, not perp `withdrawable`

Unified margin: every clearinghouse settles against one spot USDC balance,
holding against it per position. Proved to 6dp — `xyz marginUsed 64.424287` ==
`spot hold 64.424287`.

Base `withdrawable` reads `$0.00` whenever no base position is open. That means
*"nothing held yet"*, **not** *"no money"*. Gating on it blocked every base-perp
open while $151.78 sat free.

## 4. UNKNOWN is never EMPTY — fail open on reads

A fetch that fails means *we don't know*, and "don't know" must never be
actioned as "nothing there". Both 2026-08-15 position bugs were this mistake.

- Unreadable dex → **hold** local positions, don't zero them.
- Incomplete leader book → **UNKNOWN**, never **ORPHAN** (orphan auto-closes).
- No readable leader at all → skip the cycle entirely.
- Return `None`, not `0.0`, from a failed probe, so callers can tell the
  difference.

**But fail-open must not become never-act:** a *readable* source that no longer
reports a position still means closed. Always test BOTH directions.

## 5. A guard that silently drops trades is a bug, not safety

Every headline loss this month was suppression, not bad trading:

- exposure cap → best leader placed **ZERO orders in 30 days** ($96,595 missed notional)
- `fixed_usd == min_per_trade_usd` + floor-rounding → leader **muted 24 days**
- szDecimals guess → poison cooldown, **5,366** blocked opens
- 2,449,814 skips in 30d all journalled as one opaque `"filter"`

**Rule:** every skip path gets its own greppable reason. A default that disables
a whole surface (e.g. a per-dex cap defaulting to `0`) is a silent kill switch.

## 6. Never hand-start the engine

`systemd` owns it (`Restart=always`). A manual `setsid`/`nohup` on top produces
TWO live engines and double-trades. Use `sudo systemctl {status,restart} hyper-trader`.

`pgrep -f "src.main"` **matches its own shell command** — it never clears, and
that lie caused a real double-run. Count with:
`ps -eo pid,cmd | grep '[s]rc.main' | wc -l` (must be exactly 1).

## 7. `systemctl is-active` is NOT proof we are trading

A startup that aborted after opening the websocket kept its PID alive (non-daemon
thread), so systemd, the watchdog and the operator all reported healthy while the
bot traded nothing. Fixed via `os._exit`, but **always confirm
`Following N leaders` in `state/main.log` after a restart.**

Also: never run `--preflight` and restart within the same minute — HL
rate-limits the back-to-back `meta` calls and 429s the startup.

## 8. Never test a failure path by running `python -m src.main`

The API URL comes from `network.hyperliquid_env` in config — **environment
variables do NOT override it**. Doing this starts a REAL SECOND LIVE ENGINE.
Done accidentally on 2026-08-15; it ran 75s. No double-trade only because
tid-marking held. Use a subprocess harness instead.

## 9. The backtest is blind to unrealized losses

`src/backtest.py` scores only `closedPnl`. A martingale that closes only winners
backtests **perfectly**: `0xe2823659` showed 100% hit / sharpe +2.59 / maxDD
$0.00 while holding **−$3.34M unrealized at 10.6x**.

**Rule:** before adding any leader, pull `clearinghouseState` and reject on
unrealized loss > ~30% of equity, extreme leverage, or an implausibly perfect
hit rate against large never-realized volume. Realized-fill stats alone have
produced **five** false positives.

## 10. Judge on REALIZED PnL, not unrealized

Guilty of this on 2026-08-15: called xyz "the surface that works" on +$12.48
unrealized while its realized was **−$87.03**. Unrealized is a marked opinion;
realized is a fact.

## 11. The bot's key is an AGENT wallet

Signer `0x891b0526…` ≠ account `0xE5031860…`. HL permits agent wallets to trade
but **blocks transfers and withdrawals**. Fund movements need the master wallet
— they cannot be automated from this box, and that boundary is a feature.

## 12. Weight and minimum size interact

`fixed_usd × weight` must clear `min_per_trade_usd` **after** floor-rounding, or
the leader is silently muted. At `fixed_usd=30`, any weight ≤ 0.34 mutes
entirely. To mute a leader, **drop it explicitly** — never by a weight that
happens to round to nothing.

## 13. Raising clip size changes WHICH leaders are executable

At $10 clips, sub-second scalpers were harmless — every clip floor-rounded below
the minimum and was dropped. At $30 they clear it and become real orders.
`0x25773676` (~2.43M fills/30d) would have fired tens of thousands of live
orders a day. Re-check `discovery.min_holding_time_s` whenever `fixed_usd` moves.
