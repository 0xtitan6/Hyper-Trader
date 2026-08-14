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


# ---------- round_size_up (sub-minimum rescue, incident 2026-08-14) ----------


def test_round_size_up_ceils_to_sz_decimals(info):
    mm = MarketMeta(info)
    mm.load()
    # The incident case: $10 clip / $3000 ETH = 0.00333... → 0.0034, not 0.0033
    assert mm.round_size_up("ETH", 10 / 3000) == 0.0034
    assert mm.round_size_up("BTC", 0.000001) == 0.00001  # never floors to zero
    assert mm.round_size_up("WIF", 0.75) == 1.0  # szDecimals=0 → whole lots


def test_round_size_up_leaves_exact_sizes_untouched(info):
    """Binary representation error must not silently add a whole extra step —
    that would inflate every rescued order by one lot."""
    mm = MarketMeta(info)
    mm.load()
    assert mm.round_size_up("ETH", 0.0034) == 0.0034
    assert mm.round_size_up("WIF", 3.0) == 3.0
    assert mm.round_size_up("ETH", 34 / 10000) == 0.0034  # float-inexact but on-grid
    assert mm.round_size_up("BTC", 333334 / 100000000) == 0.00334


def test_round_size_up_never_below_round_size(info):
    mm = MarketMeta(info)
    mm.load()
    for coin in ("BTC", "ETH", "WIF"):
        for sz in (0.00007, 0.0033333, 1.5, 19.999):
            assert mm.round_size_up(coin, sz) >= mm.round_size(coin, sz)


def test_round_size_up_zero_or_negative(info):
    mm = MarketMeta(info)
    mm.load()
    assert mm.round_size_up("BTC", 0) == 0.0
    assert mm.round_size_up("BTC", -1) == 0.0


def test_size_step_matches_sz_decimals(info):
    mm = MarketMeta(info)
    mm.load()
    assert mm.size_step("WIF") == 1.0
    assert mm.size_step("ETH") == 0.0001
    assert mm.size_step("BTC") == 0.00001
    assert mm.size_step("#11") == 1.0  # outcomes default to integer shares
