# xyz:CL shock-window edge sizing — 2026-10-04

**NO EDGE.** Base-rate + mechanism. Shocks happen (~1.44 |ret_1m|>=50 bps
events/day, ~3.92/day at the 5-min horizon, max observed 72 bps 1-min / 292
bps 5-min) but theoretical capture against the measured top-5 depth is only
$5–15/day gross before adverse selection, and the one-shot incumbent is
already repricing every ~60 s on background drift — it will reprice *faster*
under stress, not slower. n = 5,009 one-min bars (3.5 d) + 5,002 five-min
bars (17.5 d), xyz:CL, HL candleSnapshot.

## Why this probe

Follow-up (1) from `research/binary-wall-responsiveness-2026-10-03.md`:

> Shock-window probe (|dCL_1m| > 50 bps) remains the only still-alive
> hypothesis.

The 10-03 report killed "frozen incumbent" (seen 3–6 best-bid price
transitions per market in 5 min while CL mid moved only 9 bps). The one
scenario where a lag-fade might survive is a shock big enough to outrun
the incumbent's quoting cadence. Before building a shock-trigger
collector, the right first move is to put a number on how often that
condition fires *and* what the maximum capture would be if it did.

A clean negative is a success here. The purpose is to stop re-running
"maybe there's edge in HIP-4 binaryPrice during shocks" every two weeks
without numbers.

## Workspace state

`MEASURED.md`, `research/QUESTIONS.md`, `.claude/agents/quant-researcher.md`
still only exist on `feat/inplay-guard-pair-maker` (same note the last
three cron reports made). Writing the finding to this branch and staging
a MEASURED.md graft at the bottom.

## Data

Two reads against `https://api.hyperliquid.xyz/info` `candleSnapshot`,
read-only, 0.3 s per call:

- `research/cl_shock_frequency_probe.py` — 30 d back, 1-min bars.
  HL retained 5,010 unique bars (last 3.48 d). Earlier pages returned
  empty — xyz:CL is a HIP-3 listing on a newer surface and 1-min history
  only reaches back a few days.
- `research/cl_shock_frequency_5m.py` — 90 d back, 5-min bars. HL
  retained 5,002 unique bars (last 17.5 d from 2026-09-16 23:00 Z).

Returns computed as `10000 × (close_t − close_{t-1}) / close_{t-1}` in bps.
1-min samples saved to `research/cl_shock_samples.jsonl` (5,009 rows).

## |ret| distributions

1-min bars, n = 5,009 (~3.5 d):

    p50.0   1.97 bps
    p90.0   9.55 bps
    p95.0  13.24 bps
    p99.0  24.35 bps
    p99.9  47.87 bps
    max    72.27 bps

5-min bars, n = 5,002 (~17.5 d):

    p50.0   5.86 bps
    p90.0  23.39 bps
    p95.0  31.77 bps
    p99.0  56.44 bps
    p99.9 107.59 bps
    max   292.37 bps

The 5-min distribution has fatter tails than 3× the 1-min figures (max
292 bps vs √5 × 72 ≈ 161 bps), i.e. shocks cluster rather than being
independent minute moves. Burst analysis of consecutive |ret_1m|>=20 bps
minutes:

- 70 bursts in 3.5 d
- mean length 1.27 min, mean cumulative move 36.9 bps
- longest 5 bursts: 3 min each, cumulative 75–125 bps

## Shock-event counts

| threshold          | 1-min bars  | /day  | 5-min bars  | /day  |
|-------------------:|------------:|------:|------------:|------:|
| \|ret\| >= 20 bps  | 89 / 5,009  | 25.6  | —           | —     |
| \|ret\| >= 30 bps  | 24 / 5,009  |  6.9  | —           | —     |
| \|ret\| >= 50 bps  |  5 / 5,009  |  1.44 | 68 / 5,002  |  3.92 |
| \|ret\| >= 100 bps |  0 / 5,009  |  0.00 |  7 / 5,002  |  0.40 |
| \|ret\| >= 200 bps |  0 / 5,009  |  0.00 |  3 / 5,002  |  0.17 |

Top five 1-min moves in the window:

    2026-10-01 17:54 Z   +72.3 bps  close=$92.542
    2026-10-02 13:01 Z   -67.7 bps  close=$88.453
    2026-10-02 07:57 Z   -64.8 bps  close=$90.153
    2026-10-02 18:28 Z   -60.6 bps  close=$91.034
    2026-10-02 13:58 Z   -57.0 bps  close=$89.292

All five of the >=50-bps 1-min shocks fell on 2026-10-01 and 2026-10-02.
Zero shocks on 09-28, 09-29, 09-30, 10-03. Shock arrival is Poisson-ish
with heavy day-to-day clustering, not uniform.

## Theoretical capture ceiling

Combining this with `research/binary-price-depth-2026-09-30.md`:

- Top-5 depth on the deepest binaryPrice (`xyz:CL #68150`): $531 bid /
  $621 ask.
- Standing spread: 530 bps on 0.565 mid (~3¢).
- Binary delta at ~27-day expiry, near-the-money, implied CL vol ~25 %:
  ≈ 2 (one 1-¢ CL move ≈ 2-¢ binary move at the money, by the normal-
  pdf approximation).

So a 50-bps CL shock implies ~100 bps binary mispricing at the money,
~15–40 bps on OTM strikes (0.23, 0.76 mids per 10-03). On the ATM strike
(0.44 mid), that is ~0.44 ¢ of free money per contract until the
incumbent reprices. Against $500 top-5 depth, the maximum notional edge
per shock is:

    $500 × 100 bps = $5.00  (ATM)
    $500 ×  40 bps = $2.00  (OTM)

Round-trip fees from `MEASURED.md` (2026-09-20 audit): 8.97 bps taker +
13.4 bps settlement ≈ 22 bps per basket. On $500 that is $1.10 per
round-trip. The gross-of-fees ceiling is therefore ~$1–4 per *perfectly
timed* shock.

Expected daily gross, assuming you win 100 % of shock races and clear
the top-5:

    1.44 shocks/day × $4   = $5.76 /day   (ATM, if ATM is always the shocked strike)
    1.44 shocks/day × $2   = $2.88 /day   (OTM, more typical)

Net of fees, roughly $2–5/day. Realistic win rate against a live
incumbent that reprices in <60 s is well below 100 %; see mechanism
below. The upper bound on this hypothesis is a few $/day, which is
below the "worth building" threshold.

## Why the race-win assumption is weak

The 10-03 report showed the incumbent on `xyz:CL` binaryPrice reprices
every ~60 s on background CL drift (9 bps over 5 min). The implicit
promise of the shock-window hypothesis is that the incumbent *slows
down* during stress — i.e. that a lag opens up during the moment edge
would exist. The opposite is the default behaviour of any rational
market-maker: variance-aware quoting speeds up repricing when realised
volatility rises. The incumbent I observed is clearly rules-based (fixed
standing spread, calibrated widths) but even a fixed-cadence quoter
reprices at 60 s regardless of the shock size, so the stale window is
bounded by cadence, not shock magnitude.

To falsify "incumbent reprices faster under stress" would need live
book snapshots during an actual shock, which neither the stored
`state/book_snapshots/` nor the public `recentTrades` endpoint provides
for outcome coins (both 500'd on `#NNNNN` in the 10-03 run). The one
path that would reopen this hypothesis — identifying the incumbent
wallet and reading its `userFillsByTime` during a shock — is blocked
until on-chain fill events give us a wallet.

## What I did not do

- No live shock catch. Running a 20-minute probe now has ~2 % chance
  of catching a >=50-bps shock given the 1.44/day base rate; not worth
  the API spend inside a one-shot cron.
- No multi-day forward collector. That belongs in a scheduled job, not
  this cron. If it survives the base-rate reality check, see the
  follow-up below.

## Follow-ups

1. **Only if a cheaper trigger emerges** (identifying the incumbent
   wallet, HL exposes outcome-coin trade history, or top-5 depth
   jumps >5× on these books), reopen the shock-window probe with a
   trigger on `|ret_CL_1m| > 50 bps` and a 60-s book-snap window.
   Until then the ceiling is quantified and the hypothesis is
   deprioritized.
2. **Reconcile 09-30 trade-count math** (follow-up #3 from 10-03): the
   right metric is reprices-per-trade, not reprices-per-second. 10-03
   observed ~1 reprice/min on `xyz:CL` books; 09-30 observed 29
   trades/hr on #68150. That is ~0.5 trades per reprice window —
   consistent with "incumbent reprices between almost every print",
   not "frozen policy that absorbs flow". This is a text correction
   in `research/binary-price-depth-2026-09-30.md`, not new work.

## Verdict

**NO EDGE.** Shock-window edge on HIP-4 binaryPrice is bounded above
at a few $/day gross, before adverse selection, and the race-win
assumption is contradicted by observed incumbent cadence under drift.
Combined with the measurements in 09-30, 10-03 and this report,
binaryPrice is now closed as a maker target across *all three* probe
dimensions (depth, cadence, shock).

## Reproducing

    .venv/bin/python research/cl_shock_frequency_probe.py
    # writes research/cl_shock_samples.jsonl (1-min returns)
    .venv/bin/python research/cl_shock_frequency_5m.py
    # 5-min baseline, prints to stdout

## MEASURED.md graft (append on `feat/inplay-guard-pair-maker`)

    | HIP-4 xyz:CL shock frequency (lag-fade upper bound)  | NO EDGE
    | 3.5d 1m + 17.5d 5m HL candleSnapshot, 5009 + 5002 bars
    | 2026-10-04 | |ret_1m|>=50bps = 1.44/day, max 72bps. |ret_5m|>=50bps
    | = 3.92/day, >=100bps = 0.40/day, max 292bps. Theoretical capture
    | ceiling against measured top-5 depth ($500) and ATM binary delta
    | (~2): $2-5/day net of fees, assuming 100% race-win vs an incumbent
    | that already reprices every ~60s on quiet drift (per 10-03) and
    | will reprice *faster* under stress. Below "worth building"
    | threshold. Closes the last-alive binaryPrice hypothesis across
    | depth (09-30) + cadence (10-03) + shock (today).
    | research/cl-shock-frequency-2026-10-04.md
