#!/usr/bin/env python3
"""One dense health line-set for agents. ONE call instead of ten.

Built 2026-09-11 for token cost. Agent prompts are ~1k tokens; tool OUTPUT is
3-10KB per command -- but an operator pass was costing 248k tokens. The gap is
round trips: every tool call re-sends the whole accumulated transcript, so cost
scales with the NUMBER of calls, not just their size. Ten exploratory commands
re-transmit the conversation ten times.

So this answers, in one call and under ~1KB, everything a health pass needs:
engine, double-run, per-dex risk, recent rejects, account. Designed to be
grep-able and boring -- no prose, no decoration.

    ./scripts/status.py            # health pass
    ./scripts/status.py --risk     # add per-position liq buffers
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent


def sh(cmd: str, timeout: int = 30) -> str:
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                              timeout=timeout, cwd=ROOT).stdout.strip()
    except subprocess.TimeoutExpired:
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--risk", action="store_true", help="include per-position liq buffers")
    ap.add_argument("--hours", type=float, default=6.0)
    args = ap.parse_args()

    # --- engine: the two facts that matter (INV 6, INV 7) -------------------
    active = sh("systemctl is-active hyper-trader") or "unknown"
    n = sh("ps -eo pid,cmd | grep '[s]rc.main' | wc -l") or "?"
    # Rotated logs matter: logrotate truncated main.log on 2026-09-11 and this
    # read went blank, printing "NONE SEEN" for a perfectly healthy engine.
    # Reporting unknown as broken is the mirror of INV 7's "healthy because we
    # cannot see", and just as wrong.
    following = sh("grep -h 'Following .* leaders' state/main.log state/main.log.1 2>/dev/null | tail -1")
    following = following.split("]")[-1].strip() if following else "NONE SEEN"
    flag = "  <<< DOUBLE-RUN" if n not in ("1", "?") else ""
    print(f"ENGINE {active} procs={n}{flag} | {following}")

    # --- account ------------------------------------------------------------
    wins = ROOT / "state" / "wins.log"
    if wins.exists():
        lines = [ln for ln in wins.read_text().splitlines() if ln.strip()]
        if lines:
            d = json.loads(lines[-1])
            print(f"ACCOUNT ${d['total']:.2f} unreal={d.get('unrealized',0):+.2f} "
                  f"to_target=${d.get('to_target',0):.2f} @{d['utc'][5:16]}")

    # --- what got blocked: this bot's dominant failure mode (INV 5) ---------
    cutoff = time.time() - args.hours * 3600
    counts: collections.Counter[str] = collections.Counter()
    jp = ROOT / "state" / "journal.jsonl"
    if jp.exists():
        with jp.open("rb") as f:
            f.seek(max(0, jp.stat().st_size - 400_000))
            for raw in f.read().decode("utf-8", "ignore").splitlines()[1:]:
                try:
                    e = json.loads(raw)
                except ValueError:
                    continue
                if e.get("ts", 0) < cutoff:
                    continue
                ev = e.get("event")
                if ev in ("order_result", "own_fill", "leader_fill"):
                    counts[ev] += 1
                elif ev == "intent_skipped":
                    counts["skip:" + str(e.get("reason"))[:28]] += 1
                elif ev == "risk_check" and e.get("ok") is False:
                    counts["rej:" + str(e.get("reason")).split("(")[0].strip()[:28]] += 1
    if counts:
        print(f"ACTIVITY {args.hours:g}h " + " ".join(f"{k}={v}" for k, v in counts.most_common(8)))
    else:
        print(f"ACTIVITY {args.hours:g}h none")

    # --- errors, minus the two known-benign ones ---------------------------
    errs = sh("grep -c ERROR state/main.log") or "0"
    benign = sh("grep -c -e get_fear_greed_index -e meta_and_asset_ctxs state/main.log") or "0"
    try:
        real = max(0, int(errs) - int(benign))
    except ValueError:
        real = errs
    print(f"ERRORS total={errs} benign={benign} real={real}")

    if args.risk:
        out = sh(".venv/bin/python scripts/risk_snapshot.py", timeout=120)
        for ln in out.splitlines():
            if ln.startswith(("ACCOUNT_HEALTH", "WORST_TIER")) or "tier=CRITICAL" in ln or "tier=WARN" in ln:
                print(ln)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
