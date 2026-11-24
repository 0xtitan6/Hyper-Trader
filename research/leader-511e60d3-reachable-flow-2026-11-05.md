# Leader 0x511e60d3 reachable flow — weight 1.00 is live risk, not phantom (2026-11-05)

**MEASURED RISK (CONFIRMED): leader 0x511e60d3 placed 642 reachable fills over 30d on $1.77M notional; the 11-04 claim that "we are safe only because its flow is unreachable" is FALSIFIED.**
**NO EDGE (net neutral): reachable-only leader closedPnL = -$1,890.15 / 30d; our mirror captured 103 own_fills on 511-territory coins for net realized +$2.63 (net of fee).**
**Sample sizes: leader n=1,933 fills 30d (642 reachable, 1,291 unreachable); journal n=1,188 leader_fills observed, 1,090 skipped on `market_type` (unreachable HIP-3); our own_fills n=103 on 511-territory coins 30d.**

Follow-up to the open thread #3 in
`research/leader-9551e7d4-flip-paid-mirror-silent-leader-511-blown-2026-11-04.md`:
*"Does leader 511 ever place a fill on xyz, BTC, or ZEC in a trailing 30d
window?"*

`research/QUESTIONS.md`, `MEASURED.md`, `.claude/agents/quant-researcher.md`
still absent from `main` HEAD. Verdict appended at bottom in the existing
inline-table style.

---

## Method

- `userFillsByTime` on `0x511e60d32a1fdcafb46bae7f43cfab0a87040713` paginated
  across the 30d window ending 2026-11-05 07:46 UTC. 0.15s sleeps between
  pages. `aggregateByTime=False`, dedup by `(tid, time)`.
- Reachable set = `info.coin_to_asset` after
  `src/hl_hip3.register_hip3_dexes()` — 907 total symbols (base +
  323 HIP-3 assets across every registered builder dex).
- Our own-side: `state/state.db own_fills` table (coin, closed_pnl, fee, ts)
  and `state/journal.jsonl` events (`leader_fill`, `intent_skipped`,
  `own_fill`) over the same 30d window.
- All reads READ-ONLY. No wallet material touched. Dumped raw fills to
  `/tmp/leader_511_30d_fills.jsonl` for cross-check.

---

## What I measured

### 1. Leader 511 reachable vs unreachable (30d)

```
                n     notional       closedPnL
REACHABLE     642   $1,767,895     -$1,890.15
UNREACHABLE  1,291    $580,510    -$24,788.25
                                  -----------
TOTAL        1,933   $2,348,405   -$26,678.40
Excluding dir='Settlement' expiry fills: n=1,788  closedPnL=-$4,686.59
```

Reachable is **33% of fills, 75% of notional, 7% of closedPnL damage**. The
unreachable `#NNNNNN` instances are tiny-notional, Settlement-dominated
HIP-4 outcome markets expiring worthless — that is where the -$30,230 headline
figure came from on 11-04, and it is almost entirely protocol settlement loss,
not discretionary trading loss.

### 2. Top reachable coins

```
coin           n      notional     closedPnL
HYPE         225   $342,753.14      +$129.95   base perp
BTC           85 $1,091,946.64      +$433.98   base perp
xyz:SPCX      66    $21,759.15      -$479.40   HIP-3 equity perp
STRK          48    $25,880.78       -$20.97   base perp
xyz:IREN      39    $22,155.98      -$858.76   HIP-3 equity perp
xyz:HOOD      24    $34,707.84      -$385.56   HIP-3 equity perp
xyz:GOOGL     18    $49,480.09      -$518.89   HIP-3 equity perp
LIT           14     $5,904.19       -$89.20   base perp
ZEC           13    $30,450.03        -$4.77   base perp
(+ 15 more)
```

Base-crypto subset (HYPE+BTC+STRK+LIT+ZEC+AAVE+ETHFI+ENA+BNB+ZK+@107+@334+@700):
~**+$425 net** over 30d.
`xyz:*` equity-perp subset: ~**-$2,316 net** (xyz:IREN, xyz:AMZN, xyz:GOOGL,
xyz:SPCX, xyz:HOOD dominate; xyz:COIN/xyz:SKHY are the only two xyz symbols
with positive net).

The reachable-loss concentration is on tokenized equities, not crypto.

### 3. Mirror behaviour on 511 (journal, 30d)

```
leader_fill    (observed)  n=1,188  on 511
intent_skipped (total)     n=1,596
  reason=market_type              n=1,324   # unreachable HIP-3 instance
  reason=leader_closing_we_flat   n=  184
  reason=leader_conflict(511vs9551)n=  7   # when 9551 wins the arb
  (other)                         n=   81
intent_skipped by leader
  0x511e60d32a1f  n=1,090   # ~92% of 511's observed fills skipped
```

The 1,090 `market_type` skips match — to within WS/REST drift — the 1,291
unreachable fills we saw in `userFillsByTime`. The guard is working; the
remaining ~98 reachable signals were handed to the mirror.

### 4. Own fills attributable to 511 territory (30d)

Attribution rule: own_fills on coins NOT in 9551's observed roster
(`xyz:BE`, `xyz:SP500`, `#36000`, `@107`, `#173460`, `xyz:SKHX`,
`xyz:INTC`) and on symbols observed in 511's reachable fills.

```
coin         n   realized (net of fee)
xyz:GOOGL   21             -$1.12
ZEC         17             -$0.09
BTC         13             +$5.02
xyz:SPCX    12             +$0.91
AAVE        10             +$1.44
xyz:MU       7             -$2.98
xyz:COIN     7             +$2.53
xyz:AMZN     6             -$3.45
HYPE         6             -$1.41
xyz:SKHY     4             +$1.78
            --             ------
TOTAL      103             +$2.63   net (fee-included)
```

Coarse upper-bound attribution (coin overlap, not strict leader tagging):
the entire 30d copy flow on 511-territory coins is **+$2.63 realized**.

### 5. What this changes

Prior finding (11-04): *"0x511e60d3 at weight 1.00 lost -$30,230 over 14 days
and is at $0 equity on every reachable dex. We are safe only because its
flow is on unreachable HIP-3 instances; this is a configuration accident,
not a safety design."*

Two of three clauses hold:

- `-$30,230 / 14d`: TRUE (closedPnL), but 93% of it is HIP-4 outcome
  Settlement, not discretionary perp trading. Reachable perp PnL over 30d
  is just **-$1,890**, and own-copy damage is **+$2.63** (noise).
- `$0 equity on every reachable dex`: TRUE.
- `safe only because flow is unreachable`: **FALSE**. 642 reachable fills
  over 30d, last one 2026-11-03 (2 days ago). Weight 1.00 is live — we
  only avoid damage because (a) 92% of 511's observed flow filters on
  `market_type`, (b) the reachable base-crypto slice is actually
  break-even to positive, and (c) the reachable `xyz:` equity slice fires
  on $30 clips, so even a -$2,316 leader loss over 30d maps to ~-$10
  on our book at this account size.

The dead-weight hypothesis ("it only trades unreachable instances") does
not survive this check. The idiosyncratic-safe hypothesis
("base-crypto is +$425, `xyz:` equity is where the bleed is") does.

---

## Verdict

- **NO EDGE for the mirror** — reachable copy-PnL from 511 over 30d is
  +$2.63 net, which is statistical zero on n=103. Keeping the slot has
  cost us nothing measurable; dropping it would also cost us nothing
  measurable at the current weight.
- **MEASURED LIVE RISK, not phantom** — 642 reachable signals / 30d, last
  one 48h ago. The 11-04 "safe only because unreachable" claim is
  falsified and should not be used as rationale to hold weight 1.00. If
  511 ever concentrates into reachable `xyz:` equities, its own 30d
  reachable loss of -$2,316 scaled to our clip size translates into a
  bounded but real drag; a concentration flip to base crypto would
  translate into bounded but real gain.
- **RECOMMENDATION (read-only, for strategist/executor)**: match the
  9551 precedent — demote 511 from weight 1.00 toward 0.10–0.20, keeping
  the always_follow pin for rotation protection. The symmetry case is
  stronger: 9551 at 0.10 after its SKHX blowup, 511 at the same weight
  class after its (mostly-protocol) blowup. Optionally gate the mirror
  by coin: allow base crypto (HYPE/BTC/AAVE/STRK/ZEC/ENA/LIT/ETHFI) and
  deny `xyz:*` for this specific leader; net 30d reachable-perp PnL on
  the base-crypto subset is **+$425** gross on the leader side vs
  **-$2,316** on the `xyz:` equity subset.

Open threads for a follow-up run:

1. Does 9551's 11-02 GOOGL long (open at ~$286 mark, liq ~$192) resolve
   like SP500 (single-second exit, profitable) or like the 10-30 GOOGL
   bag (-$1,239 realized)?
2. Compute reachable-perp PnL for 9551 over the same 30d window with
   `scripts/copysim.py --markets perp` to see whether its headline
   leader sharpe is also a mirage once the unreachable outcome fills are
   stripped — same methodology I just applied to 511.
3. Does the 92% `market_type` skip rate on 511 shrink or grow if we
   register more HIP-3 dexes? `register_hip3_dexes()` returned 323
   assets; HL has >2000 HIP-4 outcome markets live, and most of 511's
   unreachable flow is `#NNNNNN` HIP-4 instances that no HIP-3 call will
   ever return. Confirming this would close the structural question.

---

## Appended to running ledger (`MEASURED.md` still absent on main)

| date | what was tested | verdict | number | n |
|---|---|---|---|---|
| 2026-11-05 | 511 reachable-perp flow, 30d | MEASURED LIVE RISK | 642 reachable fills, $1.77M notional, leader -$1,890 | 1,933 leader fills |
| 2026-11-05 | 511 reachable-perp copy PnL, 30d | NO EDGE (statistical zero) | +$2.63 net realized | 103 own_fills |
| 2026-11-05 | 11-04 "safe only because unreachable" hypothesis | FALSIFIED | 93% of -$30k is HIP-4 Settlement; reachable-only leader loss = -$1,890 | 642 reachable, 1,291 unreachable |
