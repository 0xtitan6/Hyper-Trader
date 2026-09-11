#!/usr/bin/env python3
"""What have the agents actually been DOING?

Built 2026-09-11 after the executor rebuilt the same fix ~25 times across 6
branches over a month without anyone noticing. Every individual run reported
success -- branch created, tests green, report sent -- so nothing alerted. The
failure was only visible ACROSS runs, and nothing looked across runs.

This reconstructs agent activity from evidence that already exists (git history,
worktrees, branch names) rather than requiring agents to self-report, so it
works retroactively and cannot be fooled by an agent that thinks it succeeded.

    ./scripts/agent_audit.py            # last 14 days
    ./scripts/agent_audit.py --days 30
"""
from __future__ import annotations

import argparse
import collections
import re
import subprocess


def sh(cmd: str) -> str:
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()


# Branch prefixes that mean "an agent tried to solve a problem". Grouping by the
# SUBJECT (what comes after the prefix) is what surfaces repeated attempts.
_STOPWORDS = {"fix", "feat", "chore", "docs", "exec", "wip", "and", "the", "for", "to"}


def subject(branch: str) -> frozenset[str]:
    """Topic words in a branch name, for detecting two branches at one problem."""
    tail = branch.split("/", 1)[-1]
    return frozenset(w for w in re.split(r"[-_]", tail.lower()) if w and w not in _STOPWORDS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    args = ap.parse_args()
    since = f"--since={args.days}.days"

    print(f"AGENT AUDIT — last {args.days} days")
    print("=" * 78)

    # Who is committing, and how much of it reached main?
    print("\nCOMMITS BY AGENT (on main)")
    authors = collections.Counter()
    for line in sh(f'git log {since} --format="%s" origin/main').splitlines():
        tag = line.split(":", 1)[0].strip().lower() if ":" in line else "other"
        authors[tag] += 1
    for tag, n in authors.most_common(10):
        print(f"   {tag:<28} {n}")
    if not authors:
        print("   (none)")

    # The thing that was invisible: many branches aimed at ONE problem.
    print("\nREPEATED WORK  (branches whose topics overlap — the 25x failure mode)")
    branches = [b.strip().lstrip("+* ") for b in sh("git branch --list").splitlines()]
    branches = [b for b in branches if b and b != "main"]
    groups: list[tuple[frozenset[str], list[str]]] = []
    for b in branches:
        s = subject(b)
        for i, (key, members) in enumerate(groups):
            if len(s & key) >= 2:                      # two shared topic words
                groups[i] = (key & s or key, members + [b])
                break
        else:
            groups.append((s, [b]))
    dupes = [(k, m) for k, m in groups if len(m) > 1]
    if dupes:
        for key, members in dupes:
            print(f"   !! {len(members)} branches share topic {sorted(key)}:")
            for b in members:
                print(f"        {b}")
        print("   -> check the backlog: an item is probably still READY after being merged")
    else:
        print("   none — no overlapping branch topics")

    # Work that was produced and never landed is work that was wasted.
    print("\nUNMERGED BRANCHES  (produced, never landed)")
    unmerged = [b.strip().lstrip("+* ") for b in sh("git branch --no-merged main").splitlines() if b.strip()]
    for b in unmerged:
        age = sh(f'git log -1 --format="%ar" {b}')
        print(f"   {b:<52} {age}")
    if not unmerged:
        print("   none")

    # Stale worktrees are abandoned agent runs.
    print("\nWORKTREES")
    for line in sh("git worktree list").splitlines():
        flag = "  <- prunable" if "prunable" in line else ""
        print(f"   {line}{flag}")

    print("\nBACKLOG SANITY")
    ready = sh("grep -c '^## READY' BACKLOG.md") or "0"
    done_no_sha = sh("grep '^## DONE' BACKLOG.md | grep -vci 'merge\\|[0-9a-f]\\{7\\}'") or "0"
    print(f"   READY items: {ready}")
    print(f"   DONE items missing a merge SHA: {done_no_sha}   (rule: DONE needs proof)")
    print("\n" + "=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
