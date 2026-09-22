#!/usr/bin/env python3
"""Daily market-making report — and a guarantee we are actually deployed.

The 20-minute requote timer can legitimately skip every single cycle (no flow,
no capital, no qualifying surface) and the account then sits idle for a day with
nothing to show it. This runs once a day, reports what is ACTUALLY quoting, and
says plainly when the answer is nothing.

Reports, in order of what matters:
  1. are we quoting right now, and is every pair balanced
  2. fills in the last 24h — the fill rate is the whole strategy and n is tiny
  3. true P&L, netted of deposits (see scripts/equity_snapshot.py)
  4. LP reward status for the last epoch

Read-only except for the alert. Deploying is the requote timer's job; this
reports on it and escalates when it has had nothing to do.
"""
from __future__ import annotations

import collections
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
MASTER = "0xE503186067b1B0Fb973c063054B14c4625434A1a"
HLP = "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303"
INFO = "https://api.hyperliquid.xyz/info"
ENV = "/home/ec2-user/.config/hyper-trader/copytrader.env"
EQUITY = ROOT / "state" / "equity.jsonl"


def post(body: dict, tries: int = 6):
    for k in range(tries):
        try:
            r = requests.post(INFO, json=body, timeout=25)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(1.5 * (k + 1))
    return None


def alert(text: str) -> None:
    try:
        env = dict(l.split("=", 1) for l in Path(ENV).read_text().splitlines()
                   if "=" in l and not l.startswith("#"))
        url, chat = env.get("ALERT_WEBHOOK_URL"), env.get("TELEGRAM_CHAT_ID")
        if url and chat:
            requests.post(url, data={"chat_id": chat, "text": text}, timeout=15)
    except Exception:  # noqa: BLE001 — alerting must never break the report
        pass


def main() -> int:
    now = time.time()
    lines = []
    desc = {o["outcome"]: o.get("description", "")
            for o in (post({"type": "outcomeMeta"}) or {}).get("outcomes", [])}

    # --- 1. what is quoting, and is it balanced -----------------------------
    legs = collections.defaultdict(list)
    for o in post({"type": "openOrders", "user": MASTER}) or []:
        if o["coin"].startswith("#"):
            legs[int(o["coin"][1:-1])].append(
                (int(o["coin"][-1]), float(o["sz"]), float(o["limitPx"])))
    rt_owned: set[int] = set()
    try:
        rt_owned = set(json.loads((ROOT / "state" / "roundtrip_owned.json")
                                  .read_text()).get("outcomes", []))
    except (OSError, ValueError):
        pass

    quoting = 0.0
    unbalanced = []
    for oid, v in sorted(legs.items()):
        cnt = collections.Counter(s for s, _, _ in v)
        sz = {s: sum(z for x, z, _ in v if x == s) for s in cnt}
        px = {s: min(p for x, _, p in v if x == s) for s in cnt}
        d = desc.get(oid, "")
        nm = (d.split("participant:")[1].split("|")[0]
              if "participant:" in d else str(oid))
        cost = sum(sz[s] * px[s] for s in sz)
        quoting += cost
        # A single leg is NOT necessarily broken. The round-trip maker holds
        # one leg on purpose — it buys as maker and offers the SAME leg back as
        # maker, never pairing and never settling. Flagging those as BAD every
        # day trains the operator to ignore this report, which is the whole
        # value of it. Only surfaces the round-trip maker does NOT own must be
        # balanced.
        ok = (len(cnt) == 2 and sz.get(0) == sz.get(1)) or oid in rt_owned
        edge = 1.0 - sum(px.values()) if len(px) == 2 else 0.0
        if not ok:
            unbalanced.append(nm)
        tag = "  OK " if ok else "  BAD"
        if ok and oid in rt_owned and len(cnt) == 1:
            tag = "  RT "                      # round-trip inventory, intended
        lines.append(f"{tag} {nm:<12} "
                     f"{int(min(sz.values()))} sh/leg  ${cost:,.2f}  edge {edge*100:+.2f}%")
    if not legs:
        lines.append("  NOT QUOTING — no resting orders")

    # --- 2. fills in the last 24h ------------------------------------------
    cut = (now - 86400) * 1000
    fills = [f for f in (post({"type": "userFills", "user": MASTER}) or [])
             if f["time"] > cut and f.get("coin", "").startswith("#")]
    maker = [f for f in fills if not f.get("crossed")]
    notional = sum(float(f["sz"]) * float(f["px"]) for f in fills)

    # --- 3. true P&L --------------------------------------------------------
    pnl_txt = "no equity history yet"
    if EQUITY.exists():
        rows = [json.loads(l) for l in EQUITY.read_text().splitlines() if l.strip()]
        if len(rows) >= 2:
            a, b = rows[0], rows[-1]
            pnl = (b["equity"] - a["equity"]) - (b["net_deposits"] - a["net_deposits"])
            hrs = (b["ts"] - a["ts"]) / 3600
            pnl_txt = (f"${pnl:+,.2f} over {hrs:.0f}h "
                       f"(equity ${b['equity']:,.2f}, deposits ${b['net_deposits']:,.2f})")

    # --- 4. rewards ---------------------------------------------------------
    rw = "unreachable"
    try:
        j = requests.get("https://api.monarch.fast/marina/claims/rewards"
                         f"?address={MASTER}",
                         headers={"Origin": "https://monarch.fast"}, timeout=20).json()
        n = len(j.get("rewards") or [])
        rw = (f"{n} entries for {j.get('included_epochs')}"
              if n else f"$0.00 for {j.get('included_epochs')}")
    except Exception:  # noqa: BLE001
        pass

    # --- 5. agent reports filed since the last run ---------------------------
    #
    # The strategist, researcher and rewards crons no longer message the
    # operator directly (2026-09-22, at his instruction: he orchestrates agents,
    # and Quorra is the single interface). They write verdicts to disk; this
    # surfaces anything new so a finding cannot sit unread in a file.
    cutoff = now - 26 * 3600
    filed = []
    for pat in ("state/strategist_verdict_*.md", "research/*.md"):
        for f in sorted(ROOT.glob(pat)):
            try:
                if f.stat().st_mtime > cutoff:
                    first = next((l.strip() for l in f.read_text().splitlines()
                                  if l.strip() and not l.startswith("#")), "")
                    filed.append(f"  {f.relative_to(ROOT)} — {first[:90]}")
            except OSError:
                continue

    head = f"daily MM report {datetime.now(tz=timezone.utc):%Y-%m-%d %H:%M}Z"
    body = "\n".join([
        head,
        f"quoting ${quoting:,.2f} across {sum(len(v) for v in legs.values())} legs:",
        *lines,
        "",
        f"fills 24h: {len(fills)} ({len(maker)} maker) — ${notional:,.2f} notional",
        f"true P&L : {pnl_txt}",
        f"rewards  : {rw}",
        *(["", f"agent reports filed ({len(filed)}):", *filed] if filed else []),
    ])
    print(body)

    # Escalate only when something is wrong or nothing is happening — a normal
    # day where quotes rest untouched is not worth a notification.
    if unbalanced:
        alert(f"UNBALANCED PAIR(S): {', '.join(unbalanced)}\n\n{body}")
        return 2
    if not legs:
        alert(f"NOT MARKET MAKING — nothing resting\n\n{body}")
        return 2
    alert(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
