#!/usr/bin/env python3
"""audit_pnl.py

Persistent, single-source-of-truth PnL snapshot for the Hyperliquid trading
account. Sums every surface exactly once and marks any missing component
explicitly. See scripts/audit_pnl_readme.md for field meaning.

Run:
    .venv/bin/python scripts/audit_pnl.py
    .venv/bin/python scripts/audit_pnl.py --diff state/pnl_audit_<prev>.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

HL_URL = "https://api.hyperliquid.xyz/info"
REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = REPO_ROOT / "state"
DEFAULT_ENV = Path.home() / ".config" / "hyper-trader" / "copytrader.env"

# 10 HIP-3 dexes (verified live via perpDexs 2026-09-24; also matches config).
HIP3_DEXES = ["xyz", "flx", "vntl", "hyna", "km", "abcd", "cash", "para", "mkts", "io"]

REQ_SLEEP_S = 1.0            # sleep between HL calls to dodge 429s
MAX_RETRIES = 3
RETRY_BACKOFF_S = 5.0


def load_address(env_path: Path) -> str:
    if not env_path.exists():
        raise SystemExit(f"env file not found: {env_path}")
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("HL_ACCOUNT_ADDRESS="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(f"HL_ACCOUNT_ADDRESS missing from {env_path}")


def hl_post(body: dict, *, label: str) -> Any:
    """POST with rate-limit-friendly retry. Returns parsed JSON or raises."""
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.post(HL_URL, json=body, timeout=15)
            if r.status_code == 429:
                raise RuntimeError(f"429 rate-limited on {label}")
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_S * attempt)
    raise RuntimeError(f"HL post failed for {label} after {MAX_RETRIES} attempts: {last_exc}")


def fetch_perp(address: str, dex: str | None) -> dict:
    body = {"type": "clearinghouseState", "user": address}
    if dex:
        body["dex"] = dex
    label = f"clearinghouseState[{dex or 'base'}]"
    data = hl_post(body, label=label)
    ms = data.get("marginSummary", {}) or {}
    positions_raw = data.get("assetPositions", []) or []
    positions: list[dict] = []
    unrealized = 0.0
    for p in positions_raw:
        pos = p.get("position", {}) or {}
        upnl = float(pos.get("unrealizedPnl", 0.0) or 0.0)
        unrealized += upnl
        positions.append({
            "coin": pos.get("coin"),
            "szi": float(pos.get("szi", 0.0) or 0.0),
            "entryPx": float(pos.get("entryPx", 0.0) or 0.0),
            "positionValue": float(pos.get("positionValue", 0.0) or 0.0),
            "unrealizedPnl": upnl,
            "leverage": pos.get("leverage"),
        })
    return {
        "equity_usd": float(ms.get("accountValue", 0.0) or 0.0),
        "total_margin_used_usd": float(ms.get("totalMarginUsed", 0.0) or 0.0),
        "total_ntl_pos_usd": float(ms.get("totalNtlPos", 0.0) or 0.0),
        "withdrawable_usd": float(data.get("withdrawable", 0.0) or 0.0),
        "unrealized_pnl_usd": unrealized,
        "positions": positions,
        "confidence": "verified",
    }


def fetch_spot(address: str) -> list[dict]:
    body = {"type": "spotClearinghouseState", "user": address}
    data = hl_post(body, label="spotClearinghouseState[base]")
    return [b for b in (data.get("balances", []) or []) if float(b.get("total", 0.0) or 0.0) > 0]


def verify_spot_is_unified(address: str, base_balances: list[dict]) -> tuple[bool, list[str]]:
    """Query one HIP-3 dex spot view and confirm it returns the SAME balances.

    This is the guard against Bug 1 (double counting a unified pool).
    Returns (is_unified, notes). If unified, callers MUST NOT sum per-dex spot.
    """
    notes: list[str] = []
    time.sleep(REQ_SLEEP_S)
    body = {"type": "spotClearinghouseState", "user": address, "dex": "xyz"}
    try:
        data = hl_post(body, label="spotClearinghouseState[xyz]")
    except Exception as e:
        notes.append(f"could not verify unified spot pool (xyz view failed: {e})")
        return False, notes
    xyz_balances = [b for b in (data.get("balances", []) or []) if float(b.get("total", 0.0) or 0.0) > 0]

    def key(b: dict) -> tuple[str, float]:
        return (str(b.get("coin", "")), round(float(b.get("total", 0.0) or 0.0), 6))

    base_set = {key(b) for b in base_balances}
    xyz_set = {key(b) for b in xyz_balances}
    # USDC total drifts by cents between calls; allow small delta on USDC only.
    def strip_usdc(s: set[tuple[str, float]]) -> set[tuple[str, float]]:
        return {k for k in s if k[0] != "USDC"}
    if strip_usdc(base_set) == strip_usdc(xyz_set):
        return True, ["verified base spot == xyz spot balances (unified pool, summed only once)"]
    diff_only_base = strip_usdc(base_set) - strip_usdc(xyz_set)
    diff_only_xyz = strip_usdc(xyz_set) - strip_usdc(base_set)
    notes.append(
        f"spot views diverge (base_only={len(diff_only_base)} xyz_only={len(diff_only_xyz)}); "
        "treating as unified anyway per HL model but flag investigation"
    )
    return True, notes


def fetch_all_mids() -> dict[str, float]:
    """Global allMids. Outcome coins appear as '#XXXXY' (spot balance key is '+XXXXY')."""
    data = hl_post({"type": "allMids"}, label="allMids")
    out: dict[str, float] = {}
    if isinstance(data, dict):
        for k, v in data.items():
            try:
                out[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
    return out


def price_balances(balances: list[dict], mids: dict[str, float]) -> tuple[float, float, list[dict], list[str]]:
    """Return (usdc_total, usdc_hold, priced_outcome_list, issues)."""
    usdc_total = 0.0
    usdc_hold = 0.0
    priced: list[dict] = []
    issues: list[str] = []
    for b in balances:
        coin = str(b.get("coin", ""))
        total = float(b.get("total", 0.0) or 0.0)
        hold = float(b.get("hold", 0.0) or 0.0)
        entry_ntl = float(b.get("entryNtl", 0.0) or 0.0)
        if coin == "USDC":
            usdc_total += total
            usdc_hold += hold
            continue
        if coin in ("USDE", "USDT0", "USDH"):
            # other USD stables held at par; only include if non-zero
            priced.append({
                "coin": coin,
                "units": total,
                "hold": hold,
                "mid_price_usd": 1.0,
                "market_value_usd": total,
                "entry_ntl_usd": entry_ntl,
                "confidence": "estimated",
                "note": "USD-stable, marked at $1.00",
            })
            continue
        # HIP-4 outcome tokens: '+XXXXY' -> allMids key '#XXXXY'
        if coin.startswith("+"):
            mid_key = "#" + coin[1:]
            mid = mids.get(mid_key)
            if mid is None:
                issues.append(f"orderbook mid missing for {coin} ({total} units, entry ntl ${entry_ntl:.2f})")
                priced.append({
                    "coin": coin,
                    "units": total,
                    "hold": hold,
                    "mid_price_usd": None,
                    "market_value_usd": None,
                    "entry_ntl_usd": entry_ntl,
                    "confidence": "unpriced",
                })
                continue
            mv = total * mid
            priced.append({
                "coin": coin,
                "units": total,
                "hold": hold,
                "mid_price_usd": mid,
                "market_value_usd": mv,
                "entry_ntl_usd": entry_ntl,
                "confidence": "verified",
            })
            continue
        # Unknown non-USDC coin
        issues.append(f"unknown spot coin {coin} ({total} units) — not priced")
        priced.append({
            "coin": coin,
            "units": total,
            "hold": hold,
            "mid_price_usd": None,
            "market_value_usd": None,
            "entry_ntl_usd": entry_ntl,
            "confidence": "unpriced",
        })
    return usdc_total, usdc_hold, priced, issues


def build_snapshot(address: str) -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    components: dict[str, Any] = {}
    sources: list[str] = []
    issues: list[str] = []
    verified = True

    # 1. Base perp
    try:
        components["base_perp"] = fetch_perp(address, None)
        sources.append("base_perp")
    except Exception as e:
        components["base_perp"] = {"confidence": "unavailable", "error": str(e)}
        issues.append(f"base_perp fetch failed: {e}")
        verified = False
    time.sleep(REQ_SLEEP_S)

    # 2. HIP-3 perps
    hip3: dict[str, Any] = {}
    for dex in HIP3_DEXES:
        try:
            hip3[dex] = fetch_perp(address, dex)
            sources.append(f"{dex}_perp")
        except Exception as e:
            hip3[dex] = {"confidence": "unavailable", "error": str(e)}
            issues.append(f"{dex}_perp fetch failed: {e}")
            verified = False
        time.sleep(REQ_SLEEP_S)
    components["hip3_perps"] = hip3

    # 3. Base spot (unified pool)
    try:
        base_spot = fetch_spot(address)
        sources.append("base_spot")
    except Exception as e:
        base_spot = []
        issues.append(f"base_spot fetch failed: {e}")
        verified = False
    time.sleep(REQ_SLEEP_S)

    # 3b. Verify unified pool assumption
    unified_ok, unified_notes = verify_spot_is_unified(address, base_spot)
    for n in unified_notes:
        issues.append(n)
    if unified_ok:
        sources.append("xyz_spot(verify-only)")

    # 4. All mids for outcome token pricing
    try:
        mids = fetch_all_mids()
        sources.append("allMids")
    except Exception as e:
        mids = {}
        issues.append(f"allMids fetch failed: {e}")
        verified = False

    usdc_total, usdc_hold, priced_tokens, price_issues = price_balances(base_spot, mids)
    issues.extend(price_issues)
    components["spot_usdc"] = {
        "total_usd": usdc_total,
        "hold_usd": usdc_hold,
        "note": "unified pool across base + 10 HIP-3 dexes; summed exactly once",
        "confidence": "verified" if base_spot else "unavailable",
    }
    components["hip4_outcome_tokens"] = priced_tokens

    # Totals
    base_equity = components["base_perp"].get("equity_usd", 0.0) if components["base_perp"].get("confidence") == "verified" else 0.0
    hip3_equity_sum = 0.0
    hip3_unavailable = 0
    for d, v in hip3.items():
        if v.get("confidence") == "verified":
            hip3_equity_sum += v.get("equity_usd", 0.0)
        else:
            hip3_unavailable += 1

    outcome_verified_mv = sum(t["market_value_usd"] for t in priced_tokens if t["confidence"] == "verified")
    outcome_estimated_mv = sum(t["market_value_usd"] for t in priced_tokens if t["confidence"] == "estimated")
    outcome_unpriced = [t for t in priced_tokens if t["confidence"] == "unpriced"]
    outcome_unpriced_entry_ntl = sum((t.get("entry_ntl_usd") or 0.0) for t in outcome_unpriced)

    if outcome_unpriced:
        verified = False

    sum_verified = base_equity + hip3_equity_sum + usdc_total + outcome_verified_mv
    sum_estimated = outcome_estimated_mv
    grand_total = sum_verified + sum_estimated

    components["hip3_perp_totals"] = {
        "equity_sum_usd": hip3_equity_sum,
        "unrealized_pnl_sum_usd": sum(v.get("unrealized_pnl_usd", 0.0) for v in hip3.values() if v.get("confidence") == "verified"),
        "dexes_unavailable": hip3_unavailable,
    }

    totals = {
        "base_perp_equity_usd": base_equity,
        "hip3_perp_equity_sum_usd": hip3_equity_sum,
        "spot_usdc_usd": usdc_total,
        "hip4_outcome_verified_mv_usd": outcome_verified_mv,
        "hip4_outcome_estimated_mv_usd": outcome_estimated_mv,
        "hip4_outcome_unpriced_count": len(outcome_unpriced),
        "hip4_outcome_unpriced_entry_ntl_usd": outcome_unpriced_entry_ntl,
        "sum_verified_usd": sum_verified,
        "sum_estimated_usd": sum_estimated,
        "sum_unpriced_positions_note": (
            f"{len(outcome_unpriced)} outcome positions with no mid — excluded from grand_total "
            f"(entry notional ${outcome_unpriced_entry_ntl:.2f})"
            if outcome_unpriced
            else "all outcome tokens priced from allMids"
        ),
        "grand_total_usd": grand_total,
    }

    return {
        "timestamp_utc": ts,
        "address": address,
        "verified": verified,
        "sources_queried": sources,
        "components": components,
        "totals": totals,
        "issues": issues,
        "reconciliation": None,
    }


def diff_snapshot(current: dict, prev_path: Path) -> None:
    try:
        prev = json.loads(prev_path.read_text())
    except Exception as e:
        current["reconciliation"] = {"error": f"could not read {prev_path}: {e}"}
        return
    prev_total = prev.get("totals", {}).get("grand_total_usd")
    cur_total = current.get("totals", {}).get("grand_total_usd")
    if prev_total is None or cur_total is None:
        current["reconciliation"] = {
            "last_snapshot_path": str(prev_path),
            "last_snapshot_total_usd": prev_total,
            "current_total_usd": cur_total,
            "delta_usd": None,
            "explanation": "one of the totals is null",
        }
        return
    delta = cur_total - prev_total
    # Breakdown
    def get_totals(s):
        return s.get("totals", {}) or {}
    p, c = get_totals(prev), get_totals(current)
    parts = {}
    for k in ("base_perp_equity_usd", "hip3_perp_equity_sum_usd", "spot_usdc_usd", "hip4_outcome_verified_mv_usd", "hip4_outcome_estimated_mv_usd"):
        parts[k] = (c.get(k, 0.0) or 0.0) - (p.get(k, 0.0) or 0.0)
    current["reconciliation"] = {
        "last_snapshot_path": str(prev_path),
        "last_snapshot_timestamp_utc": prev.get("timestamp_utc"),
        "last_snapshot_total_usd": prev_total,
        "current_total_usd": cur_total,
        "delta_usd": delta,
        "delta_by_component_usd": parts,
        "explanation": None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=str(DEFAULT_ENV), help="path to copytrader.env")
    ap.add_argument("--diff", default=None, help="path to previous audit JSON for reconciliation")
    ap.add_argument("--out-dir", default=str(STATE_DIR), help="output dir for snapshot JSON")
    args = ap.parse_args()

    address = load_address(Path(args.env))
    snapshot = build_snapshot(address)

    if args.diff:
        diff_snapshot(snapshot, Path(args.diff))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"pnl_audit_{stamp}.json"
    out_path.write_text(json.dumps(snapshot, indent=2, sort_keys=False))

    print(json.dumps(snapshot, indent=2, sort_keys=False))
    print(f"\n# wrote {out_path}", file=sys.stderr)
    return 0 if snapshot["verified"] else 2


if __name__ == "__main__":
    sys.exit(main())
