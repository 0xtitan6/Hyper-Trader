#!/usr/bin/env python3
"""daily_mm_report.py

Once-a-day market-making + copy-trade report. Uses equity_snapshot.jsonl as
its truth series (24h ago vs now) and reads state/journal.jsonl for a
maker/copy activity roll-up.

Writes state/mm_report_YYYYMMDD.md. Read-only against HL.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from audit_pnl import DEFAULT_ENV, STATE_DIR, build_snapshot, load_address

REPO_ROOT = SCRIPT_DIR.parent
JOURNAL = REPO_ROOT / "state" / "journal.jsonl"
EQUITY_JSONL = REPO_ROOT / "state" / "equity_snapshot.jsonl"


def load_equity_series() -> list[dict]:
    if not EQUITY_JSONL.exists():
        return []
    rows: list[dict] = []
    for line in EQUITY_JSONL.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def summarize_journal(hours: int = 24) -> dict:
    if not JOURNAL.exists():
        return {"note": "journal.jsonl not found"}
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp()
    counts: dict[str, int] = {}
    own_fills: list[dict] = []
    realized = 0.0
    for line in JOURNAL.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = row.get("ts") or row.get("timestamp")
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            except ValueError:
                continue
        if not isinstance(ts, (int, float)) or ts < cutoff:
            continue
        evt = row.get("event") or row.get("type") or "unknown"
        counts[evt] = counts.get(evt, 0) + 1
        if evt in ("own_fill", "fill"):
            own_fills.append(row)
            realized += float(row.get("closed_pnl", 0.0) or 0.0)
    return {
        "hours": hours,
        "event_counts": counts,
        "own_fill_count": len(own_fills),
        "realized_pnl_usd": realized,
        "last_own_fill_tid": (own_fills[-1].get("tid") if own_fills else None),
    }


def build_report(env_path: Path) -> str:
    address = load_address(env_path)
    now = datetime.now(timezone.utc)
    snap = build_snapshot(address)
    series = load_equity_series()
    prev = None
    if series:
        cutoff = now - timedelta(hours=24)
        older = [r for r in series if r.get("ts") and datetime.fromisoformat(r["ts"]).astimezone(timezone.utc) <= cutoff]
        prev = older[-1] if older else series[0]
    j = summarize_journal(24)

    grand = snap["totals"]["grand_total_usd"]
    prev_grand = prev.get("grand_total_usd") if prev else None
    delta = (grand - prev_grand) if prev_grand is not None else None

    deployed = snap["totals"]["hip3_perp_equity_sum_usd"] > 0 or snap["totals"]["hip4_outcome_verified_mv_usd"] > 0
    lines: list[str] = []
    lines.append(f"# MM Report — {now.strftime('%Y-%m-%d %H:%MZ')}")
    lines.append("")
    lines.append(f"**Deployed:** {'YES' if deployed else 'NO — capital idle'}")
    lines.append(f"**Verified snapshot:** {snap['verified']}")
    lines.append("")
    lines.append("## Equity")
    lines.append(f"- Now: **${grand:,.2f}**")
    if prev_grand is not None:
        lines.append(f"- 24h ago: ${prev_grand:,.2f}")
        lines.append(f"- Delta: **${delta:+,.2f}**")
    else:
        lines.append("- No prior snapshot in equity_snapshot.jsonl (first run?)")
    lines.append("")
    lines.append("## Breakdown")
    t = snap["totals"]
    lines.append(f"- Base perp equity: ${t['base_perp_equity_usd']:,.2f}")
    lines.append(f"- HIP-3 perp equity (10 dex sum): ${t['hip3_perp_equity_sum_usd']:,.2f}")
    lines.append(f"- Spot USDC: ${t['spot_usdc_usd']:,.2f}")
    lines.append(f"- HIP-4 outcome MV (verified): ${t['hip4_outcome_verified_mv_usd']:,.2f}")
    if t["hip4_outcome_estimated_mv_usd"]:
        lines.append(f"- HIP-4 outcome MV (estimated): ${t['hip4_outcome_estimated_mv_usd']:,.2f}")
    if t["hip4_outcome_unpriced_count"]:
        lines.append(
            f"- HIP-4 unpriced: {t['hip4_outcome_unpriced_count']} positions "
            f"(entry ntl ${t['hip4_outcome_unpriced_entry_ntl_usd']:.2f})"
        )
    lines.append("")
    lines.append("## Last 24h activity")
    if isinstance(j.get("event_counts"), dict):
        top = sorted(j["event_counts"].items(), key=lambda kv: -kv[1])[:8]
        lines.append(f"- own_fills: {j['own_fill_count']}")
        lines.append(f"- realized PnL from fills: ${j['realized_pnl_usd']:+,.2f}")
        lines.append(f"- last own_fill tid: {j['last_own_fill_tid']}")
        lines.append("- event counts (top 8):")
        for evt, n in top:
            lines.append(f"    - {evt}: {n}")
    else:
        lines.append(f"- {j.get('note', 'no journal data')}")
    lines.append("")
    if snap.get("issues"):
        lines.append("## Issues flagged this snapshot")
        for issue in snap["issues"][:10]:
            lines.append(f"- {issue}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=str(DEFAULT_ENV))
    ap.add_argument("--out-dir", default=str(STATE_DIR))
    args = ap.parse_args()
    report = build_report(Path(args.env))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = out_dir / f"mm_report_{stamp}.md"
    out_path.write_text(report)
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
