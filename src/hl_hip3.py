"""Register HIP-3 perp DEX assets so the SDK can resolve their coin names.

The hyperliquid SDK's `Info(...)` defaults to loading only the original perp
DEX. HIP-3 builder-deployed dexes (xyz, flx, vntl, hyna, km, abcd, cash, para,
etc.) require explicit registration. Without this, `exchange.order("xyz:NVDA",
...)` fails with `KeyError: 'xyz:NVDA'` because the SDK's `coin_to_asset` map
doesn't include those names.

Same pattern as `src/hl_outcome.py` (which patches HIP-4 outcomes). Both
fixes work by post-construction mutation of the Info instance's coin maps.

Live cost of NOT having this: 2026-05-23 14:57 UTC — our oil specialist
(`0x8607a7d1`, weight 2.0, xyz domain expert) fired multiple xyz:NVDA buys.
Mirror submit raised KeyError on every child order. Missed signal entirely
from our highest-conviction leader on their specialty.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from .protocols import InfoProto

log = logging.getLogger(__name__)

# Retry policy for the /info fetches below.
#
# Why this exists: `register_hip3_dexes: perpDexs fetch failed` fired 215
# times in August 2026. A single failure used to be terminal for the whole
# cycle — we returned 0 and then sat blind until main.py's next 30-min
# refresh tick. Blind means `xyz:*` is absent from both the SDK coin map AND
# the MarketMeta szDecimals cache, which is the head of the poison cascade
# (see src/market_meta.py `_size_decimals_for`). Three attempts with 2s/4s
# backoff covers the transient upstream blips we actually observe, and costs
# at most ~6s on a genuine outage — well inside the 30-min tick, and this
# runs off the order hot path.
_FETCH_MAX_ATTEMPTS = 3
_FETCH_BASE_BACKOFF_S = 2.0


def _post_with_retry(
    info: InfoProto,
    payload: dict[str, Any],
    *,
    what: str,
    max_attempts: int = _FETCH_MAX_ATTEMPTS,
    base_backoff_s: float = _FETCH_BASE_BACKOFF_S,
) -> Any:
    """POST /info with exponential backoff. Returns None if every attempt fails.

    Retries on exception AND on a `None` body — HL occasionally answers 200
    with an empty payload, which is just as blind as a raised exception.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            result = info.post("/info", payload)
        except Exception:
            if attempt >= max_attempts:
                log.exception("register_hip3_dexes: %s fetch failed after %d attempts", what, attempt)
                return None
            backoff = base_backoff_s * (2 ** (attempt - 1))
            log.warning(
                "register_hip3_dexes: %s fetch failed (attempt %d/%d), retrying in %.1fs",
                what, attempt, max_attempts, backoff, exc_info=True,
            )
            time.sleep(backoff)
            continue
        if result is None:
            if attempt >= max_attempts:
                log.warning(
                    "register_hip3_dexes: %s returned empty after %d attempts", what, attempt
                )
                return None
            backoff = base_backoff_s * (2 ** (attempt - 1))
            log.warning(
                "register_hip3_dexes: %s returned empty (attempt %d/%d), retrying in %.1fs",
                what, attempt, max_attempts, backoff,
            )
            time.sleep(backoff)
            continue
        return result
    return None


def register_hip3_dexes(info: InfoProto, market_meta: Any | None = None) -> int:
    """Register every active HIP-3 dex's universe into `info.coin_to_asset`.

    Returns the number of assets registered. Idempotent — re-running just
    overwrites the same coin → asset_id mappings.

    When `market_meta` is passed we also copy each asset's szDecimals and
    maxLeverage into it. HIP-3 names are absent from `info.meta()`, so
    MarketMeta would otherwise fall back to its conservative 1x default and
    the margin-headroom guard would reject every HIP-3 open. We're already
    holding the dex meta here — no extra HTTP call.

    Uses the SDK's internal `set_perp_meta(meta, offset)` to mutate the
    instance's maps. Offsets match the SDK's own convention:
    builder-deployed perp dexes start at asset_id 110_000 with step 10_000.

    If `market_meta` is passed, each dex's szDecimals are also pushed into the
    MarketMeta cache. `MarketMeta.load()` calls `info.meta()`, which only ever
    returns the ORIGINAL perp dex, so this is the ONLY path by which the
    rounder learns that xyz:MU is 3dp and xyz:SKHY is 2dp. Without it the
    rounder refuses every builder-dex order (by design — see
    `UnknownPrecisionError`).

    Tolerant of partial failures: if one dex's meta fetch fails, we log and
    continue with the others. Each fetch is retried with backoff first.
    """
    dexes = _post_with_retry(info, {"type": "perpDexs"}, what="perpDexs")
    if dexes is None:
        return 0
    if not isinstance(dexes, list):
        log.warning("register_hip3_dexes: perpDexs returned non-list %s", type(dexes))
        return 0

    registered = 0
    # First entry is the original dex (null). Builder-deployed dexes follow,
    # offset starts at 110000 with step 10000 per SDK constants.
    for i, dex_info in enumerate(dexes[1:]):
        if not isinstance(dex_info, dict):
            continue
        name = dex_info.get("name")
        if not name:
            continue
        offset = 110_000 + i * 10_000
        meta: Any = _post_with_retry(
            info, {"type": "meta", "dex": name}, what=f"meta(dex={name})"
        )
        if meta is None:
            continue
        if not isinstance(meta, dict) or "universe" not in meta:
            log.warning("register_hip3_dexes: bad meta shape for dex=%s", name)
            continue
        # set_perp_meta is the SDK's blessed way to add assets post-construction.
        # We call it through the SDK's own method so future SDK changes propagate.
        try:
            info.set_perp_meta(meta, offset)  # type: ignore[attr-defined]
        except AttributeError:
            # SDK changed — fall back to manual map mutation
            universe = meta.get("universe", [])
            for asset_idx, asset_info in enumerate(universe):
                if not isinstance(asset_info, dict):
                    continue
                coin = asset_info.get("name")
                if not coin:
                    continue
                asset_id = offset + asset_idx
                info.coin_to_asset[coin] = asset_id  # type: ignore[attr-defined]
                info.name_to_coin[coin] = coin  # type: ignore[attr-defined]
                sz_decimals = asset_info.get("szDecimals")
                if sz_decimals is not None:
                    info.asset_to_sz_decimals[asset_id] = sz_decimals  # type: ignore[attr-defined]
        if market_meta is not None:
            for asset_info in meta.get("universe", []) or []:
                if not isinstance(asset_info, dict):
                    continue
                coin = asset_info.get("name")
                if not coin:
                    continue
                # HL returns HIP-3 universe names already dex-prefixed
                # ("xyz:SPCX"), which is what leader fills carry. Record the
                # bare name too so we still match if that ever changes.
                market_meta.record_asset(
                    coin, asset_info.get("szDecimals"), asset_info.get("maxLeverage")
                )
                if ":" not in coin:
                    market_meta.record_asset(
                        f"{name}:{coin}",
                        asset_info.get("szDecimals"),
                        asset_info.get("maxLeverage"),
                    )
            # Bulk szDecimals ingest as well. record_asset above carries
            # maxLeverage (which the margin-headroom guard needs, else every
            # `xyz:` name prices at the 1x default); this is the szDecimals
            # path the rounder consults. Both are idempotent.
            try:
                market_meta.register_dex_assets(meta.get("universe", []) or [])
            except Exception:
                log.exception("register_hip3_dexes: MarketMeta ingest failed for dex=%s", name)
        count = len(meta.get("universe", []) or [])
        registered += count
        log.info("register_hip3_dexes: registered %d assets from dex=%s (offset=%d)", count, name, offset)
    return registered
