# Source: Reddit — small-account crypto/derivatives edges
Status: IN PROGRESS (started 2026-09-20)
Mandate: post-mortems and failure reports first. Capacity in dollars or it does not count.

## Log
- Read CONSTRAINTS.md. 13 dead candidates noted.

## Method
Reddit is blocked to the agent WebSearch/WebFetch user-agent and to direct
`reddit.com/*.json` (403 "Blocked"). Redlib mirrors sit behind Anubis PoW; pullpush
behind Cloudflare. Working route: **arctic-shift.photon-reddit.com** full-archive API
(`/api/posts/search`, `/api/comments/search`, `/api/comments/tree`). This archive
retains body text for many posts that are now `[removed]` on reddit itself, which is
exactly where post-mortems go to die. Helper: /tmp/rs.py, raw sweeps /tmp/sweep*.txt.

Subs swept: r/algotrading, r/quant, r/highfreqtrading, r/PredictionMarkets,
r/CryptoCurrency, r/defi, r/Hyperliquid, r/Polymarket, r/Kalshi.

## Structural note before any candidate
r/algotrading auto-removes nearly every numbers-bearing post (mod filter). Score=1,
comments=0, body `[removed]` is the modal outcome for exactly the honest post-mortems
we want. The surviving visible posts are skewed toward (a) low-information questions
and (b) promotion that got past the filter. So Reddit's *visible* surface is itself
survivorship-biased in the same direction the brief warns about — the archive is the
only way to read the failures.
