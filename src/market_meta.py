"""Caches Hyperliquid market metadata for tick/lot rounding.

Hyperliquid rejects orders that don't respect the per-asset size precision
(`szDecimals`) and the price rule. We pre-load both at startup and round
before submit.

HL's price rule (verified against the docs and the SDK's own
`Exchange._slippage_price`, which does
`round(float(f"{px:.5g}"), (6 if not is_spot else 8) - szDecimals)`):

    A price may have at most 5 significant figures, AND no more than
    `MAX_DECIMALS - szDecimals` decimal places, where MAX_DECIMALS is
    6 for perps and 8 for spot.

We used to enforce only the 5-sig-fig half. That is why sub-cent coins broke:
PUMP at ~$0.0044449 needs 7 decimals to carry 5 sig figs, HL's cap is
6 - szDecimals(0) = 6, so every PUMP order came back `Order has invalid
price` (29 rejects, then the poison cooldown in mirror.py muted the coin).
`round_price` now takes the coin and applies BOTH halves of the rule.
"""

import logging
from math import ceil, floor, log10
from threading import Lock
from typing import Any

from .errors import MarketMetaError, UnknownPrecisionError

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
# HL's MAX_DECIMALS, per the tick/lot-size docs and the SDK.
_MAX_PRICE_DECIMALS_PERP = 6
_MAX_PRICE_DECIMALS_SPOT = 8


def _is_outcome(coin: str) -> bool:
    """HIP-4 outcome legs are named `#NN` (yes) / `+NN` (no)."""
    return coin.startswith("#") or coin.startswith("+")


def _is_spot(coin: str) -> bool:
    """Spot pairs are `BASE/QUOTE` or the `@index` canonical form."""
    return "/" in coin or coin.startswith("@")


def _is_dex_prefixed(coin: str) -> bool:
    """HIP-3 builder-dex coins are `<dex>:<symbol>` — e.g. `xyz:MU`, `flx:BTC`.

    The `:` separator is reserved for builder-deployed perp dexes; nothing in
    the original perp universe, the spot universe or HIP-4 outcomes uses it.
    """
    return ":" in coin


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
        """Fetch perp + spot metadata from the API. Idempotent.

        NOTE: `info.meta()` returns the ORIGINAL perp dex only. HIP-3
        builder-dex assets (`xyz:*`, `flx:*`, ...) are not in here — they
        arrive via `register_dex_assets()`, driven by `register_hip3_dexes`.
        """
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

    def register_dex_assets(self, universe: Any) -> int:
        """Ingest a HIP-3 builder-dex universe's szDecimals. Idempotent.

        `load()` can only see the original perp dex, so without this the
        `xyz:*` surface was permanently unknown to the rounder and fell back
        to a guess. Called from `register_hip3_dexes` (src/hl_hip3.py) on both
        startup and the 30-min refresh, so a dex that adds symbols mid-session
        gets picked up on the next tick.

        Returns the number of assets cached.
        """
        if not isinstance(universe, list):
            return 0
        n = 0
        with self._lock:
            for asset in universe:
                if not isinstance(asset, dict):
                    continue
                name = asset.get("name")
                sz = asset.get("szDecimals")
                if not name or sz is None:
                    continue
                try:
                    self._sz_decimals[name] = int(sz)
                except (TypeError, ValueError):
                    continue
                n += 1
        return n

    def has_size_decimals(self, coin: str) -> bool:
        """True if we KNOW this coin's szDecimals (or it needs no lookup)."""
        if _is_outcome(coin):
            return True
        return coin in self._sz_decimals

    def round_size(self, coin: str, sz: float) -> float:
        """Round size DOWN to the coin's szDecimals.

        For HIP-4 outcomes (`#NN` / `+NN`), defaults to integer shares.
        For unknown ORIGINAL-dex coins, defaults to 4 decimals (perp default).

        Raises UnknownPrecisionError for an unknown HIP-3 / builder-dex coin
        (`<dex>:<symbol>`) — see `_size_decimals_for` for why we refuse rather
        than guess there.
        """
        if sz <= 0:
            return 0.0
        decimals = self._size_decimals_for(coin)
        # Round DOWN to never exceed the leader's notional
        factor = 10**decimals
        return floor(sz * factor) / factor if factor else floor(sz)

    def round_size_up(self, coin: str, sz: float) -> float:
        """Round size UP to the coin's szDecimals (ceiling).

        Counterpart to `round_size`. Only for the sub-minimum rescue path in
        `MirrorTrader._build_intent` — floor-rounding a clip that sits exactly
        on `min_per_trade_usd` produces a notional a few cents BELOW the venue
        minimum, and the order is then discarded. Incident 2026-07-21 →
        2026-08-14: leader 0x6cd520c1's weight moved 1.5 → 1.0, making the
        fixed clip exactly $10.00 against a $10.00 minimum; 10,706 fills were
        silently dropped over 24 days while only 79 orders got through.

        Callers MUST re-check the resulting notional against
        `max_per_trade_usd` — rounding up can only ever increase exposure.

        The tiny float fudge (1e-9 of a step) stops binary representation
        error from adding a whole extra step to a size that is already exact
        (e.g. 33.3334 stored as 33.33340000000001).
        """
        if sz <= 0:
            return 0.0
        decimals = self._size_decimals_for(coin)
        factor = float(10**decimals)
        return ceil(sz * factor - 1e-9) / factor

    def size_step(self, coin: str) -> float:
        """Smallest tradable size increment for `coin` (1 szDecimals tick)."""
        return 1.0 / float(10 ** self._size_decimals_for(coin))

    def round_price(self, px: float, coin: str) -> float:
        """Round price to HL's rule: 5 sig figs AND <= MAX_DECIMALS - szDecimals.

        Symmetric (no direction bias). `coin` is required: the decimal cap is
        per-asset, and defaulting it was exactly the bug — see the module
        docstring for the 2026-08 PUMP `invalid price` cascade.

        For a coin whose szDecimals we don't know we still clamp to the hard
        MAX_DECIMALS (6 perp / 8 spot). That is strictly safer than the old
        behaviour (which could emit 7 decimals) and it is right whenever
        szDecimals is 0, which is the case for the cheap coins that are the
        only ones able to trip the cap in the first place.
        """
        if px <= 0:
            return px
        digits = _PRICE_SIG_FIGS - 1 - floor(log10(abs(px)))
        digits = min(digits, self._max_price_decimals_for(coin))
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
    def _max_price_decimals_for(self, coin: str) -> int:
        """MAX_DECIMALS - szDecimals, per HL's tick/lot-size rule."""
        max_decimals = _MAX_PRICE_DECIMALS_SPOT if _is_spot(coin) else _MAX_PRICE_DECIMALS_PERP
        if _is_outcome(coin):
            return max_decimals - _DEFAULT_OUTCOME_SZ_DECIMALS
        sz_decimals = self._sz_decimals.get(coin)
        if sz_decimals is None:
            # Unknown coin: apply the hard cap only. Never widen past it.
            return max_decimals
        return max_decimals - sz_decimals

    def _size_decimals_for(self, coin: str) -> int:
        if _is_outcome(coin):
            return _DEFAULT_OUTCOME_SZ_DECIMALS
        decimals = self._sz_decimals.get(coin)
        if decimals is not None:
            return decimals
        if _is_dex_prefixed(coin):
            # REFUSE to guess on HIP-3 builder dexes. Guessing 4 here is what
            # started the Jul-Aug cascade: `register_hip3_dexes` failed on the
            # perpDexs fetch 215 times in August, so `xyz:*` never landed in
            # the cache; we submitted `xyz:MU sz=0.0143` (4dp) on 2026-08-10
            # when xyz:MU is 3dp (xyz:SKHY is 2dp); HL answered `Order has
            # invalid size`; mirror.py's _POISON_ORDER_ERRORS then muted the
            # coin for 300s, and every subsequent leader fill on it was
            # rejected `poison_cooldown` — 5,366 of them across Jul-Aug
            # (2,510 on 07-27 alone), on precisely the surface several of our
            # leaders specialise in.
            # A skipped trade costs us one signal. A poisoned coin costs us
            # every signal on that coin for the next 5 minutes, repeatedly.
            raise UnknownPrecisionError(
                f"szDecimals unknown for builder-dex coin {coin!r} "
                "(HIP-3 registration incomplete); refusing to guess"
            )
        return _DEFAULT_PERP_SZ_DECIMALS
