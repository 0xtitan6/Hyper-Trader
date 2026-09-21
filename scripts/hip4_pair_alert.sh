#!/usr/bin/env bash
# Run the HIP-4 pair monitor; alert ONLY when it is actionable.
#
# Deterministic, zero tokens — same tier-1 pattern as operator_tier1.sh. The
# monitor exits 0 only on a model-free arb or a structure clearing absolute-EV
# thresholds, so silence here is the expected state and costs nothing.
set -uo pipefail
cd "$(dirname "$0")/.."

out=$(.venv/bin/python scripts/hip4_pair_monitor.py 2>&1); code=$?
ts=$(date -u +%FT%TZ)
echo "$ts [$code] $out" >> state/hip4_pairs.log

# 1 = no pairs exist, 2 = pairs exist but none qualify. Both are normal.
[ $code -ne 0 ] && exit 0

# shellcheck disable=SC1091
source .env 2>/dev/null && curl -sS --max-time 15 -X POST "$ALERT_WEBHOOK_URL" \
  -d chat_id="$TELEGRAM_CHAT_ID" \
  -d text="HIP-4 pair ACTIONABLE:
$out" >/dev/null 2>&1
exit 0
