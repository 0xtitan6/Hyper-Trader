# START_HERE.md — the one file to read first

This repo has ~2,100 lines of docs across 12 files. Most of a session used to be
spent rediscovering which ones are true. This routes you in one hop.

**Nothing here restates content.** It says which file answers which question,
and — just as important — which files are historical and must not be acted on.

---

## Route by what you are about to do

| I want to… | Read | Status |
|---|---|---|
| propose or size a **strategy** | **`MEASURED.md`** | ✅ current |
| change **code** that touches live orders | **`INVARIANTS.md`** | ⚠️ current but predates 09-19 |
| understand **margin / settlement / PnL** on HL | `RULES.md` §"Trading concepts" | ✅ evergreen |
| know what I may do **without asking** | `RULES.md` §"Decision authority" | ✅ evergreen |
| **set up** the repo, handle secrets | `AGENTS.md` | ✅ evergreen |
| respond to a **live incident** | `TRADING_AGENT.md` | ✅ evergreen |
| decide whether to **add capital** | `CAPITAL_LADDER.md` | ⚠️ gates assume the copy engine |
| pick up **queued work** | `BACKLOG.md` | ✅ current |
| **fork / redeploy** the stack | `SELF_HOST.md` | ✅ current |
| find a **research thread** | `RESEARCH_BACKLOG.md` | 🕰️ May 2026, historical |
| see May 2026 maker experiments | `WATCH.md` | 🕰️ historical — see warning |

## Read these two before anything else

**`MEASURED.md`** — every market finding with a date, a sample size and a
verdict. Most "new" ideas are already in there, measured and killed. It opens
with the trap that has now cost us money four times in four disguises: *a wide
spread or deep book on something nobody trades is danger money.* Check a
strategy against this file before writing code for it.

**`INVARIANTS.md`** — code rules, each one present because it broke in
production, with the date and the damage. If a change violates one it is wrong
even when the tests pass.

The split is deliberate: `MEASURED.md` is what the **market** does,
`INVARIANTS.md` is what the **code** must do.

---

## Never trust a doc for live state

Docs describing "current" positions, balances or processes go stale silently and
are the most dangerous thing in this repo — `WATCH.md` carried a May 2026
snapshot labelled "Current run state" for four months, listing an open position
that had long since settled and describing the copy engine as disabled while it
was running.

**Always read live state from the exchange or the box:**

```bash
.venv/bin/python scripts/status.py          # account, positions, health
systemctl list-timers --all | grep hip4     # what is actually scheduled
tail -5 state/main.log state/pair_minder.log
openclaw cron list                          # agent crons
```

Dated snapshots inside docs are history, never truth.

---

## The standing rules, in one place

1. **`./KILL` stops both order paths** — the mirror engine and
   `leader_reconcile` auto-close. Set `leader_exit_auto_close: false` before any
   cold boot.
2. **Never print, log, journal or commit `HL_PRIVATE_KEY`** or anything derived
   from it — not into transcripts, not masked. Secrets live in
   `~/.config/hyper-trader/copytrader.env` (0600), outside the workspace.
3. **Positions we did not open belong to the operator.** Report on them; never
   close one without being asked. (2026-09-20: a position was sold on "watch my
   position" — a −$24 lesson in reading the verb.)
4. **Never rank a trading surface by spread or depth.** Rank by realised flow.
   See the trap table in `MEASURED.md`.
5. **Never quote a live event.** Measured 6.68% in-play vs 0.17% pre-match
   paired edge — that gap is someone knowing the score before the book does.

---

## Layout

```
START_HERE.md      you are here — the router
MEASURED.md        what the market does      (findings, dated, with n)
INVARIANTS.md      what the code must do     (rules, dated, with damage)
RULES.md           trading concepts + authority
AGENTS.md          setup, secrets, conventions
TRADING_AGENT.md   incident playbook
BACKLOG.md         queued work
CAPITAL_LADDER.md  capital gates
SELF_HOST.md       fork and redeploy
docs/              deep dives (HIP-4 greeks, strip design, SDK patches)
research/          dated investigation dumps — raw, superseded by MEASURED.md
```
