# copysim outcome-market accounting — audit — 2026-09-26

**BUG CONFIRMED. Two independent flaws in `scripts/copysim.py`. Net effect on
0x511e60d3 outcome-only 30d: `+$102` → `−$151` (delta −$253). Sample: n=976
outcome fills / 145 coins / 128 settlements over 2026-08-25 → 09-24.**

## Workspace state

`MEASURED.md` and `research/QUESTIONS.md` and `.claude/agents/quant-researcher.md`
still live on `feat/inplay-guard-pair-maker`, not on the current branch
`exec/maker-shadow-harness`. Same finding as `research/oil-lag-2026-09-24.md`
and `research/mm-model-spec-2026-09-25.md`. Writing the report here; the
`MEASURED.md` graft delta is at the bottom.

Question worked: **research/QUESTIONS.md → OPEN §0** — "AUDIT copysim's
outcome-market accounting".

## What copysim does wrong

Two bugs, in the order they bite.

### Bug 1 — `px <= 0` silently drops losing settlement fills

`scripts/copysim.py:92`:

```python
if leader_sz == 0 or px <= 0:
    continue
```

The intent looks defensive (skip zero-size or zero-price rows). The effect is
that **every settlement of a losing outcome** — which HL emits as a real
`userFillsByTime` row with `dir=Settlement`, `side=A`, `px=0.0`, size = the
holder's full position — is discarded.

Winning settlements (`px=1.0`, `side=A`) are not dropped and are processed as
normal reducing fills. Copysim therefore books wins and silently omits losses.

**Measured on 0x511e60d3, 30d:**

| bucket | n |
|---|---|
| `dir=Settlement`, `px=1.0` | 95 |
| `dir=Settlement`, `px=0.0` | 33 |
| non-settlement outcome | 848 |

The 33 dropped fills carried the leader's own losing-outcome exposure. On the
leader's own book they contributed −$1,836.60 of realised outcome PnL (the
`+47.77` net of settlements is 95 wins minus 33 losses at leader size).

### Bug 2 — copysim opens **shorts** on outcome markets

Line 132 signs `our_sz` off `leader_sz`. When a leader sells and our residual
position is already zero (typical after Bug 3, below, has flattened us), the
`reducing` branch is skipped and the code opens a new position — with the
short sign. Outcome legs are bid-only on HL; the trade cannot exist.

On 0x511e60d3 30d, this fires **38 times** on outcome coins. The end-of-window
position book copysim carries has all-negative sizes at negative cost basis
(nine coins, $−390 nominal). Every one of those "positions" is fictional.

### Bug 3 — one reducing fill flattens our whole position

Line 101 `close_sz = min(abs(cur), abs(cur))` is `abs(cur)`. Any leader
reducing signal, regardless of size, closes our full position. A leader who
scales in over five fills then trims one clip has us fully out. This is what
sets up Bug 2 — a subsequent leader-sell then finds `cur == 0` and reopens
short.

## Size of the mismodelling

Same 30d cached fills, `clip=$30`, `cap=$400`, `fee=4.5 bps`, `slip=5 bps`:

| leader (30d) | broken copysim | Bug-1 fixed | Δ |
|---|---:|---:|---:|
| 0x511e60d3 outcome-only | **+102.08** | **−151.31** | −253.39 |
| 0x511e60d3 all markets  | −157.53 | −233.24 | −75.72 |
| 0xa3f996f2 outcome-only | +374.55 | +421.55 | +47.00 |
| 0xa3f996f2 all markets  | +23.35  | −180.39 | **−203.74** |
| 0x9636dc55 outcome-only | +136.98 | +106.96 | −30.03 |
| 0x9551e7d4 (no outcome) | +43.64  | +43.64  | 0 |
| 0x7d7c7d28 (no outcome) | −9.05   | −9.05   | 0 |
| 0x654016a8 (no outcome) | −106.49 | −106.49 | 0 |
| 0x7491180d (no outcome) | −215.74 | −215.74 | 0 |

Bug 1 alone flips a wallet's sign (0x511e60d3) and moves another by −$204
(0xa3f996f2 all-markets). Bugs 2 and 3 further contaminate the residual "open"
column but the numbers there were never used in a decision, so I have not tried
to isolate them.

Perp-only leaders (5 of 7 above) are unaffected because perps don't settle.

## Which decisions rested on the contaminated number?

Grepping `MEASURED.md` and prior research the contaminated `+$107` shows up
in exactly one place — the sixth paragraph of the "leader capital efficiency"
block, where it is already flagged as suspect. Every live-config decision has
been made against `--markets perp` copysim since the memory note
`copysim counted unreachable flow` on 2026-09-22, and perp numbers are clean.
The direction of the 0xa3f996f2 weight cut (0.60 → 0.30) survives — its true
all-markets PnL is worse than the broken version reported, not better.

## Fix, minimal and testable

`scripts/copysim.py:92` — reject only genuinely bad rows:

```python
if leader_sz == 0:
    continue
if px < 0:
    continue
# px == 0.0 is a real settlement for a losing outcome — process it.
```

`scripts/copysim.py:132` — refuse short opens on outcome/spot:

```python
if leader_sz < 0 and market_type(coin) in ("outcome", "spot") and pos[coin] <= 0:
    continue  # cannot short a bid-only market
```

`scripts/copysim.py:101` — proportional close, not flatten:

```python
close_sz = min(abs(cur), abs(leader_sz) * (want / abs(leader_sz) if want else 0))
# or, simplest: close_sz = abs(cur) * min(1.0, abs(leader_sz) / max(cumulative_leader_pos, 1e-9))
```

Bug 3 is harder to fix cleanly — leader cumulative position needs to be
tracked separately. Leaving it as a follow-up; the Bug-1 fix alone is what
carries the sign-flip.

**Regression test:** feed a two-fill sequence `[Buy 100 @ 0.30, Settlement 100
@ 0.00, side=A]` on an outcome coin. Broken copysim returns realised = 0
(second fill dropped). Fixed copysim returns realised ≈ −$30 minus fees. Test
the same with `px=1.00` and confirm existing +$70 behaviour is preserved.

## Verdict

**BUG. Fix and add the regression test before running copysim without
`--markets perp` again.** Do not treat any historical all-markets copysim
output as evidence — including the +$107 on 0x511e60d3 that raised this
question. Perp-only numbers stand.

## MEASURED.md graft (for the strategy branch)

Append under "HIP-4 outcome markets → Leader capital efficiency":

> **copysim outcome accounting — 2026-09-26.** `scripts/copysim.py:92` silently
> drops `px == 0` settlement fills, so losing outcome resolves are booked as
> zero while winning ones close normally. On 0x511e60d3 30d, fixing this alone
> moves outcome-only copy-PnL from +$102 to −$151 (n=976 fills, 33 dropped
> settlements). Bugs 2 and 3 additionally open phantom shorts and over-flatten
> on partial reduces; net effect: any all-markets copysim number pre-fix is
> unsafe. `--markets perp` was and remains clean. `research/copysim-outcome-audit-2026-09-26.md`.

## QUESTIONS.md graft

Move §0 from OPEN to ANSWERED with the line:

> **copysim outcome-market accounting** — BUG, closed 2026-09-26. Line 92
> `px <= 0` guard drops losing settlements; line 132 opens phantom outcome
> shorts; line 101 over-flattens on partial reduces. On 0x511e60d3 the
> `+$107` is `−$151` once losing settlements are counted. Every past
> all-markets copysim number is contaminated; every `--markets perp` number
> is unaffected. `research/copysim-outcome-audit-2026-09-26.md`.
