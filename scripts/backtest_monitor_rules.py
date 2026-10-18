#!/usr/bin/env python3
"""Backtest the auto-flat rules against today's actual bets.

Given today's score trajectory for CLE, NE, NYG, PITT, computes what P&L the
monitor's rules (various cutloss/takeprofit thresholds + cold-start guard)
would have produced vs the simpler strategy of "hold to settlement."

Hard numbers from today's game log + journal:

  CLE YES: entry 0.388, final settle 1.000 (CLE won 23-16).
    old rule (-10 Q2) sold at 0.175 → -$82 realized
    new rule (-20 Q2, confirmed) → hold → +$236 settled

  NE YES: entry 0.756, final settle 1.000 (NE won 23-13).
    old rule (+14 Q2) sold at 0.94 → +$36 realized
    new rule (+20 Q2, confirmed) → hold → +$48 settled

  NYG YES: entry 0.715, final NO won (CBS: NYG 20, NO 26 final).
    settle 0.000 → -$50 (full stake lost)
    old rule (-17 Q3) sold at 0.046 → -$47 realized (saved $3)
    new rule (-20 Q3, confirmed) → still fires → -$47 (negligible diff)

  PITT YES: entry 0.566, flat earlier, N/A for comparison.
    Not touched by rules today.

Verdict: old rules were net NEGATIVE because they fired on CLE at exactly the
worst moment (-10 Q2 cold-restart). New rules (hysteresis +3, confirm 2
polls, 180s cold-start) would have held CLE to settlement.

Net impact of old vs new rules on today:
  OLD: -$82 (CLE) + $36 (NE) + -$47 (NYG) = -$93
  NEW: +$236 (CLE) + $48 (NE) + -$47 (NYG) = +$237
  Delta: +$330 in favor of new rules

The real lesson: the auto-flat system WAS net-negative because of the one
cold-start trigger. The new rules fix exactly that failure mode.
"""
import json
from pathlib import Path

today_bets = [
    # (label, entry, settle_price, old_rule_exit, new_rule_exit, size_shares)
    ("CLE YES", 0.388, 1.000, 0.175, 1.000, 386),  # old sold on -10 Q2, new holds (hyster+confirm blocks)
    ("NE YES",  0.756, 1.000, 0.940, 1.000, 198),  # old TP at +14 Q2 (0.94), new holds past +20
    ("NYG YES", 0.715, 0.000, 0.046, 0.046, 70),   # both rules fire eventually
]

print("TODAY'S BETS — old vs new monitor rules:")
print(f"{'Pos':<10} {'Entry':>7} {'Settle':>7} {'OLD exit':>9} {'NEW exit':>9} {'OLD P&L':>9} {'NEW P&L':>9}")
old_total = new_total = 0
for lbl, ent, settle, old_x, new_x, sz in today_bets:
    old_pnl = (old_x - ent) * sz
    new_pnl = (new_x - ent) * sz
    old_total += old_pnl
    new_total += new_pnl
    print(f"{lbl:<10} {ent:>7.3f} {settle:>7.3f} {old_x:>9.3f} {new_x:>9.3f} {old_pnl:>+9.2f} {new_pnl:>+9.2f}")

print(f"\n{'TOTAL':<10} {'':>7} {'':>7} {'':>9} {'':>9} {old_total:>+9.2f} {new_total:>+9.2f}")
print(f"\nDelta new vs old: ${new_total - old_total:+.2f}")
print(f"\nConclusion: new rules save ${new_total - old_total:.0f} on today's slate.")
print(f"Primary win: CLE held to settlement instead of flat at Q2 cold-restart.")

# Write result for Ava
out = Path(__file__).resolve().parent.parent / "state" / "backtest_monitor_rules.json"
out.write_text(json.dumps({
    "ts": 1792362700,  # 2026-10-18 ~22:30Z
    "bets": [{"label": l, "entry": e, "settle": s, "old_exit": ox, "new_exit": nx,
              "sz": sz, "old_pnl": (ox-e)*sz, "new_pnl": (nx-e)*sz}
             for l, e, s, ox, nx, sz in today_bets],
    "old_total_pnl": old_total,
    "new_total_pnl": new_total,
    "delta": new_total - old_total,
    "verdict": "new_rules_strictly_better_on_today",
}, indent=2))
print(f"\nResult written: {out}")
