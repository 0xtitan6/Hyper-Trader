"""Tests for src/copy_econ.py — fee-tier economics of copying a leader."""

from __future__ import annotations

import pytest

from src.copy_econ import (
    DEFAULT_TAKER_BPS,
    compute_copy_econ,
    passes_fee_tier,
)


def _fill(
    coin: str = "BTC",
    px: float = 100.0,
    sz: float = 10.0,
    closed_pnl: float = 0.0,
    fee: float = 0.0,
    crossed: bool = True,
    fee_token: str = "USDC",
) -> dict:
    return {
        "coin": coin,
        "px": str(px),
        "sz": str(sz),
        "closedPnl": str(closed_pnl),
        "fee": str(fee),
        "crossed": crossed,
        "feeToken": fee_token,
        "side": "B",
        "time": 1_700_000_000_000,
    }


# --- turnover / basic accounting -------------------------------------------


def test_turnover_sums_absolute_notional_of_every_perp_fill():
    e = compute_copy_econ("0xABC", [_fill(px=100, sz=10), _fill(px=50, sz=4)])
    assert e.turnover_usd == pytest.approx(1200.0)
    assert e.perp_fill_count == 2
    assert e.econ_known is True
    assert e.address == "0xabc"


def test_turnover_per_mo_scales_a_short_window_up_to_30_days():
    # 360h of fills == half a month; a month of the same rate is 2x.
    e = compute_copy_econ("0xABC", [_fill(px=100, sz=10)], lookback_hours=360.0)
    assert e.turnover_usd == pytest.approx(1000.0)
    assert e.turnover_usd_per_mo == pytest.approx(2000.0)


def test_taker_fraction_counts_only_crossed_fills():
    fills = [_fill(crossed=True), _fill(crossed=True), _fill(crossed=False), _fill(crossed=False)]
    assert compute_copy_econ("0xABC", fills).taker_fill_fraction == pytest.approx(0.5)


# --- the edge maths ---------------------------------------------------------


def test_gross_edge_adds_their_fees_back_to_realized_pnl():
    # $1,000 turnover, $2 realized net, $0.45 of fees paid => $2.45 gross
    # => 24.5 bps gross. Our 4.5 bps taker leaves 20.0 bps.
    e = compute_copy_econ(
        "0xABC", [_fill(px=100, sz=10, closed_pnl=2.0, fee=0.45)], our_taker_bps=4.5
    )
    assert e.leader_fee_bps == pytest.approx(4.5)
    assert e.gross_edge_bps == pytest.approx(24.5)
    assert e.net_edge_bps == pytest.approx(20.0)
    assert e.net_pnl_at_our_tier_usd == pytest.approx(2.45 - 0.45)


def test_thin_edge_at_a_better_fee_tier_goes_NEGATIVE_at_ours():
    """The whole point of the module: a profitable leader we cannot copy.

    $100k turnover earning $20 net at a 0.5 bps tier is a real, positive
    business for them (2.5 bps gross). At our 4.5 bps it is a $200 loss.
    """
    e = compute_copy_econ(
        "0xABC",
        [_fill(px=1000.0, sz=100.0, closed_pnl=20.0, fee=5.0)],
        our_taker_bps=4.5,
    )
    assert e.realized_pnl_usd > 0  # they made money
    assert e.leader_fee_bps == pytest.approx(0.5)
    assert e.gross_edge_bps == pytest.approx(2.5)
    assert e.net_edge_bps == pytest.approx(-2.0)
    assert e.net_pnl_at_our_tier_usd == pytest.approx(-20.0)
    ok, reason = passes_fee_tier(e)
    assert ok is False
    assert "net_edge=-2.00bps" in reason


def test_maker_rebate_shows_as_a_negative_leader_fee():
    e = compute_copy_econ("0xABC", [_fill(px=100, sz=10, closed_pnl=1.0, fee=-0.10, crossed=False)])
    assert e.leader_fee_bps == pytest.approx(-1.0)
    # Rebate is added back out of the gross: their skill was $0.90, not $1.00.
    assert e.gross_edge_bps == pytest.approx(9.0)


def test_default_taker_bps_is_our_live_base_tier():
    e = compute_copy_econ("0xABC", [_fill(px=100, sz=10, closed_pnl=1.0)])
    assert e.our_taker_bps == DEFAULT_TAKER_BPS == 4.5
    assert e.net_edge_bps == pytest.approx(10.0 - 4.5)


# --- surface classification -------------------------------------------------


def test_outcome_and_spot_fills_are_excluded_from_perp_economics():
    fills = [
        _fill(coin="BTC", px=100, sz=10, closed_pnl=1.0),
        _fill(coin="#2120", px=0.5, sz=1000, closed_pnl=99.0, fee_token="+2120"),
        _fill(coin="@107", px=2.0, sz=500, closed_pnl=50.0),
        _fill(coin="PURR/USDC", px=1.0, sz=100, closed_pnl=7.0),
    ]
    e = compute_copy_econ("0xABC", fills)
    assert e.perp_fill_count == 1
    assert e.turnover_usd == pytest.approx(1000.0)
    assert e.realized_pnl_usd == pytest.approx(1.0)
    # The outcome fill's non-USD fee token must not have contaminated anything.
    assert e.fees_all_usd is True


def test_hip3_perp_fills_count_as_perps():
    e = compute_copy_econ("0xABC", [_fill(coin="xyz:SP500", px=100, sz=10, closed_pnl=1.0)])
    assert e.perp_fill_count == 1
    assert e.turnover_usd == pytest.approx(1000.0)


def test_non_usd_fee_token_on_a_perp_fill_flags_the_total_as_incomplete():
    e = compute_copy_econ(
        "0xABC", [_fill(coin="BTC", px=100, sz=10, closed_pnl=1.0, fee=0.5, fee_token="HYPE")]
    )
    assert e.fees_all_usd is False
    # The unpriceable fee is NOT guessed at, so it is simply absent.
    assert e.fees_paid_usd == pytest.approx(0.0)


# --- INV 4: UNKNOWN is never EMPTY ------------------------------------------


def test_no_fills_is_econ_unknown_not_zero_edge():
    e = compute_copy_econ("0xABC", [])
    assert e.econ_known is False
    assert e.net_edge_bps == 0.0  # placeholder, meaningless
    ok, reason = passes_fee_tier(e)
    assert ok is False
    assert "econ_unknown" in reason


def test_only_outcome_fills_is_also_econ_unknown():
    e = compute_copy_econ("0xABC", [_fill(coin="#2120", px=0.5, sz=100, closed_pnl=5.0)])
    assert e.perp_fill_count == 0
    assert e.econ_known is False
    assert passes_fee_tier(e)[0] is False


def test_econ_unknown_is_not_silently_admitted():
    """Fail-safe must not become fail-open in the wrong direction (INV 5).

    An unmeasurable leader must be rejected WITH A REASON, not admitted on the
    grounds that we found nothing bad.
    """
    ok, reason = passes_fee_tier(compute_copy_econ("0xABC", []))
    assert ok is False
    assert reason  # greppable, never empty


def test_unparseable_fills_are_skipped_not_treated_as_zero_notional():
    fills = [
        "not a dict",
        {"coin": "BTC", "px": "abc", "sz": "10"},
        {"coin": "BTC", "px": "0", "sz": "10"},  # zero price
        {"coin": "BTC", "px": "100", "sz": "0"},  # zero size
        _fill(px=100, sz=10, closed_pnl=1.0),
    ]
    e = compute_copy_econ("0xABC", fills)  # type: ignore[arg-type]
    assert e.perp_fill_count == 1
    assert e.turnover_usd == pytest.approx(1000.0)


def test_unparseable_closed_pnl_does_not_kill_the_fill():
    fills = [{**_fill(px=100, sz=10), "closedPnl": "wat", "fee": "wat"}]
    e = compute_copy_econ("0xABC", fills)
    assert e.perp_fill_count == 1
    assert e.realized_pnl_usd == pytest.approx(0.0)


# --- ...but fail-safe must not become never-act -----------------------------


def test_a_genuinely_good_leader_still_passes():
    """The other direction of INV 4: the screen must still say YES."""
    e = compute_copy_econ(
        "0xABC", [_fill(px=100, sz=10, closed_pnl=5.0, fee=0.45)], our_taker_bps=4.5
    )
    ok, reason = passes_fee_tier(e)
    assert ok is True
    assert reason == ""


def test_min_net_edge_floor_is_respected_in_both_directions():
    e = compute_copy_econ(
        "0xABC", [_fill(px=100, sz=10, closed_pnl=1.0, fee=0.0)], our_taker_bps=4.5
    )
    assert e.net_edge_bps == pytest.approx(5.5)
    assert passes_fee_tier(e, min_net_edge_bps=5.0)[0] is True
    assert passes_fee_tier(e, min_net_edge_bps=6.0)[0] is False


def test_exactly_at_the_floor_passes():
    e = compute_copy_econ(
        "0xABC", [_fill(px=100, sz=10, closed_pnl=0.45, fee=0.0)], our_taker_bps=4.5
    )
    assert e.net_edge_bps == pytest.approx(0.0)
    assert passes_fee_tier(e, min_net_edge_bps=0.0)[0] is True


def test_zero_lookback_does_not_divide_by_zero():
    e = compute_copy_econ("0xABC", [_fill(px=100, sz=10)], lookback_hours=0.0)
    assert e.turnover_usd_per_mo == pytest.approx(1000.0)
