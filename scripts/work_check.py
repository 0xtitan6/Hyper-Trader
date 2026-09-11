#!/usr/bin/env python3
"""TIER 1 for the working agents: is there anything to do at all?

Deterministic, no model, no tokens. Exit 0 = nothing to do, skip the agent.
Exit 1 = real work exists, spawn it.

Built 2026-09-11, extending the tier-1 idea (Ruflo's Agent Booster framing) from
the operator to the agents that actually change things. Each answers a factual
question that does NOT need reasoning:

  executor    is the top READY backlog item genuinely undone?
  reviewer    has anything been merged since the last review?
  strategist  has enough new trading happened to re-judge leaders?

The executor check is the important one. For a month it rebuilt the same
already-merged fix ~25 times across 6 branches because finished items were left
marked READY and the only guard was an instruction telling it to look. An
instruction is a request; this is a gate.

    ./scripts/work_check.py executor      # exit 1 if real work waiting
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
STAMPS = ROOT / "state" / "agent_stamps.json"


def sh(cmd: str, timeout: int = 60) -> str:
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                              timeout=timeout, cwd=ROOT).stdout.strip()
    except subprocess.TimeoutExpired:
        return ""


def stamps() -> dict:
    try:
        return json.loads(STAMPS.read_text())
    except Exception:
        return {}


def stamp(agent: str, value: str) -> None:
    d = stamps()
    d[agent] = {"value": value, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    STAMPS.parent.mkdir(parents=True, exist_ok=True)
    STAMPS.write_text(json.dumps(d, indent=2))


def top_ready_item() -> str | None:
    """Title of the first '## READY' heading in BACKLOG.md."""
    try:
        for line in (ROOT / "BACKLOG.md").read_text().splitlines():
            if line.startswith("## READY"):
                return line[3:].strip()
    except OSError:
        pass
    return None


def check_executor() -> tuple[int, str]:
    item = top_ready_item()
    if not item:
        return 0, "no READY item in BACKLOG.md"

    # Does a branch already exist aimed at this item? Two shared topic words is
    # enough of a signal to make a human look before we spend a model on it.
    stop = {"ready", "p0", "p0b", "p0c", "p1", "p2", "p3", "top", "start", "here",
            "the", "a", "we", "our", "and", "not", "is", "to", "of", "for"}
    words = {w for w in re.split(r"[^a-z0-9]+", item.lower()) if len(w) > 3 and w not in stop}
    for b in sh("git branch --list").splitlines():
        b = b.strip().lstrip("+* ")
        if not b or b == "main":
            continue
        bw = {w for w in re.split(r"[^a-z0-9]+", b.lower()) if len(w) > 3}
        if len(words & bw) >= 2:
            return 0, f"branch '{b}' already targets this item — PM must review/merge or mark DONE"

    return 1, f"work waiting: {item[:70]}"


def check_reviewer() -> tuple[int, str]:
    head = sh("git rev-parse HEAD")
    last = stamps().get("reviewer", {}).get("value")
    if head and head == last:
        return 0, f"nothing merged since last review ({head[:8]})"
    n = sh(f"git log --oneline {last}..HEAD 2>/dev/null | wc -l") if last else "?"
    return 1, f"{n} new commit(s) since last review"


def check_strategist() -> tuple[int, str]:
    """Leaders are re-judged on realized fills; no new closes means no new evidence."""
    jp = ROOT / "state" / "journal.jsonl"
    cutoff = time.time() - 24 * 3600
    closes = 0
    if jp.exists():
        with jp.open("rb") as f:
            f.seek(max(0, jp.stat().st_size - 2_000_000))
            for raw in f.read().decode("utf-8", "ignore").splitlines()[1:]:
                try:
                    e = json.loads(raw)
                except ValueError:
                    continue
                if e.get("ts", 0) >= cutoff and e.get("event") == "own_fill":
                    closes += 1
    if closes < 10:
        return 0, f"only {closes} fills in 24h — not enough new evidence to re-judge"
    return 1, f"{closes} fills in 24h"


CHECKS = {"executor": check_executor, "reviewer": check_reviewer, "strategist": check_strategist}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent", choices=sorted(CHECKS))
    ap.add_argument("--stamp", action="store_true", help="record current HEAD as reviewed")
    args = ap.parse_args()

    if args.stamp:
        stamp(args.agent, sh("git rev-parse HEAD"))
        print(f"stamped {args.agent}")
        return 0

    code, why = CHECKS[args.agent]()
    print(("WORK: " if code else "SKIP: ") + why)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
