#!/usr/bin/env bash
# Sally gate — ExecStartPre for hyper-trader.service (and any Warren unit).
#
# Composes three deterministic checks. Non-zero exit = ship blocked.
#
# Failure profile: PURE config-parse + git + tests + local process check.
# No network. No HL API. No hyperliquid SDK. Deliberate — this runs as an
# ExecStartPre and Restart=always, so a bug here would block automatic
# crash-recovery restarts. Any environmental dependency turns a transient
# HL blip into a permanent outage.
#
# Break-glass:
#   SALLY_OVERRIDE=1 SALLY_OVERRIDE_REASON="<why>" systemctl start hyper-trader
#
# Override fires a Telegram alert from THIS wrapper (not from Warren, who
# won't have started yet if we're overriding). Reason is REQUIRED. Every
# override writes state/sally_override_<epoch>.json for audit.
#
# Design principle: "an override that's audited isn't a bypass."
#
# 2026-09-25 initial. Ships as ExecStartPre once Neil approves the
# sudo systemctl edit hyper-trader step.

set -uo pipefail
cd "$(dirname "$0")/.."

ts=$(date -u +%FT%TZ)
epoch=$(date -u +%s)

# ============================================================
# BREAK-GLASS: SALLY_OVERRIDE
# ============================================================
if [ "${SALLY_OVERRIDE:-}" = "1" ]; then
  reason="${SALLY_OVERRIDE_REASON:-}"
  if [ -z "$reason" ]; then
    echo "FAIL  SALLY_OVERRIDE=1 requires SALLY_OVERRIDE_REASON=\"...\""
    echo "BLOCKED  break-glass rejected without reason"
    exit 2
  fi
  # Audit record — durable, greppable
  mkdir -p state
  cat > "state/sally_override_${epoch}.json" <<EOF
{
  "ts": "$ts",
  "epoch": $epoch,
  "reason": $(printf '%s' "$reason" | python3 -c 'import json, sys; print(json.dumps(sys.stdin.read()))'),
  "user": "$(whoami)",
  "systemd_invocation_id": "${INVOCATION_ID:-none}"
}
EOF
  # Telegram alert — from THIS wrapper, so it fires even if Warren won't start
  if [ -f .env ]; then
    # shellcheck disable=SC1091
    source .env 2>/dev/null || true
    if [ -n "${ALERT_WEBHOOK_URL:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
      msg="[SALLY OVERRIDE · $ts]
Warren starting with Sally gate bypassed.
Reason: $reason
Audit: state/sally_override_${epoch}.json"
      curl -sS --max-time 10 -X POST "$ALERT_WEBHOOK_URL" \
        -d chat_id="$TELEGRAM_CHAT_ID" \
        -d text="$msg" >/dev/null 2>&1 || true
    fi
  fi
  echo "ok    SALLY_OVERRIDE=1 accepted (audited: state/sally_override_${epoch}.json)"
  echo "OVERRIDE  gate bypassed by explicit override, Telegram alerted"
  exit 0
fi

# ============================================================
# NORMAL GATE: three composed checks
# ============================================================
fails=0

echo "--- preflight_deploy.sh ---"
if ! ./scripts/preflight_deploy.sh; then
  fails=$((fails+1))
fi

echo
echo "--- invariant_check.py (config-parse only, no I/O) ---"
if ! .venv/bin/python scripts/invariant_check.py; then
  fails=$((fails+1))
fi

echo
echo "--- ruff + pytest (tests + lint) ---"
# We don't call `just check` directly because `just` isn't on the systemd
# PATH; instead we run the same commands its `check` recipe expands to
# (see justfile). Cap the pytest at 60s — a hung test must not block boot.
gate_check_ok=1
if ! .venv/bin/ruff check src tests >/dev/null 2>&1; then
  echo "FAIL  ruff check failed"
  gate_check_ok=0
fi
if ! .venv/bin/ruff format --check src tests >/dev/null 2>&1; then
  echo "FAIL  ruff format --check failed"
  gate_check_ok=0
fi
if ! timeout 60 .venv/bin/python -m pytest tests/ -q --tb=line >/dev/null 2>&1; then
  echo "FAIL  pytest failed or timed out (>60s)"
  gate_check_ok=0
fi
if [ $gate_check_ok -eq 1 ]; then
  echo "ok    ruff + pytest passed"
else
  fails=$((fails+1))
fi

echo
if [ $fails -eq 0 ]; then
  echo "SALLY OK   $ts   all gates passed"
  exit 0
else
  echo "SALLY BLOCKED   $ts   $fails gate(s) failed"
  echo
  echo "To override (audited): SALLY_OVERRIDE=1 SALLY_OVERRIDE_REASON=\"...\" systemctl start hyper-trader"
  exit 1
fi
