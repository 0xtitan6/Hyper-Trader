"""Unit tests for the passive-hedge decision.

Every case here is either a situation that cost real money, or an invariant
whose violation would. The function is pure so these can be exhaustive.
"""
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "pair_minder", Path(__file__).resolve().parent.parent / "scripts" / "pair_minder.py")
pm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm)

D = pm.hedge_decision
TARGET = pm.HEDGE_TARGET_TOTAL
MAXC = pm.MAX_PAIR_COST


# --- the two fills that actually cost us money on 2026-09-21 ---------------

def test_regression_croatia_would_have_been_profitable():
    """Real fill: held Croatia NO at 0.57422, minder crossed at 0.42790 for a
    basket of 1.00212 — a locked -0.21%. Five days to kickoff, so there was no
    reason to pay that spread."""
    d = D(paid=0.57422, bid=0.42000, ask=0.42790,
          hours_to_event=120.0, position_age_h=0.1, resting_px=None)
    assert d["action"] == "REST"
    assert 0.57422 + d["px"] <= TARGET + 1e-9
    assert d["px"] < 0.42790, "must rest BELOW the ask it used to cross"


def test_regression_giants_would_have_been_profitable():
    """Real fill: held Giants NO at 0.72818, crossed at 0.28238 => 1.01056,
    a locked -1.06%."""
    d = D(paid=0.72818, bid=0.27500, ask=0.28238,
          hours_to_event=14.0, position_age_h=0.1, resting_px=None)
    assert d["action"] == "REST"
    assert 0.72818 + d["px"] <= TARGET + 1e-9


# --- positive cases --------------------------------------------------------

def test_cross_when_ask_is_already_cheap_enough():
    """If taking the ask still clears the target, immediacy is free."""
    d = D(paid=0.40, bid=0.58, ask=0.59, hours_to_event=100.0,
          position_age_h=0.1, resting_px=None)
    assert d["action"] == "CROSS"
    assert d["px"] == 0.59
    assert 0.40 + 0.59 <= TARGET


def test_keep_an_existing_correct_passive_hedge():
    """Do not churn a good resting order — cancelling loses queue position."""
    d = D(paid=0.57422, bid=0.42, ask=0.4279, hours_to_event=120.0,
          position_age_h=2.0, resting_px=0.42000)
    assert d["action"] == "KEEP"


def test_cross_near_kickoff_when_cost_is_tolerable():
    """Inside the deadline a naked leg is the bigger risk; complete it."""
    d = D(paid=0.57422, bid=0.42, ask=0.43, hours_to_event=1.0,
          position_age_h=5.0, resting_px=None)
    assert d["action"] == "CROSS"
    assert d["px"] == 0.43


def test_cross_when_position_has_aged_out():
    """A passive hedge that never fills must not ride forever."""
    d = D(paid=0.50, bid=0.49, ask=0.51, hours_to_event=200.0,
          position_age_h=pm.PASSIVE_MAX_H + 1, resting_px=None)
    assert d["action"] == "CROSS"


# --- negative cases --------------------------------------------------------

def test_hold_when_crossing_would_lock_a_big_loss():
    """Near kickoff AND expensive: locking >2% is worse than the coin flip."""
    d = D(paid=0.80, bid=0.25, ask=0.30, hours_to_event=0.5,
          position_age_h=1.0, resting_px=None)
    assert d["action"] == "HOLD"
    assert 0.80 + 0.30 > MAXC


def test_hold_when_no_passive_price_exists():
    """Paid more than the whole target basket: there is no bid that profits."""
    d = D(paid=0.998, bid=0.001, ask=0.05, hours_to_event=100.0,
          position_age_h=1.0, resting_px=None)
    assert d["action"] == "HOLD"


def test_rest_price_is_never_above_the_ask():
    """A 'passive' bid at or above the ask would cross — becoming the taker
    fill this whole change exists to avoid."""
    for paid in (0.10, 0.30, 0.50, 0.70):
        for ask in (0.05, 0.20, 0.45, 0.80):
            d = D(paid=paid, bid=ask - 0.01, ask=ask,
                  hours_to_event=100.0, position_age_h=0.1, resting_px=None)
            if d["action"] == "REST":
                assert d["px"] < ask, f"rest {d['px']} >= ask {ask}"


def test_rest_price_is_never_negative_or_dust():
    for paid in (0.90, 0.95, 0.99, 0.995, 1.05):
        d = D(paid=paid, bid=0.001, ask=0.02, hours_to_event=100.0,
              position_age_h=0.1, resting_px=None)
        if d["action"] == "REST":
            assert d["px"] >= pm.MIN_HEDGE_PX


def test_stale_resting_price_above_target_is_repriced():
    """A resting hedge too expensive to profit must be replaced, not kept."""
    d = D(paid=0.57422, bid=0.42, ask=0.4279, hours_to_event=120.0,
          position_age_h=2.0, resting_px=0.49)     # 0.57422+0.49 = 1.064
    assert d["action"] == "REST"


# --- invariants ------------------------------------------------------------

def test_cross_is_only_ever_profitable_or_forced():
    """Sweep the space: any CROSS must either clear the target, or be explained
    by the clock. A silent unprofitable cross is the original bug."""
    for paid in [i / 20 for i in range(1, 20)]:
        for ask in [i / 20 for i in range(1, 20)]:
            for hrs in (0.5, 3.0, 10.0, 100.0):
                for age in (0.1, 30.0):
                    d = D(paid=paid, bid=max(ask - 0.02, 0.001), ask=ask,
                          hours_to_event=hrs, position_age_h=age, resting_px=None)
                    if d["action"] != "CROSS":
                        continue
                    profitable = paid + ask <= TARGET + 1e-9
                    forced = hrs < pm.CROSS_DEADLINE_H or age > pm.PASSIVE_MAX_H
                    assert profitable or forced, \
                        f"unforced losing cross: paid={paid} ask={ask} hrs={hrs}"


def test_rest_always_clears_the_target_basket():
    for paid in [i / 20 for i in range(1, 19)]:
        d = D(paid=paid, bid=0.30, ask=0.45, hours_to_event=100.0,
              position_age_h=1.0, resting_px=None)
        if d["action"] == "REST":
            assert paid + d["px"] <= TARGET + 1e-9


def test_no_event_time_still_decides():
    """Markets with no parseable kickoff must not crash the minder."""
    d = D(paid=0.5, bid=0.4, ask=0.48, hours_to_event=None,
          position_age_h=1.0, resting_px=None)
    assert d["action"] in ("REST", "CROSS", "HOLD", "KEEP")
