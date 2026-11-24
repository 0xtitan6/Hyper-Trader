#!/usr/bin/env python3
"""Sally: static invariant assertions on config.yaml.

Runs in pure config-parse mode. No network, no HL API, no subprocess, no
filesystem beyond reading config.yaml. This is deliberate — the check is
meant to be safe to run as an ExecStartPre gate on the live engine, which
means it must not depend on any environmental state. A failure here must
mean the config is wrong, never that HL had a bad minute.

Exit contract matches preflight_deploy.sh:
  - print `ok` / `FAIL` lines per check
  - exit 0 if all pass, non-zero (count of failures) if any fail

Invariants asserted (all drawn from INVARIANTS.md):

  #12 SIZING: for every leader in leader_weights, fixed_usd * weight
      (floor-rounded to cent) MUST clear min_per_trade_usd. Otherwise the
      leader is silently muted — every intent it generates rounds below the
      min-order threshold and gets skipped with no error surfaced.

  #5  ZERO-CAP-IS-KILL: no risk cap may be exactly 0. max_daily_loss_usd,
      max_dex_exposure_usd, max_total_exposure_usd. A cap of zero silently
      disables the whole surface it protects (or blocks all trading through
      it) with no error surfaced — that's a silent kill switch masquerading
      as a config value.

  #2  PER-CLEARINGHOUSE CAP: max_dex_exposure_usd must be PRESENT (each
      HIP-3 dex has its own collateral pool; a shared cap charges an xyz:*
      order for risk carried on base account).

Allowed imports: yaml, sys, pathlib, math. Nothing else.
"""

from __future__ import annotations

import math
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _fmt_ok(msg: str) -> str:
    return f"ok    {msg}"


def _fmt_fail(msg: str) -> str:
    return f"FAIL  {msg}"


def check_leader_weights_not_muted(cfg: dict) -> list[str]:
    """INV #12: fixed_usd * weight must clear min_per_trade_usd for every leader.

    If not, the leader is silently muted — clips round below the min-order
    threshold and get skipped without ever surfacing an error. 15 hand-written
    comments in config.yaml document this check case-by-case; they all go stale
    the moment fixed_usd moves off 30. This asserts it mechanically.
    """
    results: list[str] = []
    sizing = cfg.get("sizing", {})
    discovery = cfg.get("discovery", {})
    fixed = sizing.get("fixed_usd")
    min_per = sizing.get("min_per_trade_usd")
    if fixed is None or min_per is None:
        results.append(
            _fmt_fail(
                f"sizing.fixed_usd={fixed} sizing.min_per_trade_usd={min_per} (both required)"
            )
        )
        return results
    weights = discovery.get("leader_weights") or {}
    if not weights:
        results.append(_fmt_fail("discovery.leader_weights empty or missing"))
        return results
    for addr, weight in weights.items():
        try:
            w = float(weight)
        except (TypeError, ValueError):
            results.append(_fmt_fail(f"leader {addr[:12]}... has non-numeric weight={weight!r}"))
            continue
        # Floor to cent, matching what a real order-sizer would do
        clip = math.floor(float(fixed) * w * 100) / 100
        if clip < float(min_per):
            results.append(
                _fmt_fail(
                    f"leader {addr[:12]}... MUTED: fixed_usd={fixed} * weight={w} "
                    f"= ${clip:.2f} clip < min_per_trade_usd=${min_per}"
                )
            )
        else:
            results.append(
                _fmt_ok(
                    f"leader {addr[:12]}... clip ${clip:.2f} clears min_per_trade_usd ${min_per}"
                )
            )
    return results


def check_no_zero_caps(cfg: dict) -> list[str]:
    """INV #5: no risk cap may be exactly 0 — that's a silent kill switch.

    A cap of 0 either blocks all trading through the surface it protects
    (looks like an outage with no error) or silently disables it (looks
    like a stealth authorization). Both are silent-behavior-change failures
    — the exact class the invariants exist to prevent.
    """
    results: list[str] = []
    risk = cfg.get("risk", {})
    caps = [
        "max_daily_loss_usd",
        "max_dex_exposure_usd",
        "max_total_exposure_usd",
    ]
    for name in caps:
        val = risk.get(name)
        if val is None:
            # Absence is handled separately in the per-clearinghouse check;
            # here we're only guarding against explicit zeros.
            results.append(_fmt_ok(f"risk.{name} not set (falls back to defaults)"))
            continue
        try:
            v = float(val)
        except (TypeError, ValueError):
            results.append(_fmt_fail(f"risk.{name} has non-numeric value={val!r}"))
            continue
        if v == 0:
            results.append(
                _fmt_fail(
                    f"risk.{name}=0 — silent kill switch. A cap of zero disables "
                    f"the surface it protects with no error."
                )
            )
        else:
            results.append(_fmt_ok(f"risk.{name}={v} non-zero"))
    return results


def check_per_clearinghouse_cap_present(cfg: dict) -> list[str]:
    """INV #2: max_dex_exposure_usd MUST be present (per-clearinghouse).

    Each HIP-3 dex settles against its own collateral. A shared cap charges
    xyz:* orders for risk carried on the base account, which blocked 40/40
    xyz opens on 2026-08-15 while base was at 2.4x maintenance coverage and
    xyz at 14.6x. See INVARIANTS.md #2 for the incident.
    """
    results: list[str] = []
    risk = cfg.get("risk", {})
    if "max_dex_exposure_usd" not in risk:
        results.append(
            _fmt_fail(
                "risk.max_dex_exposure_usd MISSING — required per-clearinghouse "
                "(2026-08-15: shared cap blocked 40/40 xyz opens)"
            )
        )
    else:
        results.append(_fmt_ok(f"risk.max_dex_exposure_usd={risk['max_dex_exposure_usd']} present"))
    return results


def main() -> int:
    cfg_path = ROOT / "config.yaml"
    try:
        cfg = yaml.safe_load(cfg_path.read_text())
    except (OSError, yaml.YAMLError) as e:
        print(_fmt_fail(f"could not load {cfg_path}: {e}"))
        return 1
    if not isinstance(cfg, dict):
        print(_fmt_fail(f"config root is not a mapping ({type(cfg).__name__})"))
        return 1

    all_lines: list[str] = []
    all_lines += check_leader_weights_not_muted(cfg)
    all_lines += check_no_zero_caps(cfg)
    all_lines += check_per_clearinghouse_cap_present(cfg)

    fails = sum(1 for ln in all_lines if ln.startswith("FAIL"))
    for ln in all_lines:
        print(ln)
    if fails:
        print(f"BLOCKED  {fails} invariant(s) failed")
    return fails


if __name__ == "__main__":
    raise SystemExit(main())
