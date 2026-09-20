#!/usr/bin/env bash
# Redeploy free USDC into fresh HIP-4 pair quotes. Deterministic, zero tokens.
#
# WHY THIS EXISTS
# Capital frees up constantly and silently: a basket settles, the minder pulls
# quotes 3h before kickoff, an edge decays and an order is cancelled. Without
# this, that capital sits idle until a human runs the maker by hand. On
# 2026-09-20 the account sat with $124 free for hours for exactly this reason.
#
# WHY IT IS SAFE TO RUN UNATTENDED
#  - run_pair_maker refuses outright if ./KILL exists or the score feed is down
#  - src/gamestate refuses any surface inside KICKOFF_BUFFER_H of kickoff, the
#    SAME constant the minder cancels on, so this can never fight the minder
#  - orders are post-only (Alo): they can never take, never pay a spread
#  - both legs are capital-reserved before either is placed, so it cannot leave
#    a lone resting bid — the unchosen directional bet that cost -$47
#  - it only ever spends FREE spot USDC; it cannot touch perp margin
#
# Bounded per run: MAX_PAIRS * USD_PER_LEG * 2.
set -uo pipefail
cd "$(dirname "$0")/.."

USD_PER_LEG=${USD_PER_LEG:-20}
MAX_PAIRS=${MAX_PAIRS:-2}
MIN_EDGE=${MIN_EDGE:-0.010}
MIN_DEPTH=${MIN_DEPTH:-60}

out=$(timeout 600 .venv/bin/python scripts/run_pair_maker.py \
        --execute --usd-per-leg "$USD_PER_LEG" --max-pairs "$MAX_PAIRS" \
        --min-edge "$MIN_EDGE" --min-depth "$MIN_DEPTH" 2>&1); code=$?
ts=$(date -u +%FT%TZ)
echo "$ts [$code] $out" >> state/pair_requote.log

# Only speak when it actually rested something. A quiet cycle is the norm:
# most runs find no free capital or no surface clearing MIN_EDGE.
rested=$(printf '%s' "$out" | grep -c ' rested #' || true)
[ "$rested" -eq 0 ] && exit 0
# shellcheck disable=SC1091
source .env 2>/dev/null && curl -sS --max-time 15 -X POST "$ALERT_WEBHOOK_URL" \
  -d chat_id="$TELEGRAM_CHAT_ID" -d text="pair requote: rested $rested leg(s)
$(printf '%s' "$out" | grep -E ' rested #|free USDC')" >/dev/null 2>&1
exit 0
