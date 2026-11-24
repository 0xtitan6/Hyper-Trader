#!/bin/bash
# Launcher for kalshi_poller — avoids setsid/nohup path-loss bugs in one-liner form
cd /home/ec2-user/.openclaw/workspace/hyper-trader
mkdir -p state/kalshi
LOG="state/kalshi_poller_$(date +%s).log"
echo "starting kalshi_poller, log: $LOG"
exec .venv-ml/bin/python scripts/kalshi_poller.py --interval 300 --series KXNFLGAME --sleep-s 0.25 > "$LOG" 2>&1
