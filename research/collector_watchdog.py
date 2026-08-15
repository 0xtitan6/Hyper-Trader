"""Collector watchdog — protects the dry-run week's data integrity.

The 4 research processes (book/tape/maker-dryrun/new-market) run detached with no
supervisor. If one dies or hangs silently, the week's dataset gets gaps that corrupt
the maker go/no-go analysis. They're all READ-ONLY (REST/WS reads or --dry-run, no
orders) so — unlike the mirror engine where a double-launch means double orders —
they are SAFE to auto-relaunch. This watchdog checks liveness (+ output freshness
where the write cadence is regular) every few minutes, relaunches the dead/hung one,
and Telegram-alerts on any action.

Anchored process matching (".venv/bin/python <script>") avoids the pgrep self-match
trap. Self-expires with the week. Detached; it does NOT watch itself.
"""
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

REPO = "/home/ec2-user/.openclaw/workspace/hyper-trader"
sys.path.insert(0, REPO)
from dotenv import load_dotenv
load_dotenv(f"{REPO}/.env")

WEEK_END = datetime(2026, 7, 14, 1, 0, tzinfo=timezone.utc)
CHECK_S = 300
PY = f"{REPO}/.venv/bin/python"
WEBHOOK = os.environ.get("ALERT_WEBHOOK_URL", "")
CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")

# (name, script-anchor+args, output file, stale_seconds[0=liveness-only])
PROCS = [
    ("book",       "research/ml_data_collector.py",        "research/ml_market_snapshots.jsonl", 240),
    ("tape",       "research/trade_flow_collector.py",      "research/trade_flow.jsonl",          0),
    ("maker-week", "research/maker_week_cycle.py --loop",   "research/maker_dryrun_week.jsonl",   3000),
    ("new-market", "research/new_market_monitor.py",        "research/new_markets.jsonl",         0),
]


def tg(text):
    if not (WEBHOOK and CHAT):
        return
    try:
        body = urllib.parse.urlencode({"chat_id": CHAT, "text": text}).encode()
        urllib.request.urlopen(urllib.request.Request(
            WEBHOOK, data=body, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"}), timeout=10)
    except Exception:
        pass


def alive(anchor):
    # anchored to the python interpreter to avoid matching this watchdog / shells
    script = anchor.split()[0]
    r = subprocess.run(["pgrep", "-f", rf"\.venv/bin/python .*{script}"],
                       capture_output=True, text=True)
    return bool(r.stdout.strip())


def relaunch(anchor):
    subprocess.Popen(f"cd {REPO} && setsid {PY} {anchor} >/dev/null 2>&1 < /dev/null &",
                     shell=True)


def stale(path, limit):
    if limit <= 0:
        return False
    try:
        return (time.time() - os.path.getmtime(f"{REPO}/{path}")) > limit
    except OSError:
        return True  # missing output = unhealthy


def main():
    # grace: let collectors settle before first check
    time.sleep(30)
    while datetime.now(timezone.utc) <= WEEK_END:
        for name, anchor, out, stale_s in PROCS:
            try:
                dead = not alive(anchor)
                hung = (not dead) and stale(out, stale_s)
                if dead or hung:
                    if hung:
                        # kill the hung instance first so we don't double-run
                        subprocess.run(["pkill", "-f", rf"\.venv/bin/python .*{anchor.split()[0]}"])
                        time.sleep(2)
                    relaunch(anchor)
                    tg(f"🔧 watchdog: {name} was {'HUNG (output stale)' if hung else 'DOWN'} — relaunched.")
            except Exception:
                pass
        # sleep in small increments so shutdown is responsive to WEEK_END
        end = time.time() + CHECK_S
        while time.time() < end and datetime.now(timezone.utc) <= WEEK_END:
            time.sleep(20)


if __name__ == "__main__":
    main()
