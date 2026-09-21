#!/usr/bin/env bash
# Re-quote the one-leg round-trip book. Deterministic, zero tokens.
#
# Runs OFTEN because the whole thesis is exit-as-maker: an unsold leg is a
# directional position, and the sooner it is offered back the sooner the round
# trip closes. Measured 2026-09-21: six minutes between a fill and the response
# cost 105.6 bps on one leg. Latency, not policy, is what we pay for.
set -uo pipefail
cd "$(dirname "$0")/.."
out=$(timeout 540 .venv/bin/python scripts/run_roundtrip_maker.py --execute \
        --usd-per-leg "${USD_PER_LEG:-25}" --max-surfaces "${MAX_SURFACES:-4}" \
        --max-inventory-usd "${MAX_INV:-60}" 2>&1); code=$?
echo "$(date -u +%FT%TZ) [$code] $out" >> state/roundtrip.log
n=$(printf '%s' "$out" | grep -cE ' (BID|OFFER) #' || true)
[ "$n" -eq 0 ] && exit 0
# shellcheck disable=SC1091
source .env 2>/dev/null && curl -sS --max-time 15 -X POST "$ALERT_WEBHOOK_URL" \
  -d chat_id="$TELEGRAM_CHAT_ID" -d text="roundtrip: $n order(s)
$(printf '%s' "$out" | grep -E ' (BID|OFFER) #')" >/dev/null 2>&1
exit 0
