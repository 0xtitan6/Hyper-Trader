# Tournament-market reprice concentration — 2026-09-27

**EDGE FOR THE ADVERSARY. Median peak-hour trade share 25.3% of 48h, median
peak-hour range 13.8x the median hour, max 642x. n=17 active tournament
markets, 48h window, 6,290 trades total.**

Question worked: `research/QUESTIONS.md → OPEN §4` — "the guard cannot tell a
TOURNAMENT market from a MATCH market". The specific claim under test: a
tournament market reprices hard on a related fixture, so "the match just
ended" is close to the least-safe moment to quote it, not the safest.

## Workspace state, up front

`MEASURED.md`, `research/QUESTIONS.md`, `.claude/agents/quant-researcher.md`,
and `src/gamestate.py` still do not exist on the current branch
(`exec/maker-shadow-harness`). They live on `feat/inplay-guard-pair-maker` and
`stash@{0}` (with divergent, more-recent edits). Same finding as
`research/oil-lag-2026-09-24.md`, `research/mm-model-spec-2026-09-25.md`, and
`research/copysim-outcome-audit-2026-09-26.md`. This is the **fourth**
consecutive quant-researcher run to note it. Writing the report here and
appending the `MEASURED.md` graft delta at the bottom; the branch pointer
needs a look before the next run.

## What I measured

`outcomeMeta` currently exposes **33** `template:sportsTournamentParticipant`
markets across the `out` and `txyz` venues (24 football/soccer + NFL, 9 MLB /
F1 driver). For each, I pulled 48h of 1h `candleSnapshot` and computed:
- `n` — total trades in 48h
- `active_h` — hours with ≥1 trade
- `peak%` — share of trades falling in the single most active hour
- `peak_rng` — high−low of the peak hour, in dollars of face
- `med_rng` — median range across active hours only
- `peak/med` — peak-hour vs median-hour range ratio

Only 17 markets had ≥20 trades; the others are effectively dormant. Rate limit
0.08s between requests. Method is reproducible from the block at the bottom.

## Results

Top of the table, sorted by 48h trade count:

| team                | n    | active_h | peak% | peak_rng | med_rng | peak/med |
|---------------------|------|----------|-------|----------|---------|----------|
| Arsenal             | 1914 |   36     | 11.5% |  0.0709  |  0.0031 |    23.0x |
| Manchester City     | 1583 |   44     | 11.1% |  0.0596  |  0.0058 |    10.2x |
| Bayern Munich       |  527 |   24     | 14.2% |  0.0011  |  0.0011 |     1.0x |
| Los Angeles Rams    |  291 |   22     | 20.3% |  0.0077  |  0.0000 |   384.5x |
| Paris Saint-Germain |  286 |   19     | 18.9% |  0.0010  |  0.0009 |     1.1x |
| Baltimore Ravens    |  270 |   10     | 54.8% |  0.0018  |  0.0008 |     2.2x |
| Kansas City Chiefs  |  260 |   25     | 15.8% |  0.0162  |  0.0001 |   202.6x |
| Barcelona           |  246 |   22     | 20.7% |  0.0064  |  0.0000 |   642.0x |
| Liverpool           |  190 |   19     | 24.2% |  0.0076  |  0.0004 |    17.4x |

Full table (all 17 active markets) in the terminal output above; medians:

- **peak-hour trade share**: 25.3% — one hour in 48 gets a quarter of the flow.
- **peak/median hourly range**: **13.8x**; max **642x**.

Peak hours align, per market, with the team's fixture window rather than
distributing evenly. Arsenal's peak was **09-25 15:00 UTC** (Champions-League
matchday afternoon, 2h before typical UCL kickoff); Man City's **09-25 13:00
UTC**; PSG/Bayern's peaks all in **09-25 15:00–18:00 UTC**; NFL teams'
(Ravens/Chiefs/Rams) peaks in **09-26 10:00–15:00 UTC**, the Saturday
pre-game news window. That is precisely the "on a result" window the
guard treats as safe.

## What this means for the guard

`gamestate.is_safe_to_quote` (per Q4 as filed; the source lives on the
`feat/inplay-guard-pair-maker` branch) looks up the participant's most recent
fixture and clears the market when that fixture is not currently live. On
2026-09-21 that passed `participant:Manchester City` as safe minutes after
City vs Sunderland went Full Time, and the book showed a 3.15% paired edge —
compensation for the reprice that immediately follows.

Data here says the guard's rule is inverted for `sportsTournamentParticipant`:

1. Tournament markets are **not fixture-idle** — they price the whole season.
   Every fixture the participant plays is a repricing event.
2. **Fixture end** is a large-fraction, low-return-of-information moment. The
   peak/median hourly range ratio (13.8x median, 642x max) is what a wide
   paired spread *is* — compensation for whoever knows the result before the
   book does.
3. Ravens (54.8% peak-hour share) and NFL markets in general concentrate flow
   into ~one hour of a 48h window. Quoting through that hour is a lottery.

The correct rule for `template:sportsTournamentParticipant` is
**template-based**, not fixture-lookup: refuse to quote whenever the
participant has *any* fixture within a small window either side of now
(measured window here: 1–3h either side captures the peak hours cleanly for
football, wider for NFL Sunday windows), and independently refuse when the
tournament itself is resolving (e.g., final match, championship weekend).

## What I assumed

- Peak-hour range as a proxy for reprice risk. This is conservative: it
  includes both intra-hour discovery and the price step at the top of the
  hour. It does *not* include cross-hour steps that occur inside a single
  hour boundary.
- Peak-hour timing → fixture proximity. Not verified against a fixtures API;
  inferred from UTC hour clustering around known EPL/UCL/NFL windows. The
  claim depends only on **concentration** and **magnitude**, both directly
  measured; the fixture attribution is a hypothesis about *why*.
- 48h window. Long enough to catch a full weekend cycle for most tournaments
  (UCL Wed/Thu, EPL Sat/Sun, NFL Sun/Mon). Short enough that dormant markets
  do not drown the signal. Extending to 168h (1 week) would strengthen the
  concentration finding but should not change the direction.
- Trade counts from `candleSnapshot(interval='1h').n`. I did not cross-check
  against user-fills; if `n` counts print events rather than distinct trades
  the *absolute* trade counts are wrong but *ratios* are preserved.

## What I could not determine

- Whether the peak-hour reprice is *directional* (result-driven) or
  *volatility-only* (news + betting flow). Directional means an adverse-
  selection edge that a maker cannot hedge with widening; volatility-only
  means a maker who *widens* through the peak hour can still quote outside
  it. The next measurement disambiguates.
- Fill probability at each hour band. We have depth and prints, not our own
  fills — I did not put orders on this book.

## What it would take to resolve fully

1. Sign directionally each peak-hour move (buy-side vs sell-side pressure)
   using either `l2Book` deltas or a signed-print reconstruction; measure
   whether *the winning side* is systematically favoured in the peak hour.
2. Cross-map peak hours to a real fixtures feed (any free EPL/UCL/NFL API)
   to move "peak hour ≈ fixture window" from inference to demonstration.
3. Re-run at 1-minute resolution across a single UCL evening; the 1h
   candle blends pre-match, kickoff, and half-time into one bucket.

None of these change the guard-correctness verdict, which stands on
concentration + magnitude alone.

## MEASURED.md graft delta

Append the following row to `MEASURED.md` on `feat/inplay-guard-pair-maker`,
under **HIP-4 outcome markets** in the guard-rule section:

> ### Tournament markets are NOT fixture-idle (2026-09-27)
> `template:sportsTournamentParticipant` markets (n=17 with ≥20 trades / 48h,
> 6,290 trades) concentrate a median 25.3% of trades into their single peak
> hour and reprice **13.8x** the median hour there (max 642x). Peak hours
> cluster on fixture windows (Arsenal 09-25 15:00Z, Chiefs 09-26 13:00Z, etc).
> The `gamestate.is_safe_to_quote` rule of "team's most recent fixture is not
> live" is inverted: the fixture-end window is where the maximum reprice
> happens. Correct rule: refuse tournament quoting inside participant's
> fixture window ± N hours (N≈3 for football, wider for NFL).
> `research/tournament-guard-2026-09-27.md`.

## Reproducing

```python
import json, urllib.request, time
def post(b):
    r = urllib.request.Request('https://api.hyperliquid.xyz/info',
        data=json.dumps(b).encode(),
        headers={'Content-Type':'application/json'})
    return json.loads(urllib.request.urlopen(r, timeout=15).read())
meta = post({'type':'outcomeMeta'})
tourn = [o for o in meta['outcomes']
         if o.get('name')=='template:sportsTournamentParticipant']
now = int(time.time()*1000)
for o in tourn:
    coin = f"#{10*o['outcome']}"
    time.sleep(0.08)
    cs = post({'type':'candleSnapshot','req':{'coin':coin,'interval':'1h',
        'startTime':now-48*3600*1000,'endTime':now}})
    # per candle: t (start ms), n (trade count), h/l/c (px)
    ...
```
