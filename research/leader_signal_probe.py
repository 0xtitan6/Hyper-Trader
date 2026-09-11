"""Leader-signal probe: do June-19 leader features predict June19->now forward PnL?

Out-of-sample predictability test. Features = the June-19 snapshot in
outcome_leaders_directional_full.csv. Label = each leader's realized PnL from
the snapshot to now, fetched fresh via the bot's own load_metrics (tested
fetch + 429 backoff). Writes research/leader_forward_pnl.csv incrementally.

Gentle on HL (sleep between leaders) so it never disturbs the live engine.
"""
import csv
import datetime
import os
import sys
import time

sys.path.insert(0, "/home/ec2-user/.openclaw/workspace/hyper-trader")
from dotenv import load_dotenv

load_dotenv("/home/ec2-user/.openclaw/workspace/hyper-trader/.env")
from hyperliquid.info import Info  # noqa: E402
from hyperliquid.utils import constants  # noqa: E402

from src.leader_score import load_metrics  # noqa: E402

REPO = "/home/ec2-user/.openclaw/workspace/hyper-trader"
SRC = f"{REPO}/research/outcome_leaders_directional_full.csv"
OUT = f"{REPO}/research/leader_forward_pnl.csv"

# June-19 15:16 UTC snapshot (mtime of the research CSV)
SNAP = datetime.datetime(2026, 6, 19, 15, 16, tzinfo=datetime.timezone.utc).timestamp()
lookback_h = (time.time() - SNAP) / 3600.0

info = Info(constants.MAINNET_API_URL, skip_ws=True)

with open(SRC) as f:
    rows = list(csv.DictReader(f))

done = set()
if os.path.exists(OUT):
    with open(OUT) as f:
        for r in csv.DictReader(f):
            done.add(r["address"])

write_header = not os.path.exists(OUT)
with open(OUT, "a", newline="") as fo:
    w = csv.writer(fo)
    if write_header:
        w.writerow(
            ["address", "rank", "overall_pnl_30d", "win_rate", "median_holding_h",
             "fills_per_day", "max_single_loss", "quality_score",
             "fwd_pnl", "fwd_sharpe", "fwd_trades", "fwd_closing_fills"]
        )
    n = 0
    for r in rows:
        addr = r["address"]
        if addr in done:
            continue
        try:
            m = load_metrics(info, addr, lookback_hours=lookback_h)
        except Exception:
            m = None
        if m is None:
            fwd = ["", "", "", ""]
        else:
            fwd = [round(m.total_realized_pnl_usd, 2), round(m.realized_pnl_sharpe, 4),
                   m.trade_count, m.closing_fill_count]
        w.writerow([addr, r.get("rank"), r.get("overall_pnl_30d"), r.get("win_rate"),
                    r.get("median_holding_h"), r.get("fills_per_day"),
                    r.get("max_single_loss"), r.get("quality_score"), *fwd])
        fo.flush()
        n += 1
        time.sleep(1.5)  # gentle on HL / live bot
print(f"DONE: fetched {n} leaders (of {len(rows)})")
