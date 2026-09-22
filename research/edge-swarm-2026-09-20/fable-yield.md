# Yield / structural income scout — 2026-09-20 (Fable)

Benchmark: HLP vault 3.86% APR (~$22/yr on $565). Anything below is dead on arrival.
Account: ~$565 on Hyperliquid. Do not re-propose the 13 dead candidates in CONSTRAINTS.md.

## Work log (as-I-go)

### 1. HL funding-rate scan (MEASURED, api.hyperliquid.xyz, 2026-09-20)
- Top |funding| perps: ACE -275% APR (OI $460k), GOAT +104%, HEMI -83%, USELESS +69%, NEAR +33% (OI $267M).
- Cluster of coins with HL spot pairs sit at EXACTLY +11.0% APR funding = Hyperliquid's baseline
  interest component (0.01%/8h = 10.95% APR), i.e. premium ~0. Structural, paid long->short.
- Delta-neutral (spot long + perp short) on these = the same shape as the DEAD "HYPE funding carry"
  candidate. Without portfolio margin ($10k gate), spot and perp margin are separate balances:
  $565 splits ~$282 spot + $282 perp margin at 1x -> collect ~11% on $282 = ~$31/yr = 5.5% on equity
  BEFORE spot round-trip fees (~14bp) + perp fees (9bp) + funding-flip risk + rebalance ops.
  Marginally above HLP 3.86% gross, not risk-adjusted. NOT proposing (dead shape, CONSTRAINTS #4).

### 2. HL vault screen (MEASURED, stats-data.hyperliquid.xyz/Mainnet/vaults, n=9,475)
- 9,475 vaults total; 3,110 open; screened = open, non-child, TVL>=$50k, age>=90d -> n=98.
- APR distribution of screened (fractional field, x100 = %):
  min -55.2%, p10 -8.0%, p25 +2.8%, median +40.7%, p75 +157%, p90 +463%, max +3763%.
  23/98 negative. 72/98 nominally beat HLP's 3.86%.
- CAVEAT: "apr" is trailing performance of a discretionary/algo TRADING vault, not yield.
  Depositing = buying someone's price-prediction risk + 10% leader profit share.
  Distribution is survivorship-heavy (dead vaults closed). Needs drawdown check -> next.

### 3. Vault details + drawdowns (MEASURED, vaultDetails, top-20 screened + HLP)
- HLP: apr 3.9%, maxDD 2.5% of TVL, $186M TVL, deposits open. Benchmark confirmed.
- Every high-APR vault is a leveraged trading book: maxDD as % of current TVL:
  Brob 11.7%, BredoStrategy 42%, Long LINK Short XRP 118%, TAPTRADE 2321% (!),
  DailyTradeAI 457%, intothecryptoverse 1844%. Several top vaults have deposits CLOSED
  (TAPTRADE, Wonderland, VaultBot V2, Delta_01, Enjoyooor V3, Aquila).
- Verdict on vaults: trailing APR is trading performance, and our own copy-trade
  measurement (n=964, t=0.25) says past leader performance does not predict forward PnL.
  A vault deposit is copy-trading with perfect execution but the same dead signal.
  Nothing here is "yield". HLP remains the only vault whose return is structural.

### 4. Stablecoin yields reachable from this account (MEASURED via yields.llama.fi, 2026-09-20)
Chain "Hyperliquid L1" = HyperEVM. HL Core -> HyperEVM transfer is native (no bridge fee;
needs pennies of HYPE for gas). Arbitrum reachable for flat $1 HL withdrawal fee.

HyperEVM stable pools (base APY, no reward-token fluff), TVL >= $1M:
- growihf USDC "147% apy" — 30d mean 293%: a trading fund, NOT yield. Treat as PROMOTIONAL until proven.
- pendle-v2 PT-LIMUSD 10.23% FIXED ($1.5M TVL) — fixed rate on Liminal basis token
- monetrix sUSDM 9.54% ($2.2M) — small/new, skip
- liminal-basis LIMUSD 7.61% ($9.4M) — HL basis/funding-capture wrapper (the >$10k-gate trade, packaged)
- harmonix USDC 6.82% ($21.4M) — strategy vault, need risk check
- morpho-blue K3USDC 5.76% ($13.3M), feUSDT0v2 5.76% ($3.5M), feUSDCv2 5.26% ($9.9M), feUSDC 4.44% ($6.2M)
- felix-cdp feUSD stability pool 5.13% ($5.5M)
- hyperlend USDC 3.66% ($33.3M; 30d mean 5.48%)

Arbitrum (after $1 withdrawal): fluid USDC 4.46%, aave-v3 USDC 3.84%, sky sUSDS 3.60%.
=> Arbitrum adds nothing over HyperEVM and costs $1 + leaves HL ecosystem. Drop.

Math at $565 (vs HLP $22/yr):
- Morpho K3/Felix USDC ~5.5% -> ~$31/yr (+$9 over HLP). Setup cost ~$2-3 (buy dust HYPE for gas + transfers).
- Liminal LIMUSD 7.6% -> ~$43/yr (+$21). Extra layer: strategy drawdown risk when funding flips.
- Pendle PT-LIMUSD 10.2% fixed -> ~$58/yr (+$36) IF entry slippage small; 3 stacked protocols.
At $10,000: Morpho ~$550/yr, Liminal ~$760/yr, PT ~$1,020/yr vs HLP $386/yr. Capacity: pools are $1.5M-$33M, our size is irrelevant.

### 5. 90d APY history of finalists (MEASURED, yields.llama.fi/chart)
- harmonix USDC:   n=90d, median 7.13%, min 5.73%, max 10.10%, now 6.82% ($21.4M TVL)
- liminal LIMUSD:  n=54d, median 7.54%, min 0.00%, max 17.25%, now 7.61% ($9.4M)
- morpho K3USDC:   n=14d only (new), median 5.72% ($13.3M)
- morpho feUSDCv2: n=18d only, median 5.51% ($9.9M)
- hyperlend USDC:  n=90d, median 5.81%, min 3.72% (= now), max 13.07% ($33.3M)
- growihf USDC:    max 12,455% in history -> junk/marked-to-fantasy. DISMISSED.
Harmonix/Liminal = packaged delta-neutral HL funding capture (long spot/short perp, portfolio-margin
scale). This is precisely the trade the $10k gate blocks us from running ourselves — packaged, it is
accessible at $565. Docs claims of "13% APY / 35%" are PROMOTIONAL; use measured 6.8-7.6%.
Sources: docs.liminal.money/more/risks, app.harmonix.fi (3-day unbonding), yields.llama.fi.

### 6. Access path + costs (SOURCED, hyperliquid.gitbook.io llms-full.txt)
- Perp USDC -> Spot USDC: free, instant. Spot -> HyperEVM: native transfer button, gas in HYPE
  on Core side; EVM -> Core costs HYPE gas on EVM. No bridge fee. Need ~$2-3 HYPE dust for gas
  (buy on HL spot, ~0.07% taker fee). Total round-trip cost to deploy $565: well under $1 in fees
  + $2-3 HYPE gas float. Arbitrum route ($1 flat withdrawal) unnecessary — nothing there beats HyperEVM.

### 7. Considered and dismissed (brief)
- Liquidation-bot economics: on HL core, liquidation flow is routed to HLP's liquidator child vault —
  retail access to HL liquidation economics IS an HLP deposit (the 3.86% benchmark itself). On HyperEVM
  lending (Morpho/HyperLend), liquidations are open but bot-competitive and engineering-heavy;
  capacity at $565 unmeasurable in a day. UNVERIFIED, not pursued.
- Oracle-update arb: HL oracle validator-pushed ~3s; HyperEVM lending reads HyperCore precompile
  prices — no stale-oracle window at our latency. UNVERIFIED dismissal.
- HIP-3 collateral quirks: per-dex isolated collateral (per-dex-collateral memory) earns nothing while
  parked; no HIP-3 dex pays for collateral presence. MEASURED from live ops. Nothing to collect.
- Negative-funding capture (ACE -275% APR): would need long perp + SHORT spot; no HL borrowable spot,
  cross-venue shorting not reachable at $565. Price-risk-free version impossible. Dismissed.
- HYPE staking ~1.9-2.9% (kinetiq measured 1.94%): below benchmark + HYPE price risk. Dismissed.
- HL trading vaults (n=9,475 screened): trailing APR is trading performance; deposits = copy-trading
  with perfect execution; our own n=964 measurement says the signal is a coin flip. Only HLP is structural.
- Points programs on HyperEVM protocols (Liminal/Harmonix/Felix/HyperLend run them): free option on top
  of measured yield, value UNVERIFIED — do not underwrite with it, but it matches the "paid in another
  currency" shape CONSTRAINTS favours.

## VERDICT
Best found: **Harmonix USDC vault on HyperEVM — measured 7.13% median APY over 90d (min 5.73%),
$21.4M TVL, delta-neutral HL funding capture, no price prediction, 3-day unbonding.**
Runner-up with less strategy risk but shorter track: Morpho Blue USDC vaults (K3/Felix curators)
~5.5% lending APY. Both reachable for <$1 in fees via native Core->EVM transfer.

Beats 3.86%? NOMINALLY YES: 7.1% vs 3.86% = +3.3pp.
- At $565: HLP $22/yr -> Harmonix ~$40/yr. Uplift +$18/yr.
- At $10,000: HLP $386/yr -> Harmonix ~$713/yr. Uplift +$327/yr.
- Capacity: pool TVLs $9M-$33M; our size is irrelevant. First candidate all cycle where capacity is NOT the binding constraint.
RISK-ADJUSTED: honest call is "marginal at $565, real at $10k". The +3.3pp premium buys smart-contract
+ curator + strategy-drawdown risk that HLP does not carry (HLP maxDD 2.5%, operator-run, $186M).
A single protocol failure costs 100%; at $565 the uplift is $18/yr, so the trade only clearly makes
sense if you assess annual protocol-failure probability below ~3%. At $10k it clears more comfortably.
Nothing else measured — vaults, funding, HIP-3, liquidations, oracle, Arbitrum — beats the benchmark at all.
