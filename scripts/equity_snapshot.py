#!/usr/bin/env python3
"""Record total account equity and TRUE P&L to state/equity.jsonl.

WHY DEPOSITS MUST BE NETTED OUT
-------------------------------
Equity alone lies. On 2026-09-21 the account went from $894 to $2,838 in nine
minutes — entirely because the operator deposited $2,000. A tracker that reports
"equity" as performance would have shown a spectacular fake profit, and the one
number we actually need is the one that can't be faked by moving money in.

    true_pnl = equity_now - equity_start - net_external_flows

Every value below is read live from the exchange. Nothing is cached, nothing is
inferred from a doc, and no position is assumed — dated snapshots in files are
history, never truth.

    ./scripts/equity_snapshot.py           # record + print
    ./scripts/equity_snapshot.py --report  # print the ledger history
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
MASTER = "0xE503186067b1B0Fb973c063054B14c4625434A1a"
HLP = "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303"
INFO = "https://api.hyperliquid.xyz/info"
LEDGER = ROOT / "state" / "equity.jsonl"


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


def external_flows() -> float:
    """Net USDC moved IN from outside the account, all time.

    Deposits and withdrawals are performance-neutral: they change equity without
    anyone having traded. Netting them out is the whole point of this file.

    THREE TRAPS, all hit on 2026-09-21:

    1. A transfer between two Hyperliquid accounts is type `send`, NOT
       `deposit`. The operator moved $1,933.87 in and a deposit-only filter
       reported $0 of it, which would have booked the entire transfer as
       profit.
    2. `send` is directional. The SAME type covers money arriving and money
       leaving; only `destination == MASTER` is incoming. Summing them blindly
       counts withdrawals as deposits.
    3. `accountClassTransfer` (spot<->perp) and `vaultDeposit` (HLP in/out) are
       INTERNAL. The money never left the account, so counting them would
       double-count our own equity.
    4. A `send` with user == destination == us is ALSO internal — it is a
       spot<->dex move, not money arriving. Four such transfers ($277.68) were
       being booked as deposits, understating true P&L by that amount.
    """
    upd = post({"type": "userNonFundingLedgerUpdates", "user": MASTER,
                "startTime": 0}) or []
    me = MASTER.lower()
    net = 0.0
    for u in upd:
        d = u.get("delta", {})
        t = d.get("type", "")
        if t == "deposit":
            net += float(d.get("usdc", 0) or 0)
        elif t == "withdraw":
            net -= float(d.get("usdc", 0) or 0)
        elif t == "send":
            amt = float(d.get("usdcValue") or d.get("amount") or 0)
            src = (d.get("user") or "").lower()
            dst = (d.get("destination") or "").lower()
            if src == me and dst == me:
                continue                        # internal spot<->dex move
            if dst == me:
                net += amt                      # arriving from outside
            elif src == me:
                net -= amt                      # leaving
        # accountClassTransfer / vaultDeposit / vaultWithdraw: internal, ignore
    return net


def realised_and_unrealised(since_ms: int) -> tuple[float, float, float]:
    """(realised closedPnl, fees, unrealised) since a timestamp, across ALL dexes.

    This is the independent check on the equity figure. Equity is a balance
    read; this is a flow read. If they disagree, one of them is wrong and the
    operator must not be told a number that has not reconciled.
    """
    # userFillsByTime, NOT userFills. The latter returns a TRUNCATED window —
    # measured 2026-09-21: exactly 2000 rows, so filtering it by timestamp
    # silently drops anything older than the cap and under-reports realised PnL
    # ($10.98 vs the true $36.23). A reconciliation check that is itself wrong
    # is worse than none, because it manufactures a phantom gap.
    recent = post({"type": "userFillsByTime", "user": MASTER,
                   "startTime": since_ms}) or []
    realised = sum(float(f.get("closedPnl", 0) or 0) for f in recent)
    fees = sum(float(f.get("fee", 0) or 0) for f in recent)
    unreal = 0.0
    for dex in (None, "xyz", "para", "io"):
        q = {"type": "clearinghouseState", "user": MASTER}
        if dex:
            q["dex"] = dex
        c = post(q) or {}
        unreal += sum(float(p["position"]["unrealizedPnl"])
                      for p in c.get("assetPositions", []))
        time.sleep(0.1)
    return realised, fees, unreal


def snapshot() -> dict:
    sp = post({"type": "spotClearinghouseState", "user": MASTER}) or {}
    bal = sp.get("balances", [])
    usdc = next((b for b in bal if b["coin"] == "USDC"), None)
    spot_total = float(usdc["total"]) if usdc else 0.0
    spot_hold = float(usdc["hold"]) if usdc else 0.0

    # Outcome legs held. A COMPLETE basket (both legs, equal size) redeems at
    # exactly $1.00/share regardless of outcome, so it is marked at par. A lone
    # leg is marked at the live bid, because that is all it is worth today.
    legs = {b["coin"]: float(b["total"]) for b in bal
            if b["coin"].startswith("+") and float(b["total"]) > 0}
    legs_value = 0.0
    unpaired = []
    seen = set()
    for coin, sz in legs.items():
        leg = coin.lstrip("+")
        oid, side = leg[:-1], int(leg[-1])
        comp = f"+{oid}{1 - side}"
        if comp in legs:
            if oid not in seen:
                seen.add(oid)
                legs_value += min(sz, legs[comp]) * 1.0        # matched -> par
                extra = abs(sz - legs[comp])
                if extra:
                    unpaired.append((coin if sz > legs[comp] else comp, extra))
        else:
            unpaired.append((coin, sz))
    for coin, sz in unpaired:
        bk = post({"type": "l2Book", "coin": "#" + coin.lstrip("+")})
        lv = (bk or {}).get("levels") or []
        bid = float(lv[0][0]["px"]) if lv and lv[0] else 0.0
        legs_value += sz * bid

    # PER-DEX. HIP-3 builder dexes are SEPARATE clearinghouses holding their own
    # collateral; they never appear in a plain clearinghouseState call. Measured
    # 2026-09-21: after flattening the base perp book this tracker reported
    # equity $2,702.70 while $133.06 sat on the xyz ($114.41) and para ($18.65)
    # dexes — money the operator would have seen simply vanish. This is
    # INVARIANT #1 in INVARIANTS.md and it still caught a tracker written an
    # hour earlier. Never sum a single clearinghouseState and call it the book.
    ch = post({"type": "clearinghouseState", "user": MASTER}) or {}
    ms = ch.get("marginSummary", {})
    perp = float(ms.get("accountValue", 0) or 0)
    per_dex = {}
    for dex in ("xyz", "para", "io"):
        d = post({"type": "clearinghouseState", "user": MASTER, "dex": dex})
        v = float(((d or {}).get("marginSummary") or {}).get("accountValue", 0) or 0)
        if v:
            per_dex[dex] = round(v, 2)
        time.sleep(0.1)
    perp += sum(per_dex.values())
    upnl = sum(float(p["position"]["unrealizedPnl"])
               for p in ch.get("assetPositions", []))
    maint = float(ch.get("crossMaintenanceMarginUsed", 0) or 0)

    vd = post({"type": "vaultDetails", "vaultAddress": HLP, "user": MASTER}) or {}
    vault = float((vd.get("followerState") or {}).get("vaultEquity", 0) or 0)

    oo = post({"type": "openOrders", "user": MASTER}) or []
    resting = sum(float(o["sz"]) * float(o["limitPx"])
                  for o in oo if o["coin"].startswith("#"))

    # spot_total already includes USDC backing resting orders (it is `hold`),
    # so equity = spot USDC + outcome legs + perp + vault. Resting is reported
    # for visibility, NOT added, or it would double-count.
    equity = spot_total + legs_value + perp + vault
    return {
        "ts": time.time(),
        "iso": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "equity": round(equity, 2),
        "spot_usdc": round(spot_total, 2),
        "spot_free": round(spot_total - spot_hold, 2),
        "outcome_legs": round(legs_value, 2),
        "perp": round(perp, 2),
        "perp_by_dex": per_dex,
        "perp_upnl": round(upnl, 2),
        "perp_maint_pct": round(maint / perp * 100, 1) if perp else 0.0,
        "vault": round(vault, 2),
        "resting_orders": round(resting, 2),
        "n_orders": len([o for o in oo if o["coin"].startswith("#")]),
        "net_deposits": round(external_flows(), 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    if args.report:
        if not LEDGER.exists():
            print("no history yet")
            return 1
        rows = [json.loads(l) for l in LEDGER.read_text().splitlines() if l.strip()]
        first = rows[0]
        print(f"{'when':<20}{'equity':>10}{'deposits':>10}{'TRUE P&L':>11}{'free':>9}{'orders':>7}")
        for r in rows:
            pnl = (r["equity"] - first["equity"]) - (r["net_deposits"] - first["net_deposits"])
            print(f"{r['iso'][:19]:<20}{r['equity']:>10,.2f}{r['net_deposits']:>10,.0f}"
                  f"{pnl:>+11.2f}{r['spot_free']:>9,.0f}{r['n_orders']:>7}")
        return 0

    s = snapshot()
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    prev = None
    if LEDGER.exists():
        lines = [l for l in LEDGER.read_text().splitlines() if l.strip()]
        if lines:
            prev = json.loads(lines[0])            # baseline = first row
    with LEDGER.open("a") as f:
        f.write(json.dumps(s) + "\n")

    print(f"equity        ${s['equity']:>10,.2f}")
    print(f"  spot USDC   ${s['spot_usdc']:>10,.2f}   (free ${s['spot_free']:,.2f})")
    print(f"  outcome legs${s['outcome_legs']:>10,.2f}")
    print(f"  perp        ${s['perp']:>10,.2f}   (upnl {s['perp_upnl']:+.2f}, maint {s['perp_maint_pct']}%)")
    if s["perp_by_dex"]:
        print(f"    per-dex   {s['perp_by_dex']}")
    print(f"  HLP vault   ${s['vault']:>10,.2f}")
    print(f"quoting       ${s['resting_orders']:>10,.2f} across {s['n_orders']} legs")
    print(f"net deposits  ${s['net_deposits']:>10,.2f}")
    if prev:
        pnl = (s["equity"] - prev["equity"]) - (s["net_deposits"] - prev["net_deposits"])
        hrs = (s["ts"] - prev["ts"]) / 3600
        print(f"\nTRUE P&L since {prev['iso'][:16]} ({hrs:.1f}h): ${pnl:+,.2f}")
        print("  (equity change with deposits/withdrawals removed)")

        # RECONCILE against the flow record. Equity is a balance read; fills are
        # a flow read. They must agree, and on 2026-09-21 they did not — equity
        # claimed +$91.81 while fills and unrealised justified only +$42.87, a
        # $48.94 gap with no matching ledger transfer. The cause is still
        # unidentified (suspected double-count of perp collateral against the
        # unified spot balance). Until it is found, the tracker must SAY SO
        # rather than print a confident wrong number — an unreconciled P&L is
        # more dangerous than no P&L, because it gets believed.
        realised, fees, unreal = realised_and_unrealised(int(prev["ts"] * 1000))
        explained = realised - fees + unreal
        gap = pnl - explained
        print(f"  reconcile: realised {realised:+,.2f} - fees {fees:,.2f} "
              f"+ unrealised {unreal:+,.2f} = {explained:+,.2f}")
        if abs(gap) > max(2.0, abs(explained) * 0.05):
            print(f"  *** UNRECONCILED: ${gap:+,.2f} unexplained — "
                  f"TREAT ${explained:+,.2f} AS THE REAL NUMBER ***")
        else:
            print(f"  reconciled (gap ${gap:+,.2f})")
    else:
        print("\nbaseline recorded — P&L measured from here")
    return 0


if __name__ == "__main__":
    sys.exit(main())
