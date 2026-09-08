"""Custom exception hierarchy for hyper-trader.

Using these instead of bare exceptions makes failure modes explicit and
lets callers catch only what they intend to handle.
"""


class HyperTraderError(Exception):
    """Base class for all hyper-trader errors."""


class ConfigError(HyperTraderError):
    """Configuration is invalid or missing required values."""


class PreflightError(HyperTraderError):
    """Preflight checks failed; bot is not safe to start."""


class MarketMetaError(HyperTraderError):
    """Failed to load market metadata or look up a coin."""


class UnknownPrecisionError(MarketMetaError):
    """A coin's szDecimals is unknown and guessing it is not safe.

    Raised for HIP-3 builder-dex coins (`<dex>:<symbol>`) that never made it
    into the MarketMeta cache — normally because `register_hip3_dexes` could
    not reach the `perpDexs` endpoint. Callers must skip the order: a wrong
    size precision gets the coin poisoned for 300s by mirror.py's
    `_POISON_ORDER_ERRORS` handler (2026-07/08, 5,366 poison_cooldown
    rejects, all on `xyz:*`).
    """


class OrderError(HyperTraderError):
    """Order submission failed at the exchange layer."""
