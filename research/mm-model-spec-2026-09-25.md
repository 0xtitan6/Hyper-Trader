# A real MM model for HIP-4 outcome markets — 2026-09-25

**UNPROVEN. Spec, not evidence. Sourced primarily from Avellaneda-Stoikov
(2008) and Guéant-Lehalle-Fernandez-Tapia (2013); adapted to a bounded-price,
binary-payoff, bid-only book. No shadow run yet. n=0 fills against this model.**

The one testable prediction up front: at our measured markout (+7.73 bps of
face at 60 s, n=1,012 third-party passive fills) and measured book spread
(29.5 bps, n=142 legs), an inventory-skewed A-S quote that never crosses and
never settles should realise **+3.8 to +7.7 bps of face per round-trip**
before drift. That is the same "realistic" cell already in MEASURED.md's
paired-quoting table — the model does not conjure new edge. What it does is
convert a hand-rules bot ("one tick inside, never below cost, pull at T-3h")
into a state-machine that (a) prices fair value off the liquid twin, (b) skews
its two-sided quote against its own inventory, and (c) is honest about the
binary terminal payoff.

## Workspace state, up front

`MEASURED.md`, `research/QUESTIONS.md`, `.claude/agents/quant-researcher.md`
still do not exist on `exec/maker-shadow-harness` (they live on
`feat/inplay-guard-pair-maker`). Same finding as
`research/oil-lag-2026-09-24.md`. Writing this file to the current branch and
appending the graft deltas at the bottom, per that precedent. The branch
mismatch is now on its second cron; it should be fixed before the next run or
we will keep writing findings the strategy branch never sees.

## What "credible open work" this is anchored to

All borrowed pieces cited by (author, year); anything not tagged is ours.

- **Avellaneda-Stoikov (2008), "High-frequency trading in a limit order book"**
  (Quantitative Finance 8(3)) — the canonical inventory-skewed two-sided
  quoting model. Reservation price shifts against inventory linearly in
  γσ²(T−t); optimal half-spread is the sum of an inventory-risk term and an
  order-flow term. The math is a HJB on a mid that is a Brownian motion with
  no drift. We use its **quoting rule**, not its diffusion assumption.
- **Guéant, Lehalle, Fernandez-Tapia (2013), "Dealing with the inventory risk"**
  (Mathematics and Financial Economics 7(4)) — closed-form asymptotics of A-S
  under an inventory ceiling. This is the one that matters for us because our
  inventory ceiling is not a preference, it is a hard exchange constraint (we
  cannot short an outcome leg). Their Corollary 4 gives spread offsets as a
  bounded function of q/q_max rather than the unbounded linear A-S formula,
  which we would blow past in one fill.
- **Cartea, Jaimungal, Penalva (2015), "Algorithmic and High-Frequency
  Trading"** (Cambridge UP) — Chapter 10 catalogues MM under bounded inventory
  and adverse selection, with a clean derivation of the "if fills are Poisson
  with intensity λ(δ) = A exp(−κδ), the optimal half-spread is δ* = 1/κ +
  γσ²(T−t)". We use their κ estimator (log-linear fit of fill probability vs
  distance-from-mid) because it is what we can measure from `own_fill` +
  `book_snapshots`.
- **Hummingbot's `pure_market_making` strategy** — production reference for how
  the A-S reservation price gets discretised to tick-priced levels, and for
  the inventory-target skew (they parameterise as
  `inventory_target_base_pct`). Public: github.com/hummingbot/hummingbot,
  strategies/pure_market_making. The **queue/tick discretisation** and the
  **per-side minimum size** we borrow from there.
- **Hanson (2003), "Combinatorial information market design"** — LMSR. Cited
  only to explain what we are *not* doing. LMSR is an automated market maker
  (a bonding curve the venue runs). We are a taker of the venue's order book,
  not a subsidised counterparty. The prediction-market vocabulary
  ("outcome", "settlement", "1 − p") is Hanson's, the mechanics are not.
- **Wolfers-Zitzewitz (2004), "Prediction markets"** (JEP 18(2)) — empirical
  properties of binary prediction markets: strong favourite-longshot bias in
  most venues (already tested and absent on HL — slope 1.034, p=0.74, per
  MEASURED.md), and the fact that prices behave as reasonably-calibrated
  probabilities near expiry. We use their result to justify one assumption in
  §4 (terminal price is a valid probability estimate at T−6h).

Anything not on this list is ours and flagged.

## Our constraints, in the shape the literature uses

Restated so the spec below can refer back to them.

| A-S symbol | our meaning | value / source |
|---|---|---|
| s | mid of a leg | dynamic; read from L2 |
| s* | fair value of a leg | **liquid twin's mid** (see §1) |
| q | inventory in shares of one leg | integer, `state.positions.get(oid, 0)` |
| q_max | inventory ceiling | operator-set surface cap. Not in code today; use `$60 / p̂` shares of the more expensive leg, where p̂ is our current fair-value estimate. Ours. |
| T − t | seconds to forced exit | forced exit at T−6h (kickoff −3h buffer −3h safety). Ours; MEASURED.md §"3h kickoff buffer costs" argues for the buffer, safety hour is a choice. |
| σ² | variance of s over (T−t) | fit from candles when a twin exists; else from own book snapshot autocorrelation |
| γ | risk aversion | grid: {0.1, 0.5, 1.0, 5.0, 20.0} on shadow; **default 1.0** |
| κ | order-flow decay | log-linear fit of P(fill within Δt) vs (δ / face) on own `own_fill` / `maker_quote` journal, per Cartea et al. Fit per surface-family (soccer, NFL, xyz binary), not per surface — we do not have enough fills per surface (n=17 total live fills to date). |
| A | order-flow scale | co-fit with κ; A cancels in the optimal-δ formula so this is only needed for expected P&L, not for the quote |
| Terminal payoff | 1{outcome} − p | binary; see §4 |

`s*` from the liquid twin is the single biggest departure from A-S. In A-S you
never see the fair value; you diffuse the mid and hope. In our market you
often **do** see it, for free, on another book. §1 spells out when and how.

## 1. Fair value from the liquid twin

The finding from MEASURED.md this rests on: for every match, HIP-4 lists a
"YES/NO" pair on **two venues** — a liquid `out`-family venue and a wider
`txyz`-family venue. Measured 2026-09-22: Browns 17 bps on 2,052 trades vs
Panthers (mirror) 118 bps on 8 trades; Lions locked at 0 bps vs Jets 142 bps.
Same event, two books.

**Detection.** Two markets are a twin pair iff (i) same underlying descriptor
(`outcomeMeta.template` matches on team names, or same `perp:xyz:*` root and
same threshold/expiry), (ii) trade-count ratio > 20:1 in the last 24 h, (iii)
the *product* of their two mids projects to a valid probability
(`|p_liquid + p_wide,complement − 1| < 0.02`, i.e. they price the same event).

The liquid twin gives `s*_liquid`. Translate to the wide leg by:

```
p_yes  ← liquid_mid_yes                       # our best guess of P(YES)
s*_wide_yes ← p_yes                           # same underlying, no basis
s*_wide_no  ← 1 − p_yes
```

**What we do when the twin is also thin (both wide, no reference).** Fall back
to the *third-party consensus* — best bid + best ask of the wide leg minus the
midpoint half-spread — and widen γ by ×2 in that regime. This is Cartea et
al.'s "no reference price, quote defensively" rule; the ×2 is ours and needs
tuning.

**Freshness.** The liquid twin's mid is only useful if we resample fast
enough. Barrier tests (`research/barrier-lag-2026-09-22/`) put barrier requote
life at 3.8 s; sports twins are much slower (pre-match a mid can sit for
minutes). Rule: resample `s*` when either (a) the liquid twin's mid ticked, or
(b) 20 s have passed. If the twin's mid ticks past our current quoted price,
**pull first, replace after**. Do not skip the pull — it is the single
mechanism that closes the "we sat on a stale bid while the twin already
moved" hole that Giants/Croatia cost us (see MEASURED.md, first-real-fills).

**When the twins disagree by > 3 %.** Something is happening on one book that
the other has not caught (news landing on the liquid one, or spike-on-thin on
the wide one). MEASURED.md's guard-hole log includes this shape at
Manchester City vs Sunderland full-time. Rule: refuse to quote for 30 s;
sample again; if still > 3 % apart, pull for the session.

## 2. The A-S reservation price, discretised

Continuous form (A-S 2008, eq. (7)):
```
r(s*, q, t) = s* − q · γ · σ² · (T − t)
```
Two changes to it, both required by our constraints:

**Change 1 — bounded inventory (Guéant et al. Cor. 4).** With a hard cap
q_max, the linear skew blows up as q → q_max. GLFT replace the linear term
with:

```
r(s*, q, t) = s* − ξ(q / q_max) · γ · σ² · (T − t)
where ξ(u) = tanh(u / (1 − u²))  for u ∈ (−1, 1)
```

This is ours: it is *a* bounded odd function with GLFT's asymptotics (linear
near 0, diverges at ±1). GLFT's exact form involves solving an ODE. If ξ
matters much we pick the ODE form; the tanh is a placeholder that gets us
into shadow without a numerical solver.

**Change 2 — bid-only, one-sided.** We cannot short. The bid is at
`r − δ_bid`; the ask is either unavailable (we hold nothing to sell) or at
`r + δ_ask` (if we hold ≥ 1 share).

The A-S optimal half-spread is δ* = (1/κ) + (γ σ² (T−t))/2. Two halves:

```
δ_bid = (1/κ) + (γ σ² (T − t)) / 2
δ_ask = same, plus a floor: max(δ_ask, entry_price + settle_fee_bps/1e4)
```

The floor on δ_ask is **the "never sell below cost" rule already in the bot**,
tightened to also cover settlement fee (13.27 bps of face). Without it, at
γ → 0 the model wants to unwind at any price. Ours; ships as a hard rail, not
a preference.

## 3. Sizing: shares, $10 minimum, whole-share legs

A-S / GLFT are size-agnostic. Sizing is entirely ours, but the constraints are
exchange-hard. Two facts collide:

- `outcome_min_per_trade_usd = 10` (from `config.yaml`).
- Whole-share legs. On a leg trading at 0.03 you cannot post $10 worth
  (333.3 shares → 333 shares → $9.99, rejected). On a leg at 0.98 the minimum
  is 11 shares ($10.78).

Rule for the primary bid at each level:

```
n_shares = max(11, ceil(10 / p̂))
notional = n_shares × p̂
```

That is *at least* $10; on high-priced legs it is naturally $10-11; on
low-priced legs it steps up in $0.03-$0.05 increments. We only quote a level
if `n_shares × (1 − p̂) ≤ residual_surface_cap` (buying the *complement* of
what we already hold cannot breach the cap).

**Only one level per side to start.** Cartea et al. show gains from ladders
when the flow intensity is high; ours is not (17 fills in 4 months on the
existing bot). Add ladders after the shadow run proves the single-level model
covers costs.

## 4. Terminal payoff: binary, not linear

A-S/GLFT use a terminal inventory penalty `-γ σ² q² (T − T)² / 2` that
vanishes at t = T. In a binary-payoff market, at settlement:
- if YES: our q shares of YES pay 1.00 each, our q' shares of NO pay 0.00
- if NO: reversed
- our expected terminal PnL is `q · p_settle + q' · (1 − p_settle) − cost`

`p_settle` is not σ² — it is a Bernoulli success rate. This changes the
inventory-risk term at long horizons: A-S's "risk grows with T-t" is right
locally, but at settlement the risk is *bounded* by `q · p_settle · (1 −
p_settle)`, max 0.25·q² at p=0.5.

**Rule.** Replace `σ²·(T−t)` in the reservation price with:

```
Var[terminal | now] = p̂ · (1 − p̂) · shrinkage(t)
shrinkage(t) = min(1, (T−t) / T_shrink)   with T_shrink = 6h
```

The shrinkage is Wolfers-Zitzewitz's empirical result that prediction-market
prices are well-calibrated near expiry — variance realises down as t → T.
`T_shrink = 6h` matches our forced-exit horizon; before that, treat variance
as fully bounded by `p̂(1 − p̂)`. Ours (the mapping); the p(1-p) form is not
new.

**Forced-exit rule at T − 6 h.** If we have not passively unwound by 6 h
before kickoff:
1. Compute settle-cost (13.27 bps of face) vs cross-cost (current spread).
2. If cross-cost + drift-risk (from measured markout at 30 s) < settle-cost,
   IOC-flatten. Else hold to settlement.

Measured today: cross costs the spread (median 29.5 bps, but if wide much
more); settle costs 13.27 bps flat. In most cases holding to settlement will
win at T-6h. This is one of two places the current bot is likely wrong —
`hedge_decision` today crosses at *any* profitable price rather than
comparing to settle.

## 5. What to measure to know it is working — and what would falsify it

Shadow metrics (`analysis/mm_model_shadow_YYYYMMDD.md`, generated by a new
`scripts/mm_shadow.py`):

| metric | target | falsifies at |
|---|---|---|
| P(fill within 60s at δ*) | matches κ-fit within ±20 % | fit is wrong; re-estimate κ |
| markout at 60 s per fill | ≥ +5 bps of face (measured median +7.73) | ≤ 0 → we are being picked off |
| twin-tracking error `s* − s_wide,mid` post-tick | median < 1 tick within 20 s | twin resample cadence too slow |
| inventory z-score `q / q_max` | median \|z\| < 0.4 | skew is too weak — raise γ |
| completed round-trips / day / surface | ≥ 3 to clear $0.50 at $25 legs | dead surface, drop from watchlist |
| net bps of face per round-trip | ≥ +3.8 (paired-quoting "realistic" cell) | model captures no edge over hand rules |

**What would falsify the whole spec.** If, after ≥ 200 shadow round-trips
across ≥ 5 surfaces, net bps of face is below 0 or the two-sided fill rate is
below what the hand-rules bot achieves at matched cap, kill the model. The
liquid-twin fair value is the largest single novel component; a false-positive
on that (i.e. twin ≠ same event, we misclassified a pair) is where I would
look first.

## 6. Interfaces and kill-switches

- Config flags (all default OFF at first ship):
  - `mm.as_model.enabled: bool` — master switch
  - `mm.as_model.gamma: float = 1.0`
  - `mm.as_model.horizon_shrink_hours: float = 6.0`
  - `mm.as_model.twin_disagreement_pull_pct: float = 3.0`
  - `mm.as_model.surface_cap_usd: float = 60.0`
- Kill: `mm.as_model.enabled: false` in config, OR global `KILL` file (already
  respected by `run_pair_maker.py`). Falls back to the current hand-rules
  quoter without state loss.
- Failure modes:
  - twin not found → quote at wide default half-spread (`(1/κ) + 20 bps of
    face`), do not adjust for σ² or inventory. Log `TWIN_MISSING`.
  - κ fit stale (> 24 h since last update) → refuse to quote; the fit is our
    only calibrated input.
  - Surface cap reached → cancel outstanding quotes on that surface, do not
    re-post. Same behaviour as current `positions.reconcile`.

## 7. What I did NOT invent — cited pieces vs ours

| piece | source |
|---|---|
| reservation price shape r = s − q·γ·σ²(T−t) | Avellaneda-Stoikov 2008 |
| optimal half-spread δ* = 1/κ + γσ²(T−t)/2 | A-S 2008, Cartea-Jaimungal-Penalva 2015 Ch. 10 |
| bounded-inventory skew ξ(q/q_max) shape | GLFT 2013 Cor. 4 — tanh form is mine as placeholder |
| κ estimated log-linearly from own fills | Cartea et al. Ch. 10.4 |
| queue/tick discretisation, per-side min size | Hummingbot pure_market_making |
| p(1−p) as terminal variance for binary payoff | standard binomial variance; **use in place of σ² is mine** |
| liquid-twin fair-value substitution | **mine** — no citation. This is the biggest new claim. |
| forced-exit at T−6h vs settle cost decision | **mine**, informed by MEASURED.md fee table |
| tanh ξ (as opposed to GLFT's ODE solution) | **mine** — a shortcut, marked to switch to the ODE form if calibration says it matters |
| all target thresholds in §5 | **mine** |

## 8. What it costs to try

Two new files: `src/mm_model.py` (state-machine, ~250 LOC) and
`scripts/mm_shadow.py` (dry-run wrapper reading `book_snapshots` and
`journal.jsonl`, ~120 LOC). Config extended by six flags. Nothing in `src/`
touched; the shadow harness runs alongside `run_pair_maker.py` and only reads
state.

Two calibration runs needed before shadow: (a) a κ fit on the existing
journal (n=17 own fills — probably too few; may need to widen to matched
public-tape fills, i.e. borrow the peer-cluster tape), and (b) a twin-pair
detection sweep on the current 201-market census. Each is a ~1 h script.

## Verdict

**UNPROVEN. Ship as a shadow model; do not touch the live quoter.** The
literature is solid; the adaptation is honest about which pieces are ours
(sizing, twin fair value, terminal binomial variance, T-6h decision, target
thresholds); the falsification bar is defined. Expected value at our measured
inputs is +3.8 to +7.7 bps of face per round-trip — same order of magnitude
as the hand-rules bot's best case, so if the model **only matches** the hand
rules we still ship it because it is more principled and calibratable, but we
should be honest that this is not a discovered edge. If shadow beats the hand
rules by > 2 bps of face over ≥ 200 round-trips, promote to a $25/leg live
run. If it does not, kill it — do not spend more research budget on this
surface — and redirect to crypto barriers (question 2), which are structurally
higher-flow.

## Next actions

1. Fix branch state so future cron runs see MEASURED.md / QUESTIONS.md
   (blocker for the next quant-researcher run).
2. Write `src/mm_model.py` and `scripts/mm_shadow.py` per §2-§4.
3. Fit κ and A once from the merged journal + peer-cluster tape.
4. Shadow for 72 h against live twin pairs; report against §5's table.

---

## Deltas for MEASURED.md and QUESTIONS.md

Live on `feat/inplay-guard-pair-maker` / stash@{0}, not this branch. Recorded
here for the operator to graft in.

### Append to MEASURED.md under a new "Market-making model" section:

```markdown
### A-S / GLFT-based MM model — SPECED, UNPROVEN (2026-09-25)
Spec at `research/mm-model-spec-2026-09-25.md`. Uses Avellaneda-Stoikov's
inventory-skewed quoting shape with Guéant-Lehalle-Fernandez-Tapia's bounded-
inventory correction, Cartea-Jaimungal-Penalva's κ-from-own-fills estimator,
and Hummingbot's tick-discretisation. **Ours, marked in the doc:** liquid-twin
fair-value substitution (biggest new claim), p(1−p) binomial variance in
place of σ² for the terminal-payoff term, and the T−6h settle-vs-cross
decision. Expected +3.8..+7.7 bps of face per round-trip at our measured
markout — same order as the hand-rules bot's best case, so this is not a
discovered edge; it is a principled quoter with a defined falsification bar
(≥ 200 shadow round-trips, ≥ 5 surfaces, net > +3.8 bps or kill).
```

### Move QUESTIONS.md Q0a (real MM model) to ANSWERED:

```markdown
- **A real MM model from credible open work** — SPECED 2026-09-25.
  Avellaneda-Stoikov + GLFT bounded-inventory + Cartea-Jaimungal-Penalva
  κ-from-fills + Hummingbot tick discretisation; liquid-twin fair value,
  p(1−p) terminal variance and T−6h decision are ours. Shadow-first; kill if
  net < +3.8 bps of face after 200 round-trips.
  `research/mm-model-spec-2026-09-25.md`.
```
