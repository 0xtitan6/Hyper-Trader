# Spec — Jev toxicity gate for the Outcome LP farm

**Status:** spec, not built. Needs `TYPESAFE_API_KEY`.

## The decision we currently make blind

`outcome_farm_daemon.py` allocates capital by arithmetic only: reward share is
`ours / (competing + ours)`, so value-per-dollar ≈ `pool / depth`, and we greedily
buy the cheapest share. That is correct as far as it goes, and it is completely
blind to the thing that actually loses money here.

Quote rewards (40% of each pool) are safe — a resting order that is never filled
carries no risk. The danger is **one-sided fills**: both legs filling is hedged
(YES+NO settles to exactly $1.00), but a single fill on the losing side loses the
stake, and adverse selection means the side that fills is disproportionately the
side about to be wrong. Somebody hits our bid *because* they know something.

Arithmetic cannot see that. `pool / depth` says a thin book is attractive, when
thin-and-suddenly-active is precisely the signature of informed flow. This is the
one judgment in the loop that is genuinely a judgment — fast, repeated, made over
structured state. That is System One shape.

## Why Jev rather than a normal LLM call

We need a number to branch on every cycle across ~36 surfaces, not prose. A text
model would cost tokens, return something to parse, and vary between runs. A Noul
returns `0-1` we can threshold in code, and questions evaluate in parallel against
one state, so adding surfaces barely changes latency.

Per TypeSafe's own guidance, questions must be **atomic**. "Is this market worth
quoting?" is the wrong question — it bundles reward economics (which we already
compute exactly) with flow toxicity (which we cannot). Ask only the part we
cannot compute, and combine with our own arithmetic in code.

## Endpoint

```
POST https://api.typesafe.ai/v1/systemone
Authorization: Bearer $TYPESAFE_API_KEY
```

## Proposed call — one per surface, batched

State is built from data we already fetch each cycle (l2Book both legs, recent
trades, market metadata, time-to-event). No new data source.

```jsonc
{
  "model": "jev-latest",
  "state": "Prediction market: English Premier League Matchday 5, Leeds United v Crystal Palace. Outcome: Draw. Kickoff in 4h12m. YES leg mid 0.246, NO leg mid 0.750 (sum 0.996). Top-of-book depth: YES $1,530 / NO $4,201. Last 30min: 14 trades, 11 of them buying YES, total $2,840 notional; YES mid moved 0.231 -> 0.246. Bid/ask spread 2bp. No team news in state.",
  "questions": {
    "informed_flow": {
      "type": "noul",
      "instructions": "Does recent order flow in this book indicate informed trading — i.e. participants acting on information not yet reflected in the price?",
      "criteria": {
        "true": "One-directional flow, accelerating, price moving with it — consistent with someone knowing something",
        "false": "Two-sided or balanced flow, price stable, consistent with ordinary liquidity taking"
      }
    },
    "imminent_repricing": {
      "type": "noul",
      "instructions": "Is this market likely to reprice sharply within the next hour?",
      "criteria": {
        "true": "Event is imminent or news is likely to land within the hour",
        "false": "Stable period, no scheduled catalyst inside the hour"
      }
    },
    "fill_asymmetry": {
      "type": "score",
      "instructions": "If we rest bids on BOTH legs, how likely is it that only one side fills, leaving us directional rather than hedged?",
      "criteria": ["Both sides likely to fill (stays hedged)",
                   "Mixed",
                   "Only one side likely to fill (ends up directional)"]
    }
  }
}
```

Three atomic questions rather than one compound one, because they weight
differently: `informed_flow` should veto, `imminent_repricing` should widen rather
than veto (repricing is fine if we are hedged), and `fill_asymmetry` should scale
size.

## How the answer is used

Jev never sizes anything. It adjusts a multiplier on our own arithmetic:

```python
alloc_usd = greedy_allocation(pool, depth)          # unchanged, exact

if ans["informed_flow"]["noul"] > 0.70:
    alloc_usd = 0                                    # skip: rewards do not cover informed flow
elif ans["fill_asymmetry"]["score"] > 1.3 and ans["fill_asymmetry"]["confidence"] > 0.6:
    alloc_usd *= 0.5                                 # halve when a one-sided fill is likely
if ans["imminent_repricing"]["noul"] > 0.70:
    quote_offset_ticks += 1                          # step back from mid, do not withdraw
```

Thresholds live in config, not in a prompt — the whole point is that when
priorities change we edit a coefficient, not re-engineer wording.

**Low confidence means quote normally.** The arithmetic is the default and Jev is
an override; an uncertain model should not be able to stop us earning the safe
40% quote reward.

## How we validate it before trusting it

Do NOT wire it into allocation on day one. Run it in **shadow** first:

1. Log `informed_flow`, `imminent_repricing`, `fill_asymmetry` per surface per
   cycle to `state/jev_shadow.jsonl`, changing nothing.
2. Log every fill we get, and whether it ended hedged or one-sided.
3. After ~200 fills, test: **were one-sided losing fills preceded by a high
   `informed_flow`?** Compute the AUC / hit rate against the realised outcome.
4. Only enable the gate if it separates. If `informed_flow` is uncorrelated with
   which fills hurt us, it is a cost with no benefit — say so and delete it.

This is the same bar every other candidate got last night: measured, with a
sample size, or it does not ship. The failure mode to avoid is a plausible-sounding
gate that quietly suppresses profitable quoting.

## Cost

One call per cycle (10 min) batching all surfaces ≈ 144 calls/day. Small state per
surface. Needs pricing confirmation, but at demo rates (~$0.20/hr quoted in Jarrod
Watts' jev-trader for per-block inference) a 10-minute cadence is negligible next
to a farm targeting $40-90/month.

## Open questions

1. **Calibration on this domain.** Jev is a general judgment model; HL prediction-
   market microstructure is not general knowledge. Shadow mode answers this.
2. **Is the state rich enough?** We may need per-trade aggressor side, which means
   subscribing to the trades websocket rather than polling l2Book.
3. Rate limits / pricing not documented publicly — confirm before wiring to a
   10-minute loop.
