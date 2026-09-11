#!/usr/bin/env python3
"""Token burn per agent, from the gateway's own cron run history.

Built 2026-09-11. In August the fleet quietly reached 45M tokens/day and hit the
account's session limit -- agents started failing with "you've hit your session
limit" and nobody knew until a run errored. The cost was invisible because it
was spread across four schedules and only ever visible in aggregate.

Reads ~/.openclaw/cron/*.json run history. No API calls, no cost.

    ./scripts/token_usage.py              # last 7 days
    ./scripts/token_usage.py --days 1     # today
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import time

CRON_DIR = pathlib.Path.home() / ".openclaw" / "cron"


def load_runs(cutoff_ms: float):
    """Yield (job_name, tokens, ts) for every run we can find."""
    names, runs = {}, []
    for f in CRON_DIR.rglob("*.json*"):
        try:
            raw = f.read_text()
        except OSError:
            continue
        blobs = []
        try:
            blobs = [json.loads(raw)]
        except ValueError:                       # jsonl
            for line in raw.splitlines():
                try:
                    blobs.append(json.loads(line))
                except ValueError:
                    pass
        for b in blobs:
            for job in (b.get("jobs") or []) if isinstance(b, dict) else []:
                if isinstance(job, dict) and job.get("id"):
                    names[job["id"]] = job.get("name", job["id"][:8])
            entries = b.get("entries") if isinstance(b, dict) else None
            for e in entries or ([b] if isinstance(b, dict) and "jobId" in b else []):
                if not isinstance(e, dict):
                    continue
                u = e.get("usage") or {}
                tok = u.get("total_tokens") or 0
                ts = e.get("ts") or e.get("runAtMs") or 0
                if tok and ts >= cutoff_ms:
                    runs.append((e.get("jobId", "?"), tok, ts))
    return names, runs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=7)
    args = ap.parse_args()
    cutoff = (time.time() - args.days * 86400) * 1000

    names, runs = load_runs(cutoff)
    if not runs:
        print(f"No run history with usage data in the last {args.days:g}d.")
        print(f"(looked in {CRON_DIR})")
        return 0

    by_job = collections.defaultdict(list)
    for jid, tok, _ in runs:
        by_job[jid].append(tok)

    print(f"TOKEN USAGE — last {args.days:g} days")
    print("=" * 74)
    print(f"  {'agent':<30}{'runs':>6}{'total':>14}{'mean/run':>12}{'/day':>11}")
    print("  " + "-" * 70)
    grand = 0
    for jid, toks in sorted(by_job.items(), key=lambda kv: -sum(kv[1])):
        tot = sum(toks)
        grand += tot
        print(f"  {names.get(jid, jid[:28]):<30}{len(toks):>6}{tot:>14,}"
              f"{tot // len(toks):>12,}{int(tot / args.days):>11,}")
    print("  " + "-" * 70)
    print(f"  {'TOTAL':<30}{len(runs):>6}{grand:>14,}{'':>12}{int(grand / args.days):>11,}")

    # The number that actually matters: are we heading for the wall again?
    per_day = grand / args.days
    print()
    print(f"  burn rate: {per_day:,.0f} tokens/day")
    if per_day > 20_000_000:
        print("  !! ABOVE 20M/day — this is the range that hit the account session")
        print("     limit in August. Cut agent frequency before adding projects.")
    elif per_day > 8_000_000:
        print("  ~  elevated. Headroom is shrinking; check before adding a project.")
    else:
        print("  ok  comfortable. Room to add another project's agent.")
    print("\n  NOTE: cron agents only. This session's own usage is not counted here")
    print("        and is usually the largest single consumer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
