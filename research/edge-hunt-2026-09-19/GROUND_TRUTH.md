# Ground truth for the 2026-09-19 edge hunt

Account: 0xE503186067b1B0Fb973c063054B14c4625434A1a — total value ~$641.
Venv: /home/ec2-user/.openclaw/workspace/hyper-trader/.venv/bin/python (hyperliquid SDK installed).

## Why we are doing this
Copy-trading has produced, over 964 bot-only closing trades in 4.5 months:
  mean +$0.0416/trade, sd $5.23, t = +0.25, 95% CI on total -$278..+$358.
Statistically indistinguishable from zero. Proving it would take 60,720 trades (~23.6 years).
We need a DIFFERENT edge, not more capital behind this one.

## Hard constraints any proposed edge MUST clear
1. FEES: we pay 0.045% taker / 0.015% maker. HL fee tiers are 14-day VOLUME based, not
   equity — a bigger account does NOT get us a better tier. Any edge whose profit is
   smaller than round-trip fees (~0.09% taker) is dead on arrival.
2. NO MAKER-REBATE DEPENDENCE. Every profitable HL account we have examined wins on
   maker rebates we cannot access. If the edge requires being a rebate-tier maker, it is
   not available to us. Say so and stop.
3. SIZE: must work at $640 AND at $10,000. HL minimum order value is $10. Thin HIP-3
   (xyz:/para:/io:) books slip badly above a few hundred dollars — measure, do not assume.
4. MEASURED, NOT ASSERTED. Every claim needs a number computed from real API data, with
   the sample size stated. "Should work in theory" is worthless here.
5. Report NEGATIVE results plainly. A well-measured "no edge here, here is the number"
   is a genuinely valuable output and the expected outcome for most hypotheses.

## API notes (learned the hard way)
- Vault list: https://stats-data.hyperliquid.xyz/Mainnet/vaults  ({"type":"vaultSummaries"} returns EMPTY)
- userFills caps at 2000/page — paginate with userFillsByTime + startTime, or you silently lose data.
- Base-dex clearinghouseState on a HIP-3 trader returns $0 equity. Always probe per-dex
  ({"type":"clearinghouseState","user":X,"dex":"xyz"}) before calling a wallet dead.
- BE GENTLE: sleep >=0.3s between calls. Parallel agents WILL trigger 429s otherwise.
