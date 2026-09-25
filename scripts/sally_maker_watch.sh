#!/bin/bash
# Sally weekend maker watch. Polls every 10 min. Silent when good.
# Now watches: 2 makers + book_logger + polymarket_poller
# Writes status to state/sally_maker.status, alerts to state/sally_maker.alerts
STATE_DIR="/home/ec2-user/.openclaw/workspace/hyper-trader/state"
STATUS="$STATE_DIR/sally_maker.status"
ALERTS="$STATE_DIR/sally_maker.alerts"
JOURNAL="$STATE_DIR/journal.jsonl"
COINS=("#44650" "#45160")

while true; do
  TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  # Match on actual argv (starts with the python interpreter path), not the
  # bash wrapper's cmdline which quotes the whole thing inside itself.
  ALIVE_MAKERS=$(ps -eo pid,args | awk '/^ *[0-9]+ [^ ]*python.*-m src\.maker.*--coin/{n++} END{print n+0}')
  ALIVE_LOGGER=$(ps -eo pid,args | awk '/^ *[0-9]+ [^ ]*python[^ ]* scripts\/book_logger\.py/{n++} END{print n+0}')
  ALIVE_POLY=$(ps -eo pid,args | awk '/^ *[0-9]+ [^ ]*python[^ ]* scripts\/polymarket_poller\.py/{n++} END{print n+0}')
  ALIVE_KALSHI=$(ps -eo pid,args | awk '/^ *[0-9]+ [^ ]*python[^ ]* scripts\/kalshi_poller\.py/{n++} END{print n+0}')

  {
    echo "== sally $TS =="
    echo "alive_makers=$ALIVE_MAKERS (expected=2)"
    echo "alive_book_logger=$ALIVE_LOGGER (expected=1)"
    echo "alive_polymarket_poller=$ALIVE_POLY (expected=1)"
    echo "alive_kalshi_poller=$ALIVE_KALSHI (expected=1)"
    for c in "${COINS[@]}"; do
      pgrep -af "src\.maker.*coin $c" | head -1 || echo "MISSING: $c"
    done
    echo "--- last 24h own_fills ---"
    python3 -c "
import json, time
cutoff = time.time() - 86400
fills = {'#44650': 0, '#45160': 0}
for line in open('$JOURNAL'):
    try: r = json.loads(line)
    except: continue
    if r.get('ts',0) < cutoff: continue
    c = r.get('coin','')
    if r.get('event') == 'own_fill' and c in fills:
        fills[c] += 1
for c,n in fills.items(): print(f'  {c}: {n} fills')
"
    echo "--- book snapshot line counts ---"
    wc -l $STATE_DIR/book_snapshots/*.jsonl 2>/dev/null | tail -3
    echo "--- polymarket snap count ---"
    ls $STATE_DIR/polymarket/ 2>/dev/null | wc -l
  } > "$STATUS.tmp" && mv "$STATUS.tmp" "$STATUS"

  # Alerts
  if [ "$ALIVE_MAKERS" -lt 2 ]; then
    echo "[$TS] ALERT: only $ALIVE_MAKERS of 2 makers alive" >> "$ALERTS"
  fi
  if [ "$ALIVE_LOGGER" -lt 1 ]; then
    echo "[$TS] ALERT: book_logger DOWN" >> "$ALERTS"
  fi
  if [ "$ALIVE_POLY" -lt 1 ]; then
    echo "[$TS] ALERT: polymarket_poller DOWN" >> "$ALERTS"
  fi
  if [ "$ALIVE_KALSHI" -lt 1 ]; then
    echo "[$TS] ALERT: kalshi_poller DOWN" >> "$ALERTS"
  fi
  sleep 600
done
