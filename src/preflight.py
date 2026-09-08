"""Pre-flight validation: prove HL connectivity, schema, and account access
before the bot subscribes to anything or submits any orders.

Exposes `run_preflight()` returning a PreflightReport. The CLI uses this for
`--preflight` mode; the main loop uses it as a startup gate.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)

REQUIRED_FILL_FIELDS = frozenset({"coin", "px", "sz", "side", "tid", "time", "closedPnl", "fee"})

# Retry budget for each preflight probe. Incident 2026-08-15 03:09 UTC: a
# deploy ran `--preflight` and then restarted the service within the same
# minute, so HL rate-limited the back-to-back `meta` + `outcomeMeta` calls
# (429). Preflight recorded them as hard errors, declared the venue UNHEALTHY
# and aborted startup — for a condition that clears on its own in seconds.
# A transient 429 must never be able to stop the engine from booting.
PREFLIGHT_MAX_ATTEMPTS = 3
PREFLIGHT_BASE_BACKOFF_S = 2.0
# Substrings marking an error worth retrying: rate limits and the transient
# 5xx/gateway family. Anything else (bad address, schema drift) is a real
# failure and should fail fast rather than burn 3 attempts.
_TRANSIENT_MARKERS = ("429", "too many requests", "rate limit", "502", "503", "504", "timed out", "timeout")


def _is_transient(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(m in text for m in _TRANSIENT_MARKERS)


def _probe(
    fn: Callable[[], Any],
    *,
    what: str,
    errors: list[str],
    max_attempts: int | None = None,
    base_backoff_s: float | None = None,
) -> Any:
    """Run one preflight probe, retrying transient failures.

    Returns the call's result, or None if every attempt failed (in which case
    the final error has been appended to `errors`, preserving the previous
    contract that a failed probe shows up in the report).

    The limits are read from the module constants at CALL time, not bound as
    argument defaults — otherwise a test that patches the backoff would still
    sleep for real, which is how this helper's own tests took 10s on the first
    pass.
    """
    if max_attempts is None:
        max_attempts = PREFLIGHT_MAX_ATTEMPTS
    if base_backoff_s is None:
        base_backoff_s = PREFLIGHT_BASE_BACKOFF_S
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 — every probe failure is reportable
            if attempt >= max_attempts or not _is_transient(e):
                errors.append(f"{what}: {type(e).__name__}: {e}")
                return None
            backoff = base_backoff_s * (2 ** (attempt - 1))
            log.warning(
                "preflight: %s failed transiently (attempt %d/%d), retrying in %.1fs: %s",
                what, attempt, max_attempts, backoff, e,
            )
            time.sleep(backoff)
    return None


@dataclass
class PreflightReport:
    api_url: str
    account_address: str
    perp_markets: int = 0
    spot_markets: int = 0
    outcome_markets: int = 0
    outcomes: list[dict[str, Any]] = field(default_factory=list)
    account_reachable: bool = False
    own_fills_count: int = 0
    sample_fill: dict[str, Any] | None = None
    schema_ok: bool = False
    schema_missing: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return (
            self.perp_markets > 0 and self.account_reachable and self.schema_ok and not self.errors
        )


def run_preflight(info: Any, account_address: str) -> PreflightReport:
    api_url = getattr(info, "base_url", "<unknown>")
    r = PreflightReport(api_url=api_url, account_address=account_address)

    meta = _probe(info.meta, what="meta", errors=r.errors) or {}
    r.perp_markets = len(meta.get("universe", []) or [])

    spot = _probe(info.spot_meta, what="spot_meta", errors=r.errors) or {}
    r.spot_markets = len(spot.get("universe", []) or [])

    outcomes_resp = _probe(
        lambda: info.post("/info", {"type": "outcomeMeta"}),
        what="outcomeMeta",
        errors=r.errors,
    ) or {}
    r.outcomes = outcomes_resp.get("outcomes", []) or []
    r.outcome_markets = len(r.outcomes)

    # Reachability is about whether the CALL succeeded, not what it returned —
    # `user_state` can legitimately answer with a falsy shape. So compare the
    # error count either side of the probe rather than inspecting the result.
    errors_before = len(r.errors)
    _probe(lambda: info.user_state(account_address), what="user_state", errors=r.errors)
    r.account_reachable = len(r.errors) == errors_before

    try:
        fills = info.user_fills(account_address) or []
        r.own_fills_count = len(fills) if isinstance(fills, list) else 0
        if r.own_fills_count > 0 and isinstance(fills[0], dict):
            r.sample_fill = fills[0]
            missing = REQUIRED_FILL_FIELDS - set(fills[0].keys())
            r.schema_missing = sorted(missing)
            r.schema_ok = not missing
        else:
            r.schema_ok = True  # nothing to validate; not a failure
    except Exception as e:
        r.errors.append(f"user_fills: {type(e).__name__}: {e}")

    return r


def format_report(r: PreflightReport) -> str:
    lines: list[str] = []
    lines.append(f"=== Hyperliquid preflight: {r.api_url} ===")
    lines.append(f"  perp markets:    {r.perp_markets}")
    lines.append(f"  spot markets:    {r.spot_markets}")
    lines.append(f"  outcome markets: {r.outcome_markets}")
    if r.outcomes:
        lines.append("  current outcomes:")
        for o in r.outcomes[:10]:
            desc = o.get("description") or o.get("name") or "?"
            lines.append(f"    - outcome={o.get('outcome')}: {desc}")
    addr = (r.account_address or "")[:10] + "…"
    lines.append(f"  account {addr}: {'reachable' if r.account_reachable else 'UNREACHABLE'}")
    lines.append(f"  own fills:       {r.own_fills_count}")
    lines.append(f"  fill schema:     {'OK' if r.schema_ok else 'MISMATCH'}")
    if r.schema_missing:
        lines.append(f"    missing fields: {r.schema_missing}")
    if r.errors:
        lines.append("  ERRORS:")
        for e in r.errors:
            lines.append(f"    ✗ {e}")
    lines.append(f"  overall:         {'HEALTHY' if r.healthy else 'UNHEALTHY'}")
    return "\n".join(lines)
