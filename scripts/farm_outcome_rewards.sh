#!/usr/bin/env bash
# Farm Outcome (outcome.xyz / Monarch) LP rewards across chosen outcome surfaces.
#
# One maker process per leg. Outcome legs are spot-like, so a maker can only
# BID (you cannot short what you do not hold) — which means a YES+NO pair is
# what makes us "two-sided" on the scored probability surface, and the
# two-sided multiplier (1x -> 3x) is the single biggest lever in the scoring
# formula. Always launch both legs of a surface, never one.
#
# Usage:  MINUTES=120 USD=25 ./scripts/farm_outcome_rewards.sh 4161 4160 4162
#         (args are hyperliquid_outcome_ids; legs are <id>0 and <id>1)
#
# NOTE: killing these processes with SIGKILL leaves orders RESTING — the
# cancel-on-exit is in a `finally` block that needs the process to exit
# cleanly. Stop them with `touch KILL` or plain `kill` (SIGTERM), then verify
# openOrders is empty.
set -uo pipefail
cd "$(dirname "$0")/.."

MINUTES="${MINUTES:-120}"
USD="${USD:-25}"

if [ "$#" -eq 0 ]; then
  echo "usage: MINUTES=120 USD=25 $0 <outcome_id> [outcome_id ...]" >&2
  exit 2
fi

for OID in "$@"; do
  for SIDE in 0 1; do
    COIN="#${OID}${SIDE}"
    nohup .venv/bin/python scripts/run_outcome_maker.py \
      --coin "$COIN" \
      --minutes "$MINUTES" \
      --usd-per-side "$USD" \
      --max-inventory-usd "$(awk "BEGIN{print $USD + 5}")" \
      --execute \
      > "state/maker_${OID}${SIDE}.log" 2>&1 &
    echo "  launched $COIN pid=$!"
    sleep 2
  done
done

echo "launched $(( $# * 2 )) legs, \$${USD}/side, ${MINUTES}min"
