"""Regression tests for the maker shadow harness (src/maker_shadow.py).

BACKLOG P0 (2026-08-17, top item): the maker on wip/maker-hip4 has never
run live. Before it does, it must be measured, and a *naive* market-maker
backtest is worse than no backtest because it self-flatters in three
specific ways:

  1. Fill on touch: assumes every trade at our price fills us — invents PnL.
  2. Ignores adverse selection: books the spread and stops. In tokenized
     equities the wide spread may exist BECAUSE the flow is toxic (someone
     arbing the real stock against a stale perp oracle), so mark-outs are
     the only test that distinguishes "wide spread" from "wide spread for
     a reason".
  3. Ignores fees: HIP-3 measured 0.86 bps r/t, base 4.32 bps. Tier 0 has
     no rebate.

Each test below FAILS without the corresponding piece of the harness:
these are the exact self-flatteries the naive harness would exhibit.
"""

from __future__ import annotations

import math

from src.maker_shadow import (
    BASE_ROUND_TRIP_BPS,
    HIP3_ROUND_TRIP_BPS,
    MARKOUT_REPORTING_HORIZON_S,
    MIN_SAMPLE_FOR_CONCLUSION,
    ShadowSimulator,
)


def _bid_ask(sim: ShadowSimulator, mid: float, spread: float, size: float, queue: float, ts: float = 0.0):
    """Post a symmetric bid/ask around `mid` with `spread` and record the
    mid so mark-outs have a baseline."""
    sim.on_mid(ts, mid)
    sim.record_quote(ts, "B", px=mid - spread / 2, size=size, queue_ahead=queue)
    sim.record_quote(ts, "A", px=mid + spread / 2, size=size, queue_ahead=queue)


# ---------- criterion 2: fill requires crossing, not touching ----------


def test_naive_fill_on_touch_is_refused():
    """Failure mode 1: A trade at our exact quote price is NOT a fill. A
    naive backtest fills you on touch; that overstates fill rate. Requires
    the trade to CROSS."""
    sim = ShadowSimulator("#20", is_hip3=True)
    _bid_ask(sim, mid=0.50, spread=0.03, size=1.0, queue=0.0)
    # Buy aggressor at exactly our ask — a naive harness fills us. We do not.
    sim.on_trade(ts=0.5, aggressor_side="B", px=0.515 - 1e-9, size=10.0)
    assert sim.fills == [], "quote should not fill on strictly-below-ask trade"


def test_cross_at_ask_fills_when_queue_empty():
    sim = ShadowSimulator("#20", is_hip3=True)
    _bid_ask(sim, mid=0.50, spread=0.03, size=1.0, queue=0.0)
    sim.on_trade(ts=0.5, aggressor_side="B", px=0.515, size=10.0)
    assert len(sim.fills) == 1
    f = sim.fills[0]
    assert f.side == "A" and f.px == 0.515 and f.size == 1.0


def test_cross_at_bid_fills_when_queue_empty():
    sim = ShadowSimulator("#20", is_hip3=True)
    _bid_ask(sim, mid=0.50, spread=0.03, size=1.0, queue=0.0)
    sim.on_trade(ts=0.5, aggressor_side="A", px=0.485, size=10.0)
    assert len(sim.fills) == 1
    f = sim.fills[0]
    assert f.side == "B" and f.px == 0.485 and f.size == 1.0


# ---------- criterion 2 (queue): pessimistic last-in-queue ----------


def test_pessimistic_queue_delays_fill():
    """Failure mode 1b: assuming zero queue-ahead flatters fills. Real queue
    means the first N units of aggressor volume clear resting size ahead of
    us. Only when that is exhausted do WE get filled."""
    sim = ShadowSimulator("#20", is_hip3=True)
    _bid_ask(sim, mid=0.50, spread=0.03, size=1.0, queue=5.0)
    # 4 units cross — not enough to reach us
    sim.on_trade(ts=0.5, aggressor_side="B", px=0.52, size=4.0)
    assert sim.fills == [], "4 of 5 queue-ahead should not reach us"
    # 2 more units — queue exhausted, we fill for our size
    sim.on_trade(ts=0.6, aggressor_side="B", px=0.52, size=2.0)
    assert len(sim.fills) == 1
    assert sim.fills[0].size == 1.0


# ---------- criterion 3: mark-outs signed so positive = our way ----------


def test_markout_positive_when_market_moves_our_way_on_sell():
    """We sold at 0.515 (ask). Mid then FELL to 0.505 — good for us. Signed
    mark-out must be POSITIVE."""
    sim = ShadowSimulator("#20", is_hip3=True)
    _bid_ask(sim, mid=0.50, spread=0.03, size=1.0, queue=0.0, ts=0.0)
    sim.on_trade(ts=0.5, aggressor_side="B", px=0.515, size=1.0)
    sim.on_mid(ts=10.5, mid=0.495)  # mid dropped 5c after our sell
    f = sim.fills[0]
    assert MARKOUT_REPORTING_HORIZON_S in f.markouts
    # move = 0.495 - 0.50 = -0.005; side A → signed = +0.005
    assert math.isclose(f.markouts[MARKOUT_REPORTING_HORIZON_S], 0.005, rel_tol=1e-9)


def test_markout_negative_when_market_moves_against_us_on_buy():
    """We bought at 0.485 (bid). Mid then FELL to 0.475 — bad for us. Signed
    mark-out must be NEGATIVE. This is the failure mode a naive harness
    ignores."""
    sim = ShadowSimulator("#20", is_hip3=True)
    _bid_ask(sim, mid=0.50, spread=0.03, size=1.0, queue=0.0, ts=0.0)
    sim.on_trade(ts=0.5, aggressor_side="A", px=0.485, size=1.0)
    sim.on_mid(ts=10.5, mid=0.475)
    f = sim.fills[0]
    assert f.markouts[MARKOUT_REPORTING_HORIZON_S] < 0


# ---------- criterion 4: net edge = spread + markout − REAL fee ----------


def test_net_edge_uses_hip3_fee_when_is_hip3():
    sim = ShadowSimulator("#20", is_hip3=True)
    assert sim.fee_bps() == HIP3_ROUND_TRIP_BPS


def test_net_edge_uses_base_fee_when_not_hip3():
    sim = ShadowSimulator("BTC", is_hip3=False)
    assert sim.fee_bps() == BASE_ROUND_TRIP_BPS


def test_net_edge_math_matches_formula():
    """For a sell filled at ask with mid returning to entry, net edge in bps
    = 10_000 * (px - mid_at_fill) / mid_at_fill - fee. Any deviation means
    the harness is double-counting or missing a component."""
    sim = ShadowSimulator("#20", is_hip3=True)
    _bid_ask(sim, mid=0.50, spread=0.02, size=1.0, queue=0.0, ts=0.0)
    sim.on_trade(ts=0.5, aggressor_side="B", px=0.51, size=1.0)  # we sell at 0.51
    sim.on_mid(ts=10.5, mid=0.50)  # mid unchanged → zero markout
    f = sim.fills[0]
    got = sim.net_edge_per_fill_bps(f)
    expected = 1e4 * (0.51 - 0.50) / 0.50 - HIP3_ROUND_TRIP_BPS  # 200bps - 0.86
    assert got is not None
    assert math.isclose(got, expected, rel_tol=1e-9)


def test_adverse_selection_subtracts_from_edge():
    """Same trade but mid moves 20 bps AGAINST our sell (mid up to 0.501).
    Net edge must DROP by ~20 bps. A naive harness that books only spread
    would report the same 199.14 bps as the flat-mid case — that's the
    exact self-flattery this test guards."""
    sim = ShadowSimulator("#20", is_hip3=True)
    _bid_ask(sim, mid=0.50, spread=0.02, size=1.0, queue=0.0, ts=0.0)
    sim.on_trade(ts=0.5, aggressor_side="B", px=0.51, size=1.0)
    sim.on_mid(ts=10.5, mid=0.501)  # mid up = adverse for sell
    f = sim.fills[0]
    got = sim.net_edge_per_fill_bps(f)
    expected = 1e4 * (0.51 - 0.501) / 0.50 - HIP3_ROUND_TRIP_BPS
    assert got is not None
    assert math.isclose(got, expected, rel_tol=1e-9)


def test_edge_is_none_until_reporting_horizon_elapses():
    """Realized-only per INV 10: don't count a fill until its mark-out
    horizon has actually elapsed."""
    sim = ShadowSimulator("#20", is_hip3=True)
    _bid_ask(sim, mid=0.50, spread=0.02, size=1.0, queue=0.0, ts=0.0)
    sim.on_trade(ts=0.5, aggressor_side="B", px=0.51, size=1.0)
    sim.on_mid(ts=2.0, mid=0.50)  # only 1.5s later — 10s horizon not settled
    assert sim.net_edge_per_fill_bps(sim.fills[0]) is None


# ---------- criterion 5: inventory tracking + cap-hit count ----------


def test_inventory_reflects_buys_and_sells():
    sim = ShadowSimulator("#20", is_hip3=True)
    _bid_ask(sim, mid=0.50, spread=0.02, size=1.0, queue=0.0, ts=0.0)
    sim.on_trade(ts=0.5, aggressor_side="A", px=0.49, size=1.0)  # we buy 1
    assert sim.inventory == 1.0
    _bid_ask(sim, mid=0.50, spread=0.02, size=1.0, queue=0.0, ts=1.0)
    sim.on_trade(ts=1.5, aggressor_side="B", px=0.51, size=1.0)  # we sell 1
    assert sim.inventory == 0.0


def test_inventory_cap_hits_counted():
    sim = ShadowSimulator("#20", is_hip3=True)
    sim.set_inventory_cap(1.0)
    _bid_ask(sim, mid=0.50, spread=0.02, size=1.0, queue=0.0, ts=0.0)
    sim.on_trade(ts=0.5, aggressor_side="A", px=0.49, size=1.0)
    assert sim.inventory == 1.0
    rep = sim.report()
    assert rep["inventory_cap_hits"] >= 1


# ---------- criterion 6: realized report shape (n, mean, SE, YES/NO) ----------


def test_report_below_min_sample_returns_no_conclusion():
    sim = ShadowSimulator("#20", is_hip3=True)
    _bid_ask(sim, mid=0.50, spread=0.02, size=1.0, queue=0.0, ts=0.0)
    sim.on_trade(ts=0.5, aggressor_side="B", px=0.51, size=1.0)
    sim.on_mid(ts=10.5, mid=0.50)
    rep = sim.report()
    assert rep["n_realized"] == 1
    assert "NO" in rep["conclusion_yes_no"]
    assert str(MIN_SAMPLE_FOR_CONCLUSION) in rep["conclusion_yes_no"]


def test_report_shape_contains_required_fields():
    """Report must carry n, mean, SE, YES/NO, real fee, queue assumption,
    reporting horizon. Missing any = we shipped an unusable report."""
    sim = ShadowSimulator("#20", is_hip3=True)
    rep = sim.report()
    required = {
        "n_shadow_fills",
        "n_realized",
        "mean_net_edge_bps",
        "stderr_bps",
        "significance_z",
        "conclusion_yes_no",
        "fee_round_trip_bps",
        "reporting_horizon_s",
        "queue_assumption",
        "markouts_bps",
        "max_abs_inventory",
        "time_weighted_avg_abs_inventory",
        "inventory_cap_hits",
    }
    missing = required - set(rep)
    assert missing == set(), f"report missing keys: {missing}"


def test_report_states_queue_assumption_explicitly():
    """Acceptance criterion 2: 'State the queue assumption explicitly in
    the output; it is the single biggest source of self-flattery.'"""
    sim = ShadowSimulator("#20", is_hip3=True)
    rep = sim.report()
    assert "last-in-queue" in rep["queue_assumption"]
    assert "queue_ahead" in rep["queue_assumption"]


def test_report_markouts_all_three_horizons():
    sim = ShadowSimulator("#20", is_hip3=True)
    rep = sim.report()
    for h in ("1s", "10s", "60s"):
        assert h in rep["markouts_bps"], f"missing markout bucket {h}"


def test_significance_conclusion_yes_when_sample_positive():
    """With enough samples and |mean|/SE > 2, we should call YES. Uses
    engineered fills to reach the threshold."""
    sim = ShadowSimulator("#20", is_hip3=True)
    # produce >= MIN_SAMPLE_FOR_CONCLUSION independent positive fills
    for i in range(MIN_SAMPLE_FOR_CONCLUSION + 5):
        t = float(i * 100)
        _bid_ask(sim, mid=0.50, spread=0.10, size=1.0, queue=0.0, ts=t)
        # we sell at 0.55; mid stays flat → +1000bps spread capture,
        # net well above zero after 0.86bps fee
        sim.on_trade(ts=t + 0.5, aggressor_side="B", px=0.55, size=1.0)
        sim.on_mid(ts=t + 10.5, mid=0.50)
    rep = sim.report()
    assert rep["n_realized"] >= MIN_SAMPLE_FOR_CONCLUSION
    assert rep["conclusion_yes_no"].startswith("YES")
    assert rep["mean_net_edge_bps"] > 0
