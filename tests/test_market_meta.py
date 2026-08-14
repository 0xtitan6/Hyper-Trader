from unittest.mock import MagicMock

import pytest

from src.errors import MarketMetaError
from src.market_meta import MarketMeta


@pytest.fixture
def info():
    info = MagicMock()
    info.meta.return_value = {
        "universe": [
            {"name": "BTC", "szDecimals": 5},
            {"name": "ETH", "szDecimals": 4},
            {"name": "WIF", "szDecimals": 0},
        ]
    }
    info.spot_meta.return_value = {
        "universe": [
            {"name": "PURR/USDC", "tokens": [1, 0]},
            {"name": "@1", "tokens": [2, 0]},
        ],
        "tokens": [
            {"name": "USDC", "szDecimals": 8, "index": 0},
            {"name": "PURR", "szDecimals": 0, "index": 1},
            {"name": "FOO", "szDecimals": 4, "index": 2},
        ],
    }
    return info


def test_load_caches_decimals(info):
    mm = MarketMeta(info)
    mm.load()
    assert mm._size_decimals_for("BTC") == 5
    assert mm._size_decimals_for("ETH") == 4
    assert mm._size_decimals_for("WIF") == 0
    assert mm._size_decimals_for("PURR/USDC") == 0  # base = PURR
    assert mm._size_decimals_for("@1") == 4  # base = FOO


def test_load_idempotent(info):
    mm = MarketMeta(info)
    mm.load()
    mm.load()
    assert info.meta.call_count == 1
    assert info.spot_meta.call_count == 1


def test_unknown_perp_uses_default(info):
    mm = MarketMeta(info)
    mm.load()
    assert mm._size_decimals_for("UNKNOWN") == 4  # default


def test_outcomes_round_to_integer(info):
    mm = MarketMeta(info)
    mm.load()
    assert mm.round_size("#11", 12.7) == 12.0
    assert mm.round_size("#10", 0.5) == 0.0
    assert mm.round_size("+11", 99.999) == 99.0


def test_perp_rounds_to_szdecimals(info):
    mm = MarketMeta(info)
    mm.load()
    # BTC szDecimals=5
    assert mm.round_size("BTC", 0.0123456789) == 0.01234
    # ETH szDecimals=4
    assert mm.round_size("ETH", 0.123456) == 0.1234
    # WIF szDecimals=0
    assert mm.round_size("WIF", 12.7) == 12.0


def test_round_size_zero_or_negative(info):
    mm = MarketMeta(info)
    mm.load()
    assert mm.round_size("BTC", 0) == 0
    assert mm.round_size("BTC", -1) == 0


def test_round_size_below_min_rounds_to_zero(info):
    mm = MarketMeta(info)
    mm.load()
    assert mm.round_size("BTC", 0.000001) == 0.0  # below 5 decimals → 0


def test_round_price_5_sig_figs(info):
    mm = MarketMeta(info)
    mm.load()
    assert mm.round_price(0.5427) == 0.5427
    assert mm.round_price(0.54271234) == 0.54271
    assert mm.round_price(65000.123) == 65000.0
    assert mm.round_price(1.234567) == 1.2346


def test_round_price_zero_negative(info):
    mm = MarketMeta(info)
    mm.load()
    assert mm.round_price(0) == 0
    assert mm.round_price(-1) == -1


def test_perp_meta_failure_raises():
    info = MagicMock()
    info.meta.side_effect = RuntimeError("upstream down")
    mm = MarketMeta(info)
    with pytest.raises(MarketMetaError, match="perp meta"):
        mm.load()


def test_spot_meta_failure_raises():
    info = MagicMock()
    info.meta.return_value = {"universe": []}
    info.spot_meta.side_effect = RuntimeError("upstream down")
    mm = MarketMeta(info)
    with pytest.raises(MarketMetaError, match="spot meta"):
        mm.load()


def test_empty_universe_safe(info):
    info.meta.return_value = {}
    info.spot_meta.return_value = {}
    mm = MarketMeta(info)
    mm.load()  # should not raise
    assert mm._size_decimals_for("ANYTHING") == 4


# --- max leverage (drives required-margin math in mirror._risk_check) ---------


def test_load_caches_max_leverage(info):
    info.meta.return_value = {
        "universe": [
            {"name": "BTC", "szDecimals": 5, "maxLeverage": 40},
            {"name": "WIF", "szDecimals": 0, "maxLeverage": 5},
        ]
    }
    mm = MarketMeta(info)
    mm.load()
    assert mm.max_leverage("BTC") == 40.0
    assert mm.max_leverage("WIF") == 5.0


def test_max_leverage_defaults_to_one_for_unknown_and_unleveraged(info):
    """Unknown → assume fully collateralized: over-stating leverage would let
    through exactly the orders HL rejects for insufficient margin."""
    mm = MarketMeta(info)
    mm.load()
    assert mm.max_leverage("NOTLISTED") == 1.0
    assert mm.max_leverage("#1420") == 1.0  # HIP-4 outcome
    assert mm.max_leverage("+1420") == 1.0  # outcome spot leg
    assert mm.max_leverage("PURR/USDC") == 1.0  # spot pair
    assert mm.max_leverage("@1") == 1.0


def test_max_leverage_ignores_junk_values(info):
    """A 0 or missing maxLeverage must not become a divide-by-zero downstream."""
    info.meta.return_value = {
        "universe": [
            {"name": "ZERO", "szDecimals": 2, "maxLeverage": 0},
            {"name": "NONE", "szDecimals": 2},
            {"name": "JUNK", "szDecimals": 2, "maxLeverage": "abc"},
        ]
    }
    mm = MarketMeta(info)
    mm.load()
    assert mm.max_leverage("ZERO") == 1.0
    assert mm.max_leverage("NONE") == 1.0
    assert mm.max_leverage("JUNK") == 1.0


def test_record_asset_registers_hip3_style_coin(info):
    """HIP-3 names never appear in info.meta(); register_hip3_dexes feeds them
    in so they aren't priced at the conservative 1x default."""
    mm = MarketMeta(info)
    mm.load()
    mm.record_asset("xyz:NVDA", sz_decimals=3, max_leverage=5)
    assert mm.max_leverage("xyz:NVDA") == 5.0
    assert mm._size_decimals_for("xyz:NVDA") == 3
    mm.record_asset("xyz:NVDA", sz_decimals=2, max_leverage=10)  # idempotent overwrite
    assert mm.max_leverage("xyz:NVDA") == 10.0
    mm.record_asset("", sz_decimals=1, max_leverage=1)  # no-op, no crash
