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


def _last_reconcile_ts(root: pathlib.Path) -> float | None:
    """Return unix ts of the most recent reconcile line across main.log{,.1}.

    Scan is TIME-BOUNDED, not line-count bounded: walks upward from EOF until
    a timestamp older than SCAN_WINDOW_S is seen, then stops. Rationale: a
    fixed-size tail (say 256KB) can be starved by a 429 burst — thousands of
    error lines evict the last reconcile from the window and the check
    false-escalates on a healthy engine. A time bound cannot be starved: if
    the reconcile is within the window, it's in the scan; if it isn't,
    that's the failure mode we want to fire on.

    Timestamp format: `YYYY-MM-DD HH:MM:SS` at column 0, UTC (system tz is
    UTC, verified 2026-09-25). Returns None if no reconcile line is found
    within the scan window in either file.
    """
    import re
    ts_re = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
    reconcile_re = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[^\n]*reconcile")
    cutoff = time.time() - SCAN_WINDOW_S
    newest: float | None = None

    for name in ("main.log", "main.log.1"):
        p = root / "state" / name
        try:
            size = p.stat().st_size
        except OSError:
            continue
        # Read in 256KB chunks from the tail upward until we see a timestamp
        # older than the scan window. Cap total read at 32MB as a safety belt
        # against pathological cases (clock skew, corrupted timestamps).
        CHUNK = 262_144
        MAX_READ = 32 * 1024 * 1024
        buf = b""
        pos = size
        stop = False
        while pos > 0 and (size - pos) < MAX_READ and not stop:
            read_size = min(CHUNK, pos)
            pos -= read_size
            try:
                with p.open("rb") as f:
                    f.seek(pos)
                    chunk = f.read(read_size)
            except OSError:
                break
            buf = chunk + buf
            # Process complete lines (drop leading partial if we're not at file start)
            lines = buf.splitlines()
            if pos > 0:
                buf = lines[0] if lines else b""
                lines = lines[1:]
            else:
                buf = b""
            # Walk bottom-up: newest match wins; stop when we cross the cutoff
            for line in reversed(lines):
                try:
                    text = line.decode("utf-8", "ignore")
                except (UnicodeDecodeError, AttributeError):
                    continue
                m = reconcile_re.match(text)
                if m:
                    try:
                        ts = time.mktime(time.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"))
                        newest = max(newest or 0.0, ts)
                        stop = True
                        break
                    except (ValueError, OverflowError):
                        continue
                # Time-bound check on ANY timestamped line (not just reconciles)
                any_ts = ts_re.match(text)
                if any_ts:
                    try:
                        ts = time.mktime(time.strptime(any_ts.group(1),
                                                        "%Y-%m-%d %H:%M:%S"))
                        if ts < cutoff:
                            stop = True
                            break
                    except (ValueError, OverflowError):
                        continue
    return newest


# Conditions that a deterministic check can settle on its own. Everything here
# is a known-shape fact, not a judgement -- which is the whole point: the
# operator agent exists for judgement, and ~95% of its runs have none to make.
#
# Idea taken from Ruflo's "Agent Booster / Tier 1" framing (deterministic path,
# $0, escalate only on need). The tiering vocabulary is theirs; the specific
# conditions below are ours, drawn from INVARIANTS.md.
CYCLE_STALE_S = 900   # 3x the observed 303s worst-case gap between reconcile events
SCAN_WINDOW_S = CYCLE_STALE_S * 2  # bound the log scan by time, not line count —
                                   # a 429 burst cannot starve the window


def tier1_check() -> tuple[int, list[str]]:
    """Return (exit_code, reasons). 0 = healthy, no agent needed."""
    reasons: list[str] = []

    active = sh("systemctl is-active hyper-trader") or "unknown"
    if active != "active":
        reasons.append(f"engine {active}")

    n = sh("ps -eo pid,cmd | grep '[s]rc.main' | wc -l")
    if n != "1":
        reasons.append(f"DOUBLE-RUN procs={n}" if n not in ("0", "") else "engine not running")

    if (ROOT / "KILL").exists():
        reasons.append("KILL file present")

    # INV 7: `active` is not proof we trade. A start that aborted after opening
    # the websocket once kept its PID and reported healthy to everything. We
    # need to assert that the engine is CYCLING, not just emitting bytes.
    #
    # 2026-09-25 lesson (two-layer error):
    #   Layer 1 removed: `grep 'Following .* leaders'` matched a STARTUP-only
    #     line. Once logrotate aged out every rotation containing it (~4 days),
    #     the check false-escalated permanently on a healthy engine. Tier1
    #     flipped solid FAIL at 2026-09-24T20:30Z when the last rotation
    #     holding the string was dropped.
    #   Layer 2 removed: file-mtime freshness (`st_mtime > age_s`). Passed as
    #     long as ANY bytes hit main.log — including pure 429-error spew with
    #     zero reconcile cycles completing. 670 tier1 runs, zero freshness
    #     fires: not because the engine was healthy, but because the check
    #     couldn't distinguish "cycling" from "erroring loudly." A guard that
    #     can never fire isn't a guard.
    #
    # Correct assertion: parse the log content for a recent reconcile event.
    # Reconcile fires roughly every 5 min in mirror.py; 900s = 3x that gives
    # ~1.67x headroom over the 9-min p95 measured under current 429 load. If
    # rate limiting worsens the p95 further, this threshold needs revisiting.
    # Empirical: 670 runs at ~5min cadence = ~2.3 days of evidence, all under
    # active 429 conditions.
    #
    # Rotation-safe: search both main.log and main.log.1 (logrotate copytruncate
    # briefly leaves fresh writes in the rotated copy).
    last_cycle_ts = _last_reconcile_ts(ROOT)
    if last_cycle_ts is None:
        reasons.append("no reconcile in main.log{,.1}")
    else:
        age = time.time() - last_cycle_ts
        if age > CYCLE_STALE_S:
            reasons.append(f"reconcile stale: last cycle {age/60:.0f} min ago")

    free = sh("df --output=avail -k / | tail -1")
    try:
        if int(free) < 500_000:                       # <500MB
            reasons.append(f"disk low: {int(free)//1024}MB free")
    except ValueError:
        pass

    # Risk is the one genuinely expensive probe; only run it if all else is fine.
    if not reasons:
        risk = sh(".venv/bin/python scripts/risk_snapshot.py", timeout=120)
        for ln in risk.splitlines():
            if "tier=CRITICAL" in ln:
                coin = ln.split("coin=")[1].split()[0] if "coin=" in ln else "?"
                # Structural, capped-loss isolated HIP-3 books -- not an incident.
                if coin not in ("para:VST", "io:ANTH"):
                    reasons.append(f"CRITICAL liq buffer {coin}")
        if not risk:
            reasons.append("risk_snapshot failed")

    return (1 if reasons else 0), reasons


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--risk", action="store_true", help="include per-position liq buffers")
    ap.add_argument("--check", action="store_true",
                    help="TIER 1: exit 0 if healthy, 1 if an agent is needed. No LLM.")
    ap.add_argument("--hours", type=float, default=6.0)
    args = ap.parse_args()

    if args.check:
        code, reasons = tier1_check()
        if code == 0:
            print("HEALTHY")            # no agent, no model, no tokens
        else:
            print("ESCALATE: " + "; ".join(reasons))
        return code

    # --- engine: the two facts that matter (INV 6, INV 7) -------------------
    active = sh("systemctl is-active hyper-trader") or "unknown"
    n = sh("ps -eo pid,cmd | grep '[s]rc.main' | wc -l") or "?"
    # Rotated logs matter: logrotate truncated main.log on 2026-09-11 and this
    # read went blank, printing "NONE SEEN" for a perfectly healthy engine.
    # Reporting unknown as broken is the mirror of INV 7's "healthy because we
    # cannot see", and just as wrong.
    # Must cover EVERY rotation state: live, rotated, and gzipped. This has now
    # broken twice -- once when logrotate truncated main.log (2026-09-11 19:17)
    # and again an hour later when the rotated copy was compressed to .gz. Both
    # times a healthy engine reported "NONE SEEN", and the tier-1 check uses this
    # same lookup, so it would have false-escalated every 15 minutes.
    following = sh("{ grep -h 'Following .* leaders' state/main.log state/main.log.1 2>/dev/null; "
                   "zgrep -h 'Following .* leaders' state/main.log.*.gz 2>/dev/null; } | tail -1")
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
