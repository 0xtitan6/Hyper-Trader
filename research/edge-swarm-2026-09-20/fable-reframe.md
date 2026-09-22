# Reframe — what is the highest-value use of this person and this infrastructure?

Slug: fable-reframe | 2026-09-20 | Status: COMPLETE

The question I was asked is not "where is the edge" — that has a measured answer
(nowhere accessible) — but "what is the most valuable thing to do now." The method
below is the same one the research used on strategies: price every option in
dollars, compare against the passive benchmark, and let the numbers eliminate.

---

## 1. Price the trading itself, once, finally

The number that should end the edge search is not any single negative result. It is
the **ceiling**: the gap between the best measured strategy and doing nothing
(HLP vault, 3.86% APR), at each capital level.

| Capital | Best measured strategy | Gross/yr | Passive (HLP) | **Alpha over passive** |
|---|---|---|---|---|
| $565 | HYPE carry (capped ~$426 notional) | ~$57 | ~$22 | **~$35/yr** |
| $10,000 | HYPE carry, ~$6.6k notional at 13.63% | ~$910 | ~$386 | **~$524/yr ≈ $44/mo** |

These are the *measured winners*. Everything else measured worse: copy-trading is a
coin flip (t=+0.25, n=964, 95% CI −$278…+$358 over 4.5 months); Outcome LP was
−$47/day realised against $0 rewards attributed; 13 candidates dead in
CONSTRAINTS.md; two full leader sweeps and a 9,474-vault screen exhausted.

So the total accessible trading alpha is **$35/yr today and ~$44/mo at $10k**.
That is the prize. Every future hour spent edge-hunting has its expected value
bounded by those numbers. At any defensible valuation of the operator's time —
even $20/hr — one hour per month of continued strategy work exceeds the entire
annual prize at current size. This is not a judgment call; it is arithmetic.

Corollary: **the $200→$1,000 mission cannot be completed by trading.** +77% on
$565 requires either an edge that two research campaigns proved absent, or
leverage into variance, which is not a strategy. The deadline (2026-08-31) has
also already passed. The mission should be formally closed as UNREACHABLE BY
TRADING, not kept ambient.

### A cost the trading books never showed

The operator cron runs every 15 minutes (~96 LLM invocations/day), the strategist
every 6 hours, plus executor/reviewer cycles. If any of this is metered, the
**infrastructure's running cost plausibly exceeds the trading's gross ceiling**.
Even on a flat plan it is attention budget spent guarding a coin flip. Whatever
else is decided, the cron fleet should shrink to match a $35/yr book.

---

## 2. What the weekend actually produced (the asset inventory)

Three assets exist. None of them is the P&L.

**Asset 1 — the execution stack.** ~12,800 LOC of source, ~11,300 LOC of tests
across 37 test files. Live-tested handling of the parts of Hyperliquid that
actually bite: per-dex HIP-3 collateral isolation, builder-code order flow with
fee=0 semantics, WS health/rebuild, reconcile-vs-kill-switch interaction, cold-boot
position adoption, a kill switch that covers every order path. This is not a bot;
it is a hardened HL integration layer plus an operational runbook (the memory/
INVARIANTS corpus) of failure modes that are documented nowhere public.

**Asset 2 — the negative results.** Methodologically, two of them are better than
almost anything public on the topic:
- *Copy-trading has no edge, measured with real money*: n=964 closes, t=+0.25,
  and the power calculation (60,720 trades to prove the point estimate) — an
  honest statement of how underpowered every "I copy-trade profitably" claim is.
- *The forward base rate of top leaders*: only 35/94 (37%) top-ranked leaders
  profitable forward; every screening feature |rho| < 0.13; the bot's own quality
  score anti-predictive (−0.12). Combined with the structural observation that
  HL's leaderboard excludes accounts under $100k and Reddit's visible surface
  auto-removes honest post-mortems, this is a genuine survivorship-bias study
  design: sampled from activity, scored forward, costs included.

**Asset 3 — the operator.** A person/agent system that demonstrably runs
production financial infrastructure, absorbs negative results without flinching,
and documents honestly. Rarer than either of the above.

---

## 3. Price each redeployment option

### Option A — keep trading the $565 (status quo)
EV ≈ $35/yr over passive, minus run-rate, minus tail risk (one-sided fills,
leader blowups already observed: 0x9636dc55 −$8,592/day). **Net negative.
Distraction.**

### Option B — sell or open-source the bot as a product
Honest answer: **~$0 direct.** GitHub is full of free HL copy-bots; buyers of
trading bots are buying claimed edge, and our own headline result is that the
edge does not exist. Selling it as a "profitable bot" would be the exact
promotional fraud the research spent a weekend documenting. The code's value is
not as a product — see Option D.

### Option C — deposit $10k and run the carry as an appliance
The carry is already demonstrated to the brief's own standard (13.63% APR,
n=13,080 hourly prints, 92.2% positive hours, 18/18 30-day windows clear costs) —
the "edge first, then $10k" gate is arguably satisfied *today*; nothing further
needs proving. But price it honestly: **$910/yr gross, $524/yr over simply
parking the same $10k in HLP.** The infrastructure makes this near-zero marginal
effort (the engine, risk gates, and monitoring already exist — this is the one
job they are genuinely good for), so it is worth doing **if the $10k arrives**.
It is a savings account with a basis-risk term, not a business, and it does not
justify one additional hour of strategy research.

### Option D — publish the negative results, and let them convert Asset 1 and 3 into income
Cost: 2–4 days of writing. Direct revenue: $0 — blog posts don't pay.
What it actually is: **the marketing instrument for the only economically
significant asset here — demonstrated HL operational expertise.** Crypto-infra
contract work clears $75–150/hr; HIP-3 builder-dex operators, vault managers, and
teams integrating HL all need exactly the integration knowledge in Asset 1. One
20 hr/month engagement is **$1,500–3,000/mo — roughly 40–70× the trading alpha
at $10k, and ~1,000× at $565.** A rigorous public negative result ("we measured
copy-trading with real money; here is the tape, here is the power analysis") is
the one credential that separates its author from every bot-seller on X, because
it is the credential a bot-seller cannot afford to publish. Concretely:
1. A writeup: *"964 real-money trades: copy-trading Hyperliquid leaders is a
   coin flip"* — the t-stat, the power calc, the 37% forward base rate, the
   leaderboard's $100k survivorship cutoff.
2. An open-source **leader/vault auditor**: wallet in → survivorship-corrected
   forward performance, fill-granularity/oversize screen, bag-holder detection
   (all code already written in `research/`). Useful to every prospective
   copy-trader; a standing demonstration of competence.
3. (Speculative, UNVERIFIED sizing) Hyper Foundation / ecosystem grants fund
   open-source HL tooling; a tested integration layer plus published research is
   a credible application. Price at $0 until a programme is confirmed, but the
   option is free once 1–2 exist.

### Option E — stop entirely, earn elsewhere, return at $10k
Correct about stopping the *search*; incomplete about the return. Come back to
*what*? $524/yr over passive. The deposit is worth making only because the
appliance already exists (Option C) — it would never justify building one.

---

## 4. The recommendation

**The asset is not the account and was never going to be. It is the demonstrated,
documented competence — and the highest-value move is to make it public.**

Do, in order:
1. **This week:** write the copy-trading negative-result piece and extract the
   leader-auditor into a standalone open-source tool. 2–4 days. This is the only
   item on any list whose upside is measured in thousands per month rather than
   tens per year.
2. **Simultaneously:** park the $565 in HLP (~$22/yr, beats the bot's measured
   expectation), set the mirror to reduce-only wind-down, and cut the operator
   cron to a daily health check. The book being guarded is worth $35/yr; the
   guard should cost less than that.
3. **If/when $10k arrives:** deploy the carry appliance. ~$76/mo gross, ~$44/mo
   over passive, near-zero marginal effort. Accept it for what it is.
4. **Never again:** fund edge research on this venue at this size. The ceiling
   is measured. Any new proposal must beat $524/yr at $10k *after* its own
   research cost, which no candidate in two campaigns has come within an order
   of magnitude of.

Everything else — another leader sweep, another incentive programme, another
venue scan — is a distraction with a measured price tag on it.
