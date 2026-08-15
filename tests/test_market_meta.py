from unittest.mock import MagicMock

import pytest

from src.errors import MarketMetaError, UnknownPrecisionError
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
    """WIF is szDecimals=0, so the decimal cap (6-0=6) never binds here and
    we see the pure 5-significant-figure half of HL's rule."""
    mm = MarketMeta(info)
    mm.load()
    assert mm.round_price(0.5427, "WIF") == 0.5427
    assert mm.round_price(0.54271234, "WIF") == 0.54271
    assert mm.round_price(65000.123, "WIF") == 65000.0
    assert mm.round_price(1.234567, "WIF") == 1.2346


def test_round_price_zero_negative(info):
    mm = MarketMeta(info)
    mm.load()
    assert mm.round_price(0, "WIF") == 0
    assert mm.round_price(-1, "WIF") == -1


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


# --- HIP-3 builder-dex size precision (2026-08 poison cascade) --------------
#
# Chain of failure this section locks down:
#   `register_hip3_dexes: perpDexs fetch failed` x215 in Aug 2026
#     -> xyz:* never lands in MarketMeta
#     -> old code guessed szDecimals=4
#     -> `xyz:MU sz=0.0143` (4dp) submitted 2026-08-10, real xyz:MU is 3dp
#     -> HL: `Order has invalid size`
#     -> mirror.py _POISON_ORDER_ERRORS mutes the coin 300s
#     -> 5,366 poison_cooldown rejects Jul-Aug (2,510 on 07-27 alone).


def test_unknown_builder_dex_coin_refuses_to_guess(info):
    """The regression that matters: never invent szDecimals for `<dex>:<sym>`."""
    mm = MarketMeta(info)
    mm.load()
    assert not mm.has_size_decimals("xyz:MU")
    with pytest.raises(UnknownPrecisionError, match="xyz:MU"):
        mm._size_decimals_for("xyz:MU")
    with pytest.raises(UnknownPrecisionError, match="xyz:MU"):
        mm.round_size("xyz:MU", 0.0143)


def test_unknown_builder_dex_coin_is_not_silently_4dp(info):
    """Explicitly assert the OLD behaviour is gone (it returned 0.0143)."""
    mm = MarketMeta(info)
    mm.load()
    try:
        got = mm.round_size("xyz:MU", 0.01439)
    except UnknownPrecisionError:
        got = None
    assert got is None, f"guessed a size ({got}) for an unregistered builder-dex coin"


def test_registered_xyz_mu_rounds_to_3dp(info):
    """xyz:MU is szDecimals=3. 0.0143 (the size we actually submitted on
    2026-08-10) must come back 0.014, not 0.0143."""
    mm = MarketMeta(info)
    mm.load()
    n = mm.register_dex_assets(
        [
            {"name": "xyz:MU", "szDecimals": 3},
            {"name": "xyz:SKHY", "szDecimals": 2},
            {"name": "xyz:SKHX", "szDecimals": 2},
        ]
    )
    assert n == 3
    assert mm.has_size_decimals("xyz:MU")
    assert mm._size_decimals_for("xyz:MU") == 3
    assert mm.round_size("xyz:MU", 0.0143) == 0.014
    # rounds DOWN, never up past the leader's notional
    assert mm.round_size("xyz:MU", 0.01399) == 0.013
    # xyz:SKHY is 2dp — the most-poisoned coin (40 rejects)
    assert mm.round_size("xyz:SKHY", 0.0143) == 0.01
    assert mm.round_size("xyz:SKHX", 1.2345) == 1.23


def test_register_dex_assets_idempotent_and_junk_tolerant(info):
    mm = MarketMeta(info)
    mm.load()
    mm.register_dex_assets([{"name": "xyz:MU", "szDecimals": 3}])
    mm.register_dex_assets([{"name": "xyz:MU", "szDecimals": 3}])
    assert mm._size_decimals_for("xyz:MU") == 3
    # Junk shapes must not raise or poison the cache
    assert mm.register_dex_assets(None) == 0
    assert mm.register_dex_assets({"universe": []}) == 0
    assert mm.register_dex_assets(["notadict", {}, {"name": "x:Y"}, {"szDecimals": 1}]) == 0
    assert mm.register_dex_assets([{"name": "x:Y", "szDecimals": "bad"}]) == 0
    assert mm._size_decimals_for("xyz:MU") == 3


def test_builder_dex_symbol_can_be_updated_by_later_refresh(info):
    """HL can re-list a symbol at a different precision; the 30-min HIP-3
    refresh must overwrite, not keep the stale value."""
    mm = MarketMeta(info)
    mm.load()
    mm.register_dex_assets([{"name": "xyz:MU", "szDecimals": 4}])
    mm.register_dex_assets([{"name": "xyz:MU", "szDecimals": 3}])
    assert mm._size_decimals_for("xyz:MU") == 3


def test_non_dex_unknown_coin_still_defaults(info):
    """Scope check: the refusal is ONLY for `<dex>:<sym>` names. Original-dex
    coins keep the historical 4dp default (they come from info.meta(), so a
    miss there means the whole universe fetch was empty, not a HIP-3 gap)."""
    mm = MarketMeta(info)
    mm.load()
    assert mm._size_decimals_for("UNKNOWN") == 4
    assert mm.round_size("UNKNOWN", 0.123456) == 0.1234
    # Outcomes never need a lookup at all
    assert mm.has_size_decimals("#11")
    assert mm.round_size("#11", 12.7) == 12.0


# --- price rule: 5 sig figs AND <= MAX_DECIMALS - szDecimals ---------------


def _decimals(px: float) -> int:
    s = repr(float(px))
    return len(s.split(".")[1].rstrip("0")) if "." in s and "e" not in s else 0


def test_round_price_pump_sub_cent_respects_6_decimal_perp_cap(info):
    """PUMP regression. ~$0.004 needs 7 decimals to carry 5 sig figs, but HL
    caps perps at 6 - szDecimals. 5-sig-figs-only produced 7dp -> `Order has
    invalid price` -> 29 PUMP rejects + poison cascade (Aug 2026)."""
    mm = MarketMeta(info)
    mm.load()
    mm.register_dex_assets([{"name": "PUMP", "szDecimals": 0}])
    px = mm.round_price(0.0044449, "PUMP")
    assert _decimals(px) <= 6
    assert px == 0.004445
    # A few more sub-cent points across the cap boundary
    assert _decimals(mm.round_price(0.00123456, "PUMP")) <= 6
    assert _decimals(mm.round_price(0.000987654, "PUMP")) <= 6
    assert _decimals(mm.round_price(0.0000123456, "PUMP")) <= 6


def test_round_price_5_sig_figs_alone_would_have_been_invalid():
    """Pin the exact old-vs-new difference so nobody 'simplifies' the clamp away."""
    from math import floor, log10

    px = 0.0044449
    old_digits = 5 - 1 - floor(log10(abs(px)))
    assert old_digits == 7  # > HL's 6-decimal perp cap → rejected


def test_round_price_decimal_cap_binds_for_high_szdecimals(info):
    """BTC is szDecimals=5 → at most 6-5=1 decimal place on the price."""
    mm = MarketMeta(info)
    mm.load()
    assert _decimals(mm.round_price(65000.123, "BTC")) <= 1
    assert mm.round_price(1.234567, "BTC") == 1.2
    # ETH is 4 → cap 2
    assert mm.round_price(1.234567, "ETH") == 1.23


def test_round_price_spot_gets_8_decimals(info):
    """Spot MAX_DECIMALS is 8, not 6. PURR base szDecimals=0 → cap 8."""
    mm = MarketMeta(info)
    mm.load()
    assert mm._max_price_decimals_for("PURR/USDC") == 8
    # 5 sig figs still binds first here
    assert mm.round_price(0.0044449, "PURR/USDC") == 0.0044449


def test_round_price_unknown_coin_clamped_to_hard_cap(info):
    """Unknown szDecimals: we can't compute 6-szDecimals, but we must never
    emit more than the hard MAX_DECIMALS. Strictly safer than the old 7dp."""
    mm = MarketMeta(info)
    mm.load()
    assert _decimals(mm.round_price(0.0044449, "xyz:UNKNOWN")) <= 6
    assert _decimals(mm.round_price(0.0044449, "NOPE")) <= 6


def test_round_price_outcome_uses_perp_cap(info):
    """HIP-4 outcomes are szDecimals=0 perps → cap 6.

    At normal outcome prices (~0.5) the 5-sig-fig half binds and nothing
    changes. But a deep-longshot leg at ~0.0012 needed 7 decimals under the
    old rule — i.e. outcomes could hit `invalid price` too, not just PUMP.
    The cap now truncates it to 6."""
    mm = MarketMeta(info)
    mm.load()
    assert mm.round_price(0.54271234, "#11") == 0.54271
    assert mm.round_price(0.001234567, "+11") == 0.001235
    assert _decimals(mm.round_price(0.001234567, "+11")) <= 6


def test_round_price_registered_xyz_coin_uses_its_szdecimals(info):
    mm = MarketMeta(info)
    mm.load()
    mm.register_dex_assets([{"name": "xyz:MU", "szDecimals": 3}])
    # cap = 6 - 3 = 3
    assert mm.round_price(123.45678, "xyz:MU") == 123.46  # 5 sig figs binds
    assert mm.round_price(1.2345678, "xyz:MU") == 1.235  # decimal cap binds
    assert _decimals(mm.round_price(0.0044449, "xyz:MU")) <= 3
