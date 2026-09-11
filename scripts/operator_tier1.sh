#!/usr/bin/env bash
# TIER 1 operator. Runs on a cron, costs ZERO tokens.
#
# 2026-09-11: the operator agent was spending ~991k Opus tokens/day, and on
# roughly 95% of runs its entire output was "everything is fine". That is not
# judgement, it is pattern-matching on known-shape facts -- so a shell script
# can do it, and the agent only needs to exist when something is actually wrong.
#
# Escalation writes a marker the agent cron reads. Healthy runs write nothing
# and cost nothing.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

out=$(./scripts/status.py --check 2>&1); code=$?
ts=$(date -u +%FT%TZ)

if [ $code -eq 0 ]; then
  echo "$ts HEALTHY" >> state/tier1.log
  exit 0
fi

echo "$ts $out" >> state/tier1.log
echo "$out" > state/ESCALATE          # agent cron checks for this
source .env 2>/dev/null && curl -sS --max-time 15 -X POST "$ALERT_WEBHOOK_URL" \
  -d chat_id="$TELEGRAM_CHAT_ID" -d text="tier1: $out" >/dev/null 2>&1
exit 1
