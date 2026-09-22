39 commits. Three themes: stop quoting things we cannot see, rebuild the market-making loop on measured economics, and make the P&L number trustworthy.

## The measurements that drove this

Full evidence and sample sizes in `MEASURED.md`.

- **YES and NO are one book.** Every trade prints on both legs at prices summing to exactly 1.000000 (n=807 matched prints, min = max = mean); `askNO == 1 − bidYES` on 142/142 live legs. "Paired quoting" was two-sided market making in a single instrument, and "hedging a one-sided fill" is crossing to flatten — one tick **by construction**.
- **Entry is free, every exit is charged.** Across 42,251 public fills: buys 0.00 bps maker or taker, maker sells 7.83, taker sells 13.73, settlement 13.27. Settling is the *expensive* exit, 3.4× dearer than selling the leg back as a maker.
- **In-play is closed to us.** 22 price moves with no score change against 2 the other way; a field goal moved our feed and moved the book zero, because it had already repriced during the drive.
- **Depth is not flow.** Four books showed $330–358 of depth at a clean 1.15% spread and had never traded — $0 volume, 0 fills, over both 24h and 7d.
- **LP rewards are dead.** $0 across four consecutive epochs, the last with front-of-book quoting, a full 24h window, 94% maker share and 57 real fills.

## Bugs fixed

| bug | consequence |
|---|---|
| quotes rested one tick **below** the touch | $384–$795 of queue ahead; zero fills in 5h on books doing ~340 trades/day |
| sizing by equal **dollars**, not shares | 20 YES against 59 NO — 39 shares naked while looking hedged |
| manual run raced the cron | 116 YES against 27 NO, a 4:1 directional position nobody chose |
| surfaces ranked by depth | capital placed in books that have never traded |
| minder left our bid resting on the leg it hedged | 202 shares from naked on a binary |
| minder paired off round-trip inventory | silently converted +bps round trips into the −18.3 bps trade |
| round-trip maker sold **below cost** | −132 bps and −1,229 bps legs; the entire realised loss |
| equity summed components | double-counted perp collateral; reported +$96 when the truth was −$28.72 |
| reconcile used a truncated endpoint | invented a phantom $75 gap |
| tier-1 paged on a deliberately disabled engine | alert fatigue on an intended state |

## Guard

`src/gamestate.py` refuses any market whose event is live, imminent, or unresolvable. Four distinct holes found and closed: competition-keyed NFL waved through as "not a sports market", `England` token-matching `New England Patriots`, unresolvable UFC, and season-long tournament markets passing because the team's *match* had just finished ($548 of quotes were sitting in those).

Each failed the same way — a confident answer to a misread question — so each now has a regression test.

## New

- `scripts/run_roundtrip_maker.py` — quotes one leg at the front of the book, offers the same leg back on fill. Never crosses, never settles.
- `scripts/equity_snapshot.py` — true P&L from `portfolio.accountValue`, netted of deposits, cross-checked against fills, prints `UNRECONCILED` rather than a confident wrong number.
- `scripts/backtest_passive_hedge.py` — killed a fix I was confident in (−0.93% vs −0.78%) before it shipped.
- `MEASURED.md` / `START_HERE.md` — dated findings with sample sizes; a router marking which docs are current.
- `.claude/agents/quant-researcher.md` + `research/QUESTIONS.md` — adversarial research agent and its queue.

## Test plan

827 tests passing, ruff/mypy clean. Every bug above has a regression test naming the date, the measurement and the damage.

Live on mainnet since 2026-09-21 17:46Z: 63 fills, 87% maker share (the old configuration ran 50%).

## Not fixed

Inventory accumulates faster than it clears (buys ~6:1 over sells). The cost floor added here stops loss-making exits but makes positions sit longer. That trade-off is the next measurement.
