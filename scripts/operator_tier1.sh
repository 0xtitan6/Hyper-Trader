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
echo "$out" > state/ESCALATE          # tier-2 agent reads this

# PUSH the tier-2 agent instead of letting it poll.
#
# 2026-09-19: the operator cron fired an LLM agent every 15 min purely to run
# `test -f state/ESCALATE`. Each noop run cost ~79,400 tokens (4 in, ~150 out,
# the rest system prompt + tools) = ~7.6M tokens/day to say "noop", and it
# exhausted the account session limit overnight ("FailoverError: You've hit your
# session limit"), which meant six consecutive runs did nothing at all. The
# irony: the token budget spent proving health is what stopped us detecting ill
# health.
#
# This script already runs every 15 min under systemd for ZERO tokens and is the
# thing that knows whether there is work. So it wakes the agent. The cron keeps a
# once-daily heartbeat so a broken trigger path still surfaces within 24h, and
# the Telegram alert below fires regardless of whether the agent starts.
OPERATOR_JOB="b4c506ef-879f-4bb2-9027-9d71507550c8"
openclaw cron run "$OPERATOR_JOB" >/dev/null 2>&1 \
  || echo "$ts WARN could not trigger operator agent" >> state/tier1.log
source .env 2>/dev/null && curl -sS --max-time 15 -X POST "$ALERT_WEBHOOK_URL" \
  -d chat_id="$TELEGRAM_CHAT_ID" -d text="tier1: $out" >/dev/null 2>&1
exit 1
