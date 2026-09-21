#!/usr/bin/env bash
# Mind live HIP-4 pair positions. Deterministic, zero tokens, alerts only on action.
set -uo pipefail
cd "$(dirname "$0")/.."
out=$(.venv/bin/python scripts/pair_minder.py --execute 2>&1); code=$?
ts=$(date -u +%FT%TZ)
echo "$ts [$code] $out" >> state/pair_minder.log
[ $code -eq 0 ] && exit 0      # nothing needed
# shellcheck disable=SC1091
source .env 2>/dev/null && curl -sS --max-time 15 -X POST "$ALERT_WEBHOOK_URL" \
  -d chat_id="$TELEGRAM_CHAT_ID" -d text="pair minder acted:
$out" >/dev/null 2>&1
exit 0
