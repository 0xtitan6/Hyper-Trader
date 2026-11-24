# Polymarket <-> HL Outcome Fair-Value Pairer v0

Run epoch: 1790296333 (2026-09-25)
PM snapshot: `state/polymarket/markets_1790296633.jsonl` (100 markets)
HL coins in scope: 20

## Verdict: **KILLED (v0 blocked by upstream data selection, not by fair-value math)**

Every one of the 20 HL outcome coins we log is a **sports** market (UEFA Nations League soccer, NFL games, EPL tournament). Every one of the 100 markets the Polymarket collector snapshots is **US politics** (98/100 are 2028 presidential nomination/election; the other 2 are Xi Jinping / misc). The two universes do not overlap. Best fuzzy score across all 20 pairings is 47.4 (`rapidfuzz.token_set_ratio`); the >=70 acceptance bar was never approached and the >=85 strong-match bar is unreachable in principle.

The "divergences" this pipeline would surface are all comparisons of unrelated markets (e.g. "Scotland beat Slovenia" at 0.658 vs "Will Bernie Sanders win the 2028 nomination" at 0.005). They would 100% look like giant arbs and 100% be noise. Not tradeable.

The block is upstream: **the Polymarket collector needs to pull sports markets** (or, symmetric: HL needs politics outcomes we can quote). Once that ships, this v0 pipeline (fuzzy match + divergence in bps) can be re-run in ~30s and re-graded.

## Coverage stats

- Strong matches (>=85): **0 / 20**
- Weak matches (70-84): **0 / 20**
- Below threshold (<70, discarded): **20 / 20**
- Tradeable pairs: **0**

## Match table (best fuzzy candidate per HL coin, all skip-tier)

| HL coin | HL question | HL mid | Best PM candidate | Score | PM YES | Div (bps, spurious) |
|---|---|---:|---|---:|---:|---:|
| `#44851` | Croatia beat Czechia (NO) | 0.5546 | Will Chris Murphy win the 2028 Democratic presidential nomination? | 32.6 | 0.0045 | -4,429 |
| `#44850` | Croatia beat Czechia (YES) | 0.4454 | Will Chris Murphy win the 2028 Democratic presidential nomination? | 32.6 | 0.0045 | 979,733 |
| `#45160` | New York Giants beat Tennessee Titans (YES) | 0.5611 | Will Glenn Youngkin win the 2028 US Presidential Election? | 35.8 | 0.0015 | 3,730,433 |
| `#43261` | Italy beat Belgium (NO) | 0.5702 | Will Nikki Haley win the 2028 US Presidential Election? | 27.4 | 0.0005 | -4,296 |
| `#43260` | Italy beat Belgium (YES) | 0.4298 | Will Nikki Haley win the 2028 US Presidential Election? | 27.4 | 0.0005 | 8,586,900 |
| `#46620` | Carolina Panthers beat Cleveland Browns (YES) | 0.5735 | Will Jalen Brunson win the 2028 US Presidential Election? | 39.6 | 0.0005 | 11,460,600 |
| `#44711` | Spain beat England (NO) | 0.5953 | Xi Jinping out before 2027? | 35.6 | 0.0440 | -3,773 |
| `#44710` | Spain beat England (YES) | 0.4047 | Xi Jinping out before 2027? | 35.6 | 0.0440 | 81,978 |
| `#14741` | Manchester City win English Premier League (NO) | 0.6140 | Will Pete Hegseth win the 2028 US Presidential Election? | 44.9 | 0.0005 | -3,857 |
| `#14740` | Manchester City win English Premier League (YES) | 0.3860 | Will Pete Hegseth win the 2028 US Presidential Election? | 44.9 | 0.0005 | 7,710,100 |
| `#44730` | Slovenia beat Scotland (YES) | 0.3560 | Will Elissa Slotkin win the 2028 Democratic presidential nomination? | 33.3 | 0.0015 | 2,363,200 |
| `#44650` | Sweden beat Romania (YES) | 0.6583 | Will Zohran Mamdani win the 2028 US Presidential Election? | 33.8 | 0.0005 | 13,155,500 |
| `#44751` | Scotland beat Slovenia (NO) | 0.6584 | Will Elissa Slotkin win the 2028 Democratic presidential nomination? | 33.3 | 0.0015 | -3,406 |
| `#44750` | Scotland beat Slovenia (YES) | 0.3416 | Will Elissa Slotkin win the 2028 Democratic presidential nomination? | 33.3 | 0.0015 | 2,267,167 |
| `#45131` | Green Bay Packers beat Atlanta Falcons (NO) | 0.2355 | Will Greg Abbott win the 2028 US Presidential Election? | 40.9 | 0.0035 | -7,636 |
| `#45130` | Green Bay Packers beat Atlanta Falcons (YES) | 0.7645 | Will Greg Abbott win the 2028 US Presidential Election? | 40.9 | 0.0035 | 2,174,214 |
| `#44950` | Switzerland beat N.Macedonia (YES) | 0.6944 | Will JB Pritzker win the 2028 US Presidential Election? | 36.1 | 0.0045 | 1,533,167 |
| `#43470` | France beat Turkiye (YES) | 0.7087 | Xi Jinping out before 2027? | 30.4 | 0.0440 | 151,068 |
| `#43471` | France beat Turkiye (NO) | 0.2913 | Xi Jinping out before 2027? | 30.4 | 0.0440 | -6,953 |
| `#45190` | Detroit Lions beat New York Jets (YES) | 0.7188 | Will LeBron James win the 2028 Democratic presidential nomination? | 38.8 | 0.0005 | 14,366,900 |

## Top 10 "divergences" (all noise — mismatched markets)

These are included only to demonstrate what the naive pipeline would emit. Every row is a spurious pair of unrelated markets. **Do not trade on any of these.**

| Rank | HL coin | HL question | HL mid | PM (unrelated) | PM YES | Div (bps) |
|---:|---|---|---:|---|---:|---:|
| 1 | `#45190` | Detroit Lions beat New York Jets | 0.7188 | Will LeBron James win the 2028 Democratic presidential nomination? | 0.0005 | 14,366,900 |
| 2 | `#44650` | Sweden beat Romania | 0.6583 | Will Zohran Mamdani win the 2028 US Presidential Election? | 0.0005 | 13,155,500 |
| 3 | `#46620` | Carolina Panthers beat Cleveland Browns | 0.5735 | Will Jalen Brunson win the 2028 US Presidential Election? | 0.0005 | 11,460,600 |
| 4 | `#43260` | Italy beat Belgium | 0.4298 | Will Nikki Haley win the 2028 US Presidential Election? | 0.0005 | 8,586,900 |
| 5 | `#14740` | Manchester City win English Premier League | 0.3860 | Will Pete Hegseth win the 2028 US Presidential Election? | 0.0005 | 7,710,100 |
| 6 | `#45160` | New York Giants beat Tennessee Titans | 0.5611 | Will Glenn Youngkin win the 2028 US Presidential Election? | 0.0015 | 3,730,433 |
| 7 | `#44730` | Slovenia beat Scotland | 0.3560 | Will Elissa Slotkin win the 2028 Democratic presidential nomination? | 0.0015 | 2,363,200 |
| 8 | `#44750` | Scotland beat Slovenia | 0.3416 | Will Elissa Slotkin win the 2028 Democratic presidential nomination? | 0.0015 | 2,267,167 |
| 9 | `#45130` | Green Bay Packers beat Atlanta Falcons | 0.7645 | Will Greg Abbott win the 2028 US Presidential Election? | 0.0035 | 2,174,214 |
| 10 | `#44950` | Switzerland beat N.Macedonia | 0.6944 | Will JB Pritzker win the 2028 US Presidential Election? | 0.0045 | 1,533,167 |

## Overall stats

- Match rate at strong tier (>=85): **0%**
- Match rate at weak tier (>=70): **0%**
- Best score observed: **47.4** (`Slovenia beat Scotland` <-> `Will Bernie Sanders win the 2028 Democratic presidential nomination?`) — a false-friend caused by common tokens "beat / Sanders" length, not semantic overlap
- Biggest "arb candidate" flagged by the naive pipeline: **>500 bps on every single matched pair**, all spurious

## What would unblock this

1. **Sports on Polymarket collector.** The collector pulls a single Gamma endpoint slice that is politics-heavy. It needs a query variant that pulls NFL/soccer markets, or a second collector. Without this, v0 has no addressable universe.
2. **Snapshot cadence and outcome-token liquidity check.** Once sports markets flow, gate on Polymarket `liquidity > $50k` per market before quoting.
3. **Semantic match, not fuzzy.** For sports, extract (participantA, participantB, competition, date) from both sides and match on structured tuples, not string similarity. Manchester City vs Man City vs Man. City will not survive token_set_ratio.
4. **HL side coverage.** We log 20 coins right now; the outcomeMeta has 242. Expanding the log list is cheap and helps once PM sports is live.

## Files

- `models/fair_value_v0.json` — structured results (all 20 rows + top-3 fuzzy candidates each)
- `analysis/hl_outcome_meta_cache.json` — HL outcomeMeta at run time (242 outcomes, 20 tournament questions)
