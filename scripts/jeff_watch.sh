#!/usr/bin/env bash
# Jeff → Quorra escalator.
#
# Watches state/proposals/ + state/strategist_*.md for NEW findings since
# the last-read pointer. When new findings land, sends a Type B (yellow /
# strategy) escalation to Telegram, then updates the pointer.
#
# Rationale: before this, Jeff (quant-researcher cron) burned 3.3M tokens
# per run producing evidenced findings that landed in state/ files nobody
# read. Personas.md said "Jeff reports findings" but there was no wire.
# Now: Jeff's output actually reaches Quorra.
#
# Idempotent: safe to run every N minutes. Only fires on files with mtime
# newer than the last-read pointer. Zero action on first-run baseline (it
# just stamps the pointer to "now").
#
# Deploy: run from operator_tier1.timer as a companion step, or its own
# systemd timer. Runs under the same $0-tokens principle as tier1.

set -euo pipefail
cd "$(dirname "$0")/.."

POINTER=state/jeff_last_read
ALERTS=state/jeff.alerts

# First run: stamp pointer to now and exit silently. Prevents alert-flood
# on the 30+ existing historical proposals.
if [ ! -f "$POINTER" ]; then
  date -u +%s > "$POINTER"
  echo "[$(date -u +%FT%TZ)] jeff_watch: first run, pointer initialized" >> "$ALERTS"
  exit 0
fi

last_read=$(cat "$POINTER")
ts=$(date -u +%FT%TZ)

# Find findings newer than pointer. Two conventions:
#   - state/proposals/YYYY-MM-DD_strategist.md  (newer format)
#   - state/strategist_*.md                     (older/legacy format)
new_files=$(find state/proposals -type f -name '*.md' -newer "$POINTER" 2>/dev/null; \
            find state -maxdepth 1 -type f -name 'strategist_*.md' -newer "$POINTER" 2>/dev/null)

if [ -z "$new_files" ]; then
  exit 0   # nothing new, no noise
fi

n=$(echo "$new_files" | wc -l)
newest=$(echo "$new_files" | head -1)
newest_name=$(basename "$newest")

# Extract a title + first meaningful paragraph as the summary
title=$(head -1 "$newest" | sed 's/^# //')
summary=$(awk '
  /^$/ {if (seen) exit}
  /^[^# ]/ {seen=1; print}
' "$newest" | head -30 | tr '\n' ' ' | cut -c1-500)

# Build Telegram message. Uses the same env pattern as operator_tier1.sh.
msg="[JEFF · Type B / Yellow]
${n} new finding(s), latest: ${newest_name}

${title}

${summary}...

Path: ${newest}
Escalation: Quorra to review, decide, respond."

# Log locally regardless of whether Telegram is reachable
echo "[$ts] JEFF ESCALATION: ${n} findings, latest=${newest_name}" >> "$ALERTS"

# Try Telegram; log-only if env not set (matches operator_tier1.sh pattern)
if [ -f .env ]; then
  # shellcheck disable=SC1091
  source .env 2>/dev/null || true
  if [ -n "${ALERT_WEBHOOK_URL:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
    curl -sS --max-time 15 -X POST "$ALERT_WEBHOOK_URL" \
      -d chat_id="$TELEGRAM_CHAT_ID" \
      -d text="$msg" \
      >/dev/null 2>&1 || echo "[$ts] jeff_watch: telegram send failed" >> "$ALERTS"
  fi
fi

# Update pointer AFTER successful escalation. If Telegram fails but we've
# logged, still advance — the alerts file is the durable record.
date -u +%s > "$POINTER"
