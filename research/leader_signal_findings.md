# Leader-Signal Probe — Findings (2026-07-06)

**Question:** do June-19 leader features predict June19→now (~16d) forward realized PnL, out-of-sample? If yes → an ML leader-selection model is worth building.

**Data:** 94 of 97 leaders returned forward data (3 fetch-failed). Caveat: **22 leaders hit the 2000-fill/pull cap** → their forward PnL is under-counted (biases the tails). Outcome (HIP-4) leaders; single ~16d window; forward PnL is the *leader's own* PnL (not copy-adjusted for our slippage/caps).

## Sobering base rate
- Forward PnL: **median $0**, mean **−$2,988**, range −$176k … +$115k.
- **Only 35/94 (37%) of these top-ranked leaders were profitable forward.**
- i.e. past top-leaderboard status did NOT translate to forward profit for most.

## Predictability = weak-to-none
Spearman rank-corr (June-19 feature vs forward PnL):
| feature | rho |
|---|---|
| median_holding_h | **+0.126** (best, still weak) |
| overall_pnl_30d | +0.071 |
| fills_per_day | +0.033 |
| max_single_loss | +0.011 |
| win_rate | +0.009 |
| **quality_score (the bot's own)** | **−0.122** (weakly NEGATIVE / anti-predictive!) |

All |rho| < 0.13 = essentially noise.

## Quartile tests
- **quality_score:** bottom-quartile forward mean −$9,646 vs top −$3,071 (both negative; median $0 both). Barely separates, and top still loses on average.
- **prior-30d-PnL (persistence):** bottom-quartile forward mean −$276 vs **top +$3,755**. The one glimmer — but driven by a few big winners (outliers), not a robust rank relationship (rho only +0.071).

## Verdict
1. **Do NOT build an ML leader-forward-PnL model on this** — there's no exploitable signal; a model would fit noise. (No Cerebrium needed — good we probed cheaply first.)
2. **Actionable finding:** the bot's current `quality_score` is **non-predictive (rho −0.12)** — it isn't earning its keep and may be slightly anti-selecting. The only faint signals are raw prior-PnL persistence + longer holding times.
3. **Cheap non-ML experiment worth trying:** replace/augment quality_score with a simpler screen — favor leaders with real prior PnL + longer median holding times, avoid churny high-fills/day ones. Validate across MULTIPLE rolling windows (this was one 16d window — not definitive).

Bottom line: the ML route (predict-the-winning-leader) is a dead end with our data; the real lever is that leader forward-performance is mostly unpredictable, so the current selection heuristic is the thing to question — cheaply, without ML.
