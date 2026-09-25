#!/usr/bin/env bash
# Persona-tagged escalation helper.
#
# Any script can source or call this to fire a formatted Telegram alert
# from a named persona. Aligns with ESCALATION.md types A/B/C/D.
#
# Usage:
#   scripts/escalate.sh houston red "kill fired: max_daily_loss_usd breach"
#   scripts/escalate.sh jeff yellow "9 findings, latest 2026-09-24_strategist.md"
#   scripts/escalate.sh sally orange "gate blocked: 2 invariants failed"
#   scripts/escalate.sh houston blue "reconcile stale >15min"
#
# Persona → emoji + tagline mapping so Quorra can read the source at a glance.
# Message is written to state/escalations.log regardless of Telegram reachability.

set -uo pipefail
cd "$(dirname "$0")/.."

if [ $# -lt 3 ]; then
  echo "usage: $0 <persona> <color> <message>" >&2
  echo "  persona: houston | warren | jeff | sally | data" >&2
  echo "  color:   red (safety) | yellow (strategy) | orange (quality) | blue (ops)" >&2
  exit 2
fi

persona="$1"
color="$2"
shift 2
message="$*"
ts=$(date -u +%FT%TZ)

case "$persona" in
  houston) emoji="🤖"; commit="\"If it breaks, I kill it. If I kill it, you know.\"" ;;
  warren)  emoji="📈"; commit="\"I own every fill.\"" ;;
  jeff)    emoji="🔬"; commit="\"Good research beats fast trading.\"" ;;
  sally)   emoji="✅"; commit="\"If I didn't test it, it doesn't ship.\"" ;;
  data)    emoji="📊"; commit="\"Fresh data, every interval.\"" ;;
  *) echo "unknown persona: $persona" >&2; exit 2 ;;
esac

case "$color" in
  red)    type_label="Type A / Red / Safety" ;;
  yellow) type_label="Type B / Yellow / Strategy" ;;
  orange) type_label="Type C / Orange / Quality" ;;
  blue)   type_label="Type D / Blue / Ops" ;;
  *) echo "unknown color: $color" >&2; exit 2 ;;
esac

# Human-readable Telegram message
tg_msg="[${emoji} ${persona^^} · ${type_label}]
${message}

${commit}
${ts}"

# Structured log (append-only, greppable)
mkdir -p state
printf '%s persona=%s color=%s msg=%q\n' "$ts" "$persona" "$color" "$message" \
  >> state/escalations.log

# Telegram (log-only fallback matches sally_gate.sh + operator_tier1.sh pattern)
if [ -f .env ]; then
  # shellcheck disable=SC1091
  source .env 2>/dev/null || true
  if [ -n "${ALERT_WEBHOOK_URL:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
    curl -sS --max-time 10 -X POST "$ALERT_WEBHOOK_URL" \
      -d chat_id="$TELEGRAM_CHAT_ID" \
      -d text="$tg_msg" >/dev/null 2>&1 || true
  fi
fi

echo "$tg_msg"
