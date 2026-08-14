"""Caches Hyperliquid market metadata for tick/lot rounding.

Hyperliquid rejects orders that don't respect the per-asset size precision
(`szDecimals`) and the 5-significant-figure price rule. We pre-load both at
startup and round before submit.
"""

import logging
from math import floor, log10
from threading import Lock
from typing import Any

from .errors import MarketMetaError

log = logging.getLogger(__name__)

_DEFAULT_PERP_SZ_DECIMALS = 4
_DEFAULT_OUTCOME_SZ_DECIMALS = 0
_PRICE_SIG_FIGS = 5
# Leverage assumed for a coin we have no `maxLeverage` for. 1x = "fully
# collateralized", i.e. the most margin any order could possibly need. The
# margin-headroom guard (mirror._margin_headroom_check) divides notional by
# this number, so guessing HIGH would under-state the margin an order needs
# and let through exactly the orders HL then rejects. Guessing low only ever
# costs us a skipped trade, which is the cheaper mistake.
_DEFAULT_MAX_LEVERAGE = 1.0
# Outcomes (`#NN`/`+NN`) and spot are bought outright out of the spot balance —
# there is no leverage on them, so required margin == notional.
_UNLEVERAGED_MAX_LEVERAGE = 1.0


class MarketMeta:
    """Per-coin size precision + max-leverage lookup, with safe defaults if a
    coin isn't in cache."""

    def __init__(self, info: Any):
        self.info = info
        self._lock = Lock()
        self._sz_decimals: dict[str, int] = {}
        self._max_leverage: dict[str, float] = {}
        self._loaded = False

    def load(self) -> None:
        """Fetch perp + spot metadata from the API. Idempotent."""
        with self._lock:
            if self._loaded:
                return
            perp_count = self._load_perp()
            spot_count = self._load_spot()
            self._loaded = True
        log.info(
            "MarketMeta loaded: %d perp markets, %d spot markets cached",
            perp_count,
            spot_count,
        )

    def _load_perp(self) -> int:
        try:
            meta = self.info.meta() or {}
        except Exception as e:
            raise MarketMetaError(f"failed to fetch perp meta: {e}") from e
        n = 0
        for asset in meta.get("universe", []) or []:
            name = asset.get("name")
            if not name:
                continue
            self._sz_decimals[name] = int(asset.get("szDecimals", _DEFAULT_PERP_SZ_DECIMALS))
            self._record_max_leverage(name, asset.get("maxLeverage"))
            n += 1
        return n

    def _record_max_leverage(self, coin: str, raw: Any) -> None:
        """Store a coin's HL-declared maxLeverage, ignoring junk values.

        Missing/garbage stays out of the map so `max_leverage` falls back to
        the conservative default rather than trusting a 0 (which would make
        required-margin arithmetic divide by zero).
        """
        try:
            lev = float(raw)
        except (TypeError, ValueError):
            return
        if lev >= 1.0:
            self._max_leverage[coin] = lev

    def _load_spot(self) -> int:
        try:
            spot = self.info.spot_meta() or {}
        except Exception as e:
            raise MarketMetaError(f"failed to fetch spot meta: {e}") from e
        tokens_by_idx = {t.get("index"): t for t in spot.get("tokens", []) or []}
        n = 0
        for pair in spot.get("universe", []) or []:
            name = pair.get("name")
            token_idxs = pair.get("tokens", []) or []
            if not name or not token_idxs:
                continue
            base = tokens_by_idx.get(token_idxs[0], {})
            self._sz_decimals[name] = int(base.get("szDecimals", 0))
            n += 1
        return n

    def round_size(self, coin: str, sz: float) -> float:
        """Round size to the coin's szDecimals.

        For HIP-4 outcomes (`#NN` / `+NN`), defaults to integer shares.
        For unknown coins, defaults to 4 decimals (perp default).
        """
        if sz <= 0:
            return 0.0
        decimals = self._size_decimals_for(coin)
        # Round DOWN to never exceed the leader's notional
        factor = 10**decimals
        return floor(sz * factor) / factor if factor else floor(sz)

    def round_price(self, px: float) -> float:
        """Round price to 5 significant figures (HL rule). Symmetric (no direction bias)."""
        if px <= 0:
            return px
        digits = _PRICE_SIG_FIGS - 1 - floor(log10(abs(px)))
        return round(px, max(digits, 0))

    def record_asset(self, coin: str, sz_decimals: Any = None, max_leverage: Any = None) -> None:
        """Register a single asset discovered outside `load()`.

        HIP-3 builder dexes (`xyz:`, `flx:`, …) are NOT in `info.meta()`, so
        without this their max leverage is unknown and every HIP-3 order gets
        priced at the 1x default. `register_hip3_dexes` already fetches each
        dex's meta at startup and every 30 min, so it feeds us the numbers for
        free — no extra HTTP on our side. Idempotent (re-registration just
        overwrites, matching register_hip3_dexes' own contract).
        """
        if not coin:
            return
        with self._lock:
            if sz_decimals is not None:
                try:
                    self._sz_decimals[coin] = int(sz_decimals)
                except (TypeError, ValueError):
                    log.warning("record_asset: bad szDecimals for %s: %r", coin, sz_decimals)
            self._record_max_leverage(coin, max_leverage)

    def max_leverage(self, coin: str) -> float:
        """Max leverage HL allows on this coin (1.0 for outcomes/spot).

        Used to compute the initial margin an order needs. Unknown perps get
        `_DEFAULT_MAX_LEVERAGE` — see that constant for why we round down.
        """
        if coin.startswith("#") or coin.startswith("+"):
            return _UNLEVERAGED_MAX_LEVERAGE
        if coin.startswith("@") or "/" in coin:
            return _UNLEVERAGED_MAX_LEVERAGE
        return self._max_leverage.get(coin, _DEFAULT_MAX_LEVERAGE)

    def _size_decimals_for(self, coin: str) -> int:
        if coin.startswith("#") or coin.startswith("+"):
            return _DEFAULT_OUTCOME_SZ_DECIMALS
        return self._sz_decimals.get(coin, _DEFAULT_PERP_SZ_DECIMALS)
