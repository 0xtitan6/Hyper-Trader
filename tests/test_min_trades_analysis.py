"""Tests for scripts/min_trades_analysis.py — the min_trades dry-run screen.

The script itself is read-only analysis, but `screen()` reproduces
`src/leaders.discover_leaders`'s decision order. If the reproduction drifts,
the recommendation describes a selection process the bot does not actually run,
which is worse than no analysis at all. These tests pin the order and the
fail-open behaviour.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from scripts.min_trades_analysis import Candidate, screen
from src.config import DiscoveryConfig
from src.copy_econ import compute_copy_econ
from src.leader_score import _compute_metrics
from src.liquidiction import Trader


def _cfg(**over) -> SimpleNamespace:
    """Stand-in for `Config`, carrying the live config.yaml discovery values.

    `screen()` reads `cfg.discovery` and nothing else, and the real `Config` is
    a frozen dataclass requiring a private key and five other sections. A
    namespace keeps these tests about the screening logic rather than about
    constructing a credentialed config object.
    """
    defaults = {
        "period": "30d",
        "top_n": 4,
        "min_trades": 50,
        "min_volume_usd": 5000.0,
        "min_pnl_usd": 100.0,
        "refresh_seconds": 600,
        "score_lookback_hours": 720.0,
        "min_holding_time_s": 120.0,
        "min_perp_fraction": 0.5,
        "min_leader_equity_usd": 500.0,
        "use_quality_filter": True,
        "score_perp_only": True,
    }
    return SimpleNamespace(discovery=DiscoveryConfig(**{**defaults, **over}))


def _fills(n: int, *, gap_s: float, px: float, sz: float, pnl: float, fee: float, coin="BTC"):
    """n perp fills `gap_s` apart, alternating nothing (pure directional)."""
    t0 = 1_700_000_000_000
    return [
        {
            "coin": coin,
            "px": str(px),
            "sz": str(sz),
            "closedPnl": str(pnl),
            "fee": str(fee),
            "crossed": True,
            "feeToken": "USDC",
            "side": "B",
            "time": t0 + int(i * gap_s * 1000),
        }
        for i in range(n)
    ]


def _cand(
    *,
    lb_trades: int = 100,
    lb_volume: float = 1_000_000.0,
    lb_pnl: float = 10_000.0,
    equity: float | None = 50_000.0,
    n_fills: int = 100,
    gap_s: float = 3600.0,
    pnl_per_fill: float = 5.0,
    fee_per_fill: float = 0.45,
    px: float = 100.0,
    sz: float = 10.0,
    coin: str = "BTC",
) -> Candidate:
    fills = _fills(
        n_fills, gap_s=gap_s, px=px, sz=sz, pnl=pnl_per_fill, fee=fee_per_fill, coin=coin
    )
    t = Trader(address="0xAAA", rank=1, pnl=lb_pnl, trades=lb_trades, volume=lb_volume)
    return Candidate(
        trader=t,
        metrics=_compute_metrics(address=t.address, lookback_hours=720.0, fills=fills),
        econ=compute_copy_econ(t.address, fills, lookback_hours=720.0, our_taker_bps=4.5),
        equity_usd=equity,
        unrealized_pnl_usd=0.0,
        leverage_notional_usd=0.0,
    )


# --- the happy path ---------------------------------------------------------


def test_a_solvent_profitable_low_frequency_leader_is_selected():
    ok, reason = screen(_cand(), _cfg(), 50, 0.0)
    assert ok is True, reason
    assert reason == ""


# --- the screen order (each rejection names ITSELF — INV 5) -----------------


def test_coarse_trade_count_rejects_below_threshold_and_admits_at_it():
    c = _cand(lb_trades=43)
    ok, reason = screen(c, _cfg(), 50, 0.0)
    assert ok is False
    assert reason == "coarse_trades=43 < 50"
    # ...and the SAME wallet passes once the threshold drops. This is the exact
    # candidate the backlog item is about: 43 trades/30d, auto-rejected at 50.
    assert screen(c, _cfg(), 30, 0.0)[0] is True
    assert screen(c, _cfg(), 20, 0.0)[0] is True


def test_coarse_volume_and_pnl_have_their_own_reasons():
    ok, reason = screen(_cand(lb_volume=100.0), _cfg(), 50, 0.0)
    assert ok is False and reason.startswith("coarse_volume=")
    ok, reason = screen(_cand(lb_pnl=1.0), _cfg(), 50, 0.0)
    assert ok is False and reason.startswith("coarse_pnl=")


def test_insolvent_leader_is_rejected_by_the_solvency_gate():
    """INV 9 / 2026-08-15: a leaderboard rank is history, not a balance.

    (The old "44 of the top 60 hold $0 equity" figure was a base-dex-only
    artifact — INV 1, see P0c. `equity` now reads every clearinghouse.)
    """
    ok, reason = screen(_cand(equity=12.0), _cfg(min_leader_equity_usd=500.0), 50, 0.0)
    assert ok is False
    assert reason == "equity=$12 < $500"


def test_unreadable_equity_fails_OPEN_and_does_not_disqualify():
    """INV 4: None means we did not measure it, not that they have nothing.

    `src/leaders._perp_equity_usd` takes the same stance; if this diverged, the
    analysis would report a leader as rejected whom the live bot would select.
    """
    ok, reason = screen(_cand(equity=None), _cfg(min_leader_equity_usd=500.0), 50, 0.0)
    assert ok is True, reason


def test_scalper_is_rejected_by_the_turnover_screen():
    # 5s median gap, far under min_holding_time_s=120.
    ok, reason = screen(_cand(gap_s=5.0), _cfg(min_holding_time_s=120.0), 50, 0.0)
    assert ok is False
    assert "holding_p50" in reason


def test_quality_trade_count_uses_hl_fills_not_the_leaderboard_number():
    """The same config number is applied to two different quantities.

    Leaderboard says 100 trades; HL fills say 10. `meets_quality` must reject
    on the HL number — otherwise a wallet whose leaderboard count is stale
    sails through a filter that thinks it checked something.
    """
    c = _cand(lb_trades=100, n_fills=10)
    ok, reason = screen(c, _cfg(), 50, 0.0)
    assert ok is False
    assert reason == "trades=10 < 50"


def test_fee_tier_screen_rejects_a_leader_who_is_profitable_only_at_their_tier():
    # $100k per fill of turnover, $20 net, 0.5 bps of fees => 2.5 bps gross,
    # which is under our 4.5 bps taker.
    c = _cand(px=1000.0, sz=100.0, pnl_per_fill=20.0, fee_per_fill=5.0)
    assert c.econ is not None and c.econ.net_edge_bps == pytest.approx(-2.0)
    ok, reason = screen(c, _cfg(), 50, 0.0)
    assert ok is False
    assert reason.startswith("net_edge=-2.00bps")


def test_fee_tier_screen_runs_LAST_so_cheaper_screens_report_first():
    """A wallet failing several screens must report the cheapest one.

    Otherwise the rejection histogram blames the fee tier for wallets that
    never got that far, and the recommendation reads the wrong binding
    constraint.
    """
    c = _cand(lb_trades=1, px=1000.0, sz=100.0, pnl_per_fill=20.0, fee_per_fill=5.0)
    assert screen(c, _cfg(), 50, 0.0)[1] == "coarse_trades=1 < 50"


def test_missing_metrics_or_econ_are_rejected_with_their_own_reason():
    c = _cand()
    assert screen(replace(c, metrics=None), _cfg(), 50, 0.0)[1] == "metrics_unavailable"
    assert screen(replace(c, econ=None), _cfg(), 50, 0.0)[1] == "econ_unavailable"


def test_outcome_only_leader_is_rejected_before_the_econ_screen():
    """A wallet with no perp flow has unknown perp economics (INV 4).

    It is rejected by `min_perp_fraction` first, which is the more informative
    reason; it must never be admitted just because econ was unmeasurable.
    """
    c = _cand(coin="#2120", px=0.5, sz=1000.0)
    ok, reason = screen(c, _cfg(min_perp_fraction=0.5), 50, 0.0)
    assert ok is False
    assert "perp_frac" in reason


def test_min_net_edge_floor_tightens_the_fee_tier_screen():
    c = _cand(pnl_per_fill=5.0, fee_per_fill=0.45)  # net_edge = +50.0 bps
    assert screen(c, _cfg(), 50, 0.0)[0] is True
    assert screen(c, _cfg(), 50, 100.0)[0] is False
