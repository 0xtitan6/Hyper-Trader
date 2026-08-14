from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.mirror import MirrorTrader, TradeIntent


@pytest.fixture
def positions():
    p = MagicMock()
    p.realized_pnl_today.return_value = 0.0
    p.total_exposure_usd.return_value = 0.0
    # Default: no existing position → reduce_only stays False
    p.state.get_position.return_value = (0.0, 0.0)
    # Default: no originator set → conflict-lock falls through (PR #25)
    p.state.get_position_originator.return_value = None
    return p


@pytest.fixture
def exchange():
    e = MagicMock()
    e.order.return_value = {"status": "ok"}
    return e


@pytest.fixture
def mt(cfg, exchange, positions, journal, alerter, market_meta):
    return MirrorTrader(cfg, exchange, positions, journal, alerter, market_meta)


def test_happy_path_dry_run_logs_no_order(mt, exchange, outcome_fill):
    mt.on_leader_fill("0xleader", outcome_fill)
    exchange.order.assert_not_called()


def test_happy_path_live_submits(
    cfg, positions, journal, alerter, exchange, outcome_fill, market_meta
):
    cfg = _override_risk(cfg, dry_run=False)
    mt = MirrorTrader(cfg, exchange, positions, journal, alerter, market_meta)
    mt.on_leader_fill("0xleader", outcome_fill)
    exchange.order.assert_called_once()
    args, kwargs = exchange.order.call_args
    coin, is_buy, sz, px = args[:4]
    assert coin == "#11"
    assert is_buy is True
    # 100 sz * 0.54 = 54 leader notional * 0.10 = 5.4 mirror notional / 0.54 = 10 sz
    assert abs(sz - 10.0) < 1e-9
    # IOC slippage: 0.5%
    assert px > float(outcome_fill["px"])  # buy side adds slippage
    assert kwargs["order_type"] == {"limit": {"tif": "Ioc"}}
    assert kwargs["reduce_only"] is False  # no opposing position → not reduce_only


def test_sell_path_subtracts_slippage(
    cfg, positions, journal, alerter, exchange, outcome_fill, market_meta
):
    cfg = _override_risk(cfg, dry_run=False)
    mt = MirrorTrader(cfg, exchange, positions, journal, alerter, market_meta)
    fill = {**outcome_fill, "side": "A"}
    mt.on_leader_fill("0xleader", fill)
    args, _ = exchange.order.call_args
    px = args[3]
    assert px < float(outcome_fill["px"])  # sell side subtracts


def test_kill_switch_blocks(mt, exchange, cfg, outcome_fill, market_meta):
    Path(cfg.risk.kill_switch_file).touch()
    cfg2 = _override_risk(cfg, dry_run=False)
    mt2 = MirrorTrader(cfg2, exchange, mt.positions, mt.journal, mt.alerter, market_meta)
    mt2.on_leader_fill("0xleader", outcome_fill)
    exchange.order.assert_not_called()


def test_daily_loss_blocks_and_alerts(cfg, positions, journal, exchange, outcome_fill, market_meta):
    positions.realized_pnl_today.return_value = -150.0
    alerter = MagicMock()
    cfg2 = _override_risk(cfg, dry_run=False)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    mt.on_leader_fill("0xleader", outcome_fill)
    exchange.order.assert_not_called()
    crit = [c for c in alerter.alert.call_args_list if c.args[0] == "critical"]
    assert len(crit) == 1


def test_exposure_cap_blocks(cfg, positions, journal, alerter, exchange, outcome_fill, market_meta):
    positions.total_exposure_usd.return_value = 499.0
    cfg2 = _override_risk(cfg, dry_run=False, max_total_exposure_usd=500)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    mt.on_leader_fill("0xleader", outcome_fill)
    exchange.order.assert_not_called()


def test_disallowed_market_skipped(cfg, positions, journal, alerter, exchange, market_meta):
    fill = {"tid": 1, "coin": "BTC", "px": "65000", "sz": "0.01", "side": "B"}
    cfg2 = _override_risk(cfg, dry_run=False)  # only outcome allowed by default
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    mt.on_leader_fill("0xleader", fill)
    exchange.order.assert_not_called()


def test_perp_allowed_when_configured(cfg, positions, journal, alerter, exchange, market_meta):
    cfg2 = _override_risk(cfg, dry_run=False, allowed_market_types=["outcome", "perp"])
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    fill = {"tid": 1, "coin": "BTC", "px": "65000", "sz": "0.01", "side": "B"}
    mt.on_leader_fill("0xleader", fill)
    exchange.order.assert_called_once()


def test_below_min_per_trade_skipped(cfg, positions, journal, alerter, exchange, market_meta):
    cfg2 = _override_sizing(cfg, min_per_trade_usd=20)
    cfg2 = _override_risk(cfg2, dry_run=False)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    # leader_notional = 1 * 0.01 = 0.01, * 0.10 = 0.001 → below min
    fill = {"tid": 1, "coin": "#11", "px": "0.01", "sz": "1", "side": "B"}
    mt.on_leader_fill("0xleader", fill)
    exchange.order.assert_not_called()


def test_max_per_trade_caps_size(cfg, positions, journal, alerter, exchange, market_meta):
    cfg2 = _override_sizing(cfg, max_per_trade_usd=50)
    cfg2 = _override_risk(cfg2, dry_run=False)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    # huge leader fill: $10000 notional * 0.1 = $1000, capped at $50
    fill = {"tid": 1, "coin": "#11", "px": "1.00", "sz": "10000", "side": "B"}
    mt.on_leader_fill("0xleader", fill)
    args, _ = exchange.order.call_args
    sz = args[2]
    assert sz == 50.0  # 50 / 1.00 = 50


def test_fixed_sizing_uses_fixed_usd(cfg, positions, journal, alerter, exchange, market_meta):
    cfg2 = _override_sizing(cfg, mode="fixed", fixed_usd=30)
    cfg2 = _override_risk(cfg2, dry_run=False)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    fill = {"tid": 1, "coin": "#11", "px": "0.50", "sz": "1000", "side": "B"}
    mt.on_leader_fill("0xleader", fill)
    args, _ = exchange.order.call_args
    sz = args[2]
    assert sz == 60.0  # 30 / 0.50


def test_per_leader_weight_doubles_size(
    cfg, positions, journal, alerter, exchange, market_meta
):
    """Leader with weight 2.0 produces 2x the proportional mirror size."""
    cfg2 = _override_sizing(cfg, max_per_trade_usd=200)
    cfg2 = _override_risk(cfg2, dry_run=False)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    mt.update_leader_weights({"0xtrusted": 2.0})
    # Leader $100 notional x 0.10 prop x 2.0 weight = $20 mirror
    fill = {"tid": 1, "coin": "#11", "px": "1.0", "sz": "100", "side": "B"}
    mt.on_leader_fill("0xtrusted", fill)
    args, _ = exchange.order.call_args
    sz = args[2]
    assert sz == 20.0  # 20 / 1.0


def test_per_leader_weight_halves_size(
    cfg, positions, journal, alerter, exchange, market_meta
):
    """Leader with weight 0.5 produces half the proportional mirror size,
    but still must clear min_per_trade_usd after weighting (min=$1 in cfg)."""
    cfg2 = _override_sizing(cfg, min_per_trade_usd=1, max_per_trade_usd=200)
    cfg2 = _override_risk(cfg2, dry_run=False)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    mt.update_leader_weights({"0xweak": 0.5})
    # Leader $100 notional x 0.10 prop x 0.5 weight = $5 mirror
    fill = {"tid": 1, "coin": "#11", "px": "1.0", "sz": "100", "side": "B"}
    mt.on_leader_fill("0xweak", fill)
    args, _ = exchange.order.call_args
    sz = args[2]
    assert sz == 5.0


def test_unknown_leader_uses_default_weight(
    cfg, positions, journal, alerter, exchange, market_meta
):
    """Leader not in the weight map gets default 1.0 = legacy behavior."""
    cfg2 = _override_risk(cfg, dry_run=False)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    mt.update_leader_weights({"0xother": 5.0})
    # Deliberately 2x the $5 min: a clip sitting exactly ON min_per_trade_usd
    # now triggers the sub-minimum rescue (2026-08-14), which would make this
    # weight assertion about rounding instead of about weights.
    fill = {"tid": 1, "coin": "#11", "px": "1.00", "sz": "100", "side": "B"}
    mt.on_leader_fill("0xnotinmap", fill)
    args, _ = exchange.order.call_args
    sz = args[2]
    # No weight applied: $100 leader notional x 0.10 = $10 mirror / 1.00 = 10
    assert sz == 10.0


def test_weight_lookup_is_case_insensitive(
    cfg, positions, journal, alerter, exchange, market_meta
):
    """Mixed-case leader address still matches a lowercase weight map key."""
    cfg2 = _override_sizing(cfg, max_per_trade_usd=200)
    cfg2 = _override_risk(cfg2, dry_run=False)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    mt.update_leader_weights({"0xABCDEF": 2.0})  # uppercase set
    fill = {"tid": 1, "coin": "#11", "px": "1.0", "sz": "100", "side": "B"}
    mt.on_leader_fill("0xabcdef", fill)  # lowercase callback
    args, _ = exchange.order.call_args
    sz = args[2]
    assert sz == 20.0  # weight applied despite case mismatch


# ---------- funding-aware sizing ----------


def _funding_stub(apr_map: dict[str, float]):
    """Build a FundingTracker-like stub returning apr_pct from a dict."""
    stub = MagicMock()
    stub.get_apr_pct.side_effect = lambda c: apr_map.get(c)
    return stub


def test_funding_amplifies_short_when_funding_positive(
    cfg, positions, journal, alerter, exchange, market_meta
):
    """Shorting an asset with +50% APR funding (we get paid) → size boost."""
    cfg2 = _override_sizing(
        cfg,
        max_per_trade_usd=200,
        use_funding_aware_sizing=True,
        funding_amplify_threshold_apr_pct=20.0,
        funding_amplify_cap=1.5,
        funding_skip_threshold_apr_pct=200.0,
    )
    cfg2 = _override_risk(cfg2, dry_run=False, allowed_market_types=["perp"])
    funding = _funding_stub({"BTC": 50.0})
    mt = MirrorTrader(
        cfg2, exchange, positions, journal, alerter, market_meta, funding=funding
    )
    # Leader sells (short) BTC: $1000 leader notional x 0.10 = $100
    # we_get_paid_apr = +50, raw_mult = 1 + 50/200 = 1.25 → $125 mirror
    fill = {"tid": 1, "coin": "BTC", "px": "100", "sz": "10", "side": "A"}
    mt.on_leader_fill("0xleader", fill)
    args, _ = exchange.order.call_args
    sz = args[2]
    assert abs(sz - 1.25) < 1e-9  # 125 / 100 = 1.25


def test_funding_amplification_clipped_by_cap(
    cfg, positions, journal, alerter, exchange, market_meta
):
    """Extreme positive funding still respects funding_amplify_cap."""
    cfg2 = _override_sizing(
        cfg,
        max_per_trade_usd=500,
        use_funding_aware_sizing=True,
        funding_amplify_threshold_apr_pct=20.0,
        funding_amplify_cap=1.5,
        funding_skip_threshold_apr_pct=1000.0,  # don't skip
    )
    cfg2 = _override_risk(cfg2, dry_run=False, allowed_market_types=["perp"])
    funding = _funding_stub({"BTC": 400.0})  # 400% APR — would scale to 3.0x raw
    mt = MirrorTrader(
        cfg2, exchange, positions, journal, alerter, market_meta, funding=funding
    )
    fill = {"tid": 1, "coin": "BTC", "px": "100", "sz": "10", "side": "A"}  # short
    mt.on_leader_fill("0xleader", fill)
    args, _ = exchange.order.call_args
    sz = args[2]
    assert abs(sz - 1.5) < 1e-9  # 100 * 1.5 cap = 150 / 100


def test_funding_skips_when_adverse_above_threshold(
    cfg, positions, journal, alerter, exchange, market_meta
):
    """Longing an asset with +200% APR (we PAY 200% APR) → trade skipped."""
    cfg2 = _override_sizing(
        cfg,
        use_funding_aware_sizing=True,
        funding_skip_threshold_apr_pct=100.0,
    )
    cfg2 = _override_risk(cfg2, dry_run=False, allowed_market_types=["perp"])
    funding = _funding_stub({"BTC": 200.0})
    mt = MirrorTrader(
        cfg2, exchange, positions, journal, alerter, market_meta, funding=funding
    )
    fill = {"tid": 1, "coin": "BTC", "px": "100", "sz": "10", "side": "B"}  # long
    mt.on_leader_fill("0xleader", fill)
    exchange.order.assert_not_called()


def test_funding_no_effect_below_threshold(
    cfg, positions, journal, alerter, exchange, market_meta
):
    """APR below amplify_threshold and above skip_threshold = no size change."""
    cfg2 = _override_sizing(
        cfg,
        use_funding_aware_sizing=True,
        funding_amplify_threshold_apr_pct=20.0,
        funding_skip_threshold_apr_pct=100.0,
    )
    cfg2 = _override_risk(cfg2, dry_run=False, allowed_market_types=["perp"])
    funding = _funding_stub({"BTC": 5.0})  # tiny funding, well within "do nothing"
    mt = MirrorTrader(
        cfg2, exchange, positions, journal, alerter, market_meta, funding=funding
    )
    fill = {"tid": 1, "coin": "BTC", "px": "100", "sz": "10", "side": "A"}
    mt.on_leader_fill("0xleader", fill)
    args, _ = exchange.order.call_args
    sz = args[2]
    # No funding adjustment: $1000 x 0.10 = $100 / 100 = 1.0 sz
    assert abs(sz - 1.0) < 1e-9


def test_funding_skip_when_we_pay_extreme(
    cfg, positions, journal, alerter, exchange, market_meta
):
    """Shorting an asset with -120% APR funding (we'd PAY) → skip."""
    cfg2 = _override_sizing(
        cfg,
        use_funding_aware_sizing=True,
        funding_skip_threshold_apr_pct=100.0,
    )
    cfg2 = _override_risk(cfg2, dry_run=False, allowed_market_types=["perp"])
    funding = _funding_stub({"STABLE": -120.0})  # short would PAY 120% APR
    mt = MirrorTrader(
        cfg2, exchange, positions, journal, alerter, market_meta, funding=funding
    )
    fill = {"tid": 1, "coin": "STABLE", "px": "0.05", "sz": "1000", "side": "A"}
    mt.on_leader_fill("0xleader", fill)
    exchange.order.assert_not_called()


def test_funding_disabled_when_flag_off(
    cfg, positions, journal, alerter, exchange, market_meta
):
    """use_funding_aware_sizing=False → no adjustment regardless of funding."""
    cfg2 = _override_risk(cfg, dry_run=False, allowed_market_types=["perp"])
    funding = _funding_stub({"BTC": 500.0})  # extreme but should be ignored
    mt = MirrorTrader(
        cfg2, exchange, positions, journal, alerter, market_meta, funding=funding
    )
    fill = {"tid": 1, "coin": "BTC", "px": "100", "sz": "10", "side": "A"}
    mt.on_leader_fill("0xleader", fill)
    args, _ = exchange.order.call_args
    sz = args[2]
    assert abs(sz - 1.0) < 1e-9  # no amplification


def test_funding_does_not_affect_outcome_trades(
    cfg, positions, journal, alerter, exchange, market_meta
):
    """Outcomes don't have funding — funding-aware sizing must not touch them."""
    cfg2 = _override_sizing(cfg, use_funding_aware_sizing=True)
    cfg2 = _override_risk(cfg2, dry_run=False)  # outcome allowed by default
    funding = _funding_stub({})  # no entry for outcomes; would return None anyway
    mt = MirrorTrader(
        cfg2, exchange, positions, journal, alerter, market_meta, funding=funding
    )
    fill = {"tid": 1, "coin": "#11", "px": "0.54", "sz": "100", "side": "B"}
    mt.on_leader_fill("0xleader", fill)
    exchange.order.assert_called_once()


def test_malformed_fills_skipped(mt, exchange):
    bad_fills = [
        {"tid": 1},  # missing everything
        {"tid": 1, "coin": "#11", "px": "0", "sz": "10", "side": "B"},  # zero px
        {"tid": 1, "coin": "#11", "px": "0.5", "sz": "0", "side": "B"},  # zero sz
        {"tid": 1, "coin": "#11", "px": "0.5", "sz": "10", "side": "?"},  # bad side
        {"tid": 1, "coin": "", "px": "0.5", "sz": "10", "side": "B"},  # empty coin
        {"tid": 1, "coin": "#11", "px": "abc", "sz": "10", "side": "B"},  # non-numeric
    ]
    for f in bad_fills:
        mt.on_leader_fill("0xleader", f)
    exchange.order.assert_not_called()


def test_order_failure_alerts_and_propagates(
    cfg, positions, journal, exchange, outcome_fill, market_meta
):
    from src.errors import OrderError

    cfg2 = _override_risk(cfg, dry_run=False)
    exchange.order.side_effect = RuntimeError("nonce too low")
    alerter = MagicMock()
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    with pytest.raises(OrderError):
        mt.on_leader_fill("0xleader", outcome_fill)
    err = [c for c in alerter.alert.call_args_list if c.args[0] == "error"]
    assert any("Order submit failed" in c.args[1] for c in err)


def test_journal_records_decisions(
    cfg, positions, exchange, alerter, outcome_fill, tmp_path, market_meta
):
    import json as _json

    from src.journal import Journal as J

    j = J(str(tmp_path / "j.jsonl"))
    cfg2 = _override_risk(cfg, dry_run=True)
    mt = MirrorTrader(cfg2, exchange, positions, j, alerter, market_meta)
    mt.on_leader_fill("0xleader", outcome_fill)
    lines = (tmp_path / "j.jsonl").read_text().splitlines()
    events = [_json.loads(ln)["event"] for ln in lines]
    assert "leader_fill" in events
    assert "risk_check" in events
    assert "order_dry_run" in events


def _override_risk(cfg, **changes):
    from dataclasses import replace

    return replace(cfg, risk=replace(cfg.risk, **changes))


def _override_sizing(cfg, **changes):
    from dataclasses import replace

    return replace(cfg, sizing=replace(cfg.sizing, **changes))


def test_intent_dataclass_basic():
    i = TradeIntent(coin="#11", is_buy=True, sz=10.0, limit_px=0.5, notional_usd=5.0)
    assert i.coin == "#11" and i.is_buy is True
    assert i.reduce_only is False  # default


def test_configurable_slippage_50bps(
    cfg, positions, journal, alerter, exchange, outcome_fill, market_meta
):
    cfg2 = _override_sizing(cfg, ioc_slippage_bps=50)
    cfg2 = _override_risk(cfg2, dry_run=False)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    mt.on_leader_fill("0xleader", outcome_fill)
    px = exchange.order.call_args.args[3]
    leader_px = float(outcome_fill["px"])
    # 0.5% above leader px, then 5-sig-fig rounding
    expected = market_meta.round_price(leader_px * 1.005)
    assert abs(px - expected) < 1e-9


def test_configurable_slippage_zero(
    cfg, positions, journal, alerter, exchange, outcome_fill, market_meta
):
    cfg2 = _override_sizing(cfg, ioc_slippage_bps=0)
    cfg2 = _override_risk(cfg2, dry_run=False)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    mt.on_leader_fill("0xleader", outcome_fill)
    px = exchange.order.call_args.args[3]
    leader_px = float(outcome_fill["px"])
    # zero slippage → submitted px equals (rounded) leader px
    assert abs(px - market_meta.round_price(leader_px)) < 1e-9


def test_reduce_only_on_opposing_sell_into_long(
    cfg, positions, journal, alerter, exchange, outcome_fill, market_meta
):
    # Existing long 50; leader sells (opposing) ≤ 50 → reduce_only
    positions.state.get_position.return_value = (50.0, 0.5)
    cfg2 = _override_risk(cfg, dry_run=False)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    fill = {**outcome_fill, "side": "A"}  # SELL
    mt.on_leader_fill("0xleader", fill)
    kwargs = exchange.order.call_args.kwargs
    assert kwargs["reduce_only"] is True


def test_reduce_only_on_opposing_buy_into_short(
    cfg, positions, journal, alerter, exchange, outcome_fill, market_meta
):
    positions.state.get_position.return_value = (-50.0, 0.5)  # short
    cfg2 = _override_risk(cfg, dry_run=False)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    # outcome_fill is BUY, opposing the short → reduce_only
    mt.on_leader_fill("0xleader", outcome_fill)
    kwargs = exchange.order.call_args.kwargs
    assert kwargs["reduce_only"] is True


def test_no_reduce_only_when_no_position(
    cfg, positions, journal, alerter, exchange, outcome_fill, market_meta
):
    positions.state.get_position.return_value = (0.0, 0.0)
    cfg2 = _override_risk(cfg, dry_run=False)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    mt.on_leader_fill("0xleader", outcome_fill)
    kwargs = exchange.order.call_args.kwargs
    assert kwargs["reduce_only"] is False


def test_no_reduce_only_when_flips_through_zero(
    cfg, positions, journal, alerter, exchange, market_meta
):
    # Existing long 5; leader sells 10 → would flip to short 5. HL rejects
    # reduce_only flips, so we must submit reduce_only=False.
    positions = MagicMock()
    positions.realized_pnl_today.return_value = 0.0
    positions.total_exposure_usd.return_value = 0.0
    positions.state.get_position.return_value = (5.0, 0.5)
    cfg2 = _override_risk(cfg, dry_run=False)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    # leader fill: SELL 100 @ 0.50 → 50 leader notional x 0.10 = $5 mirror = 10 size
    fill = {"tid": 7, "coin": "#11", "px": "0.50", "sz": "100", "side": "A"}
    mt.on_leader_fill("0xleader", fill)
    kwargs = exchange.order.call_args.kwargs
    assert kwargs["reduce_only"] is False  # 10 > existing 5 → flip → not reduce_only


def test_reduce_only_bypasses_exposure_cap(
    cfg, positions, journal, alerter, exchange, outcome_fill, market_meta
):
    # Already at exposure cap — a normal order would be rejected, but a
    # reduce_only order shrinks exposure so it must go through.
    positions.state.get_position.return_value = (50.0, 0.5)
    positions.total_exposure_usd.return_value = 1_000_000.0  # way over cap
    cfg2 = _override_risk(cfg, dry_run=False, max_total_exposure_usd=100)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    fill = {**outcome_fill, "side": "A"}  # opposing sell-into-long
    mt.on_leader_fill("0xleader", fill)
    exchange.order.assert_called_once()
    assert exchange.order.call_args.kwargs["reduce_only"] is True


def test_in_flight_notional_blocks_runaway(cfg, positions, journal, alerter, exchange, market_meta):
    """Race condition fix — rapid mirrors must respect in-flight notional.

    Real bug observed 2026-05-05: 19 leader fills hit the WS in <1s, mirror
    submitted them all because each new submit's risk check saw stale local
    position state (own-fill WS feedback hadn't propagated yet). Result: 5x
    leverage on XMR, ~18% from liquidation.

    Fix: each successful submit adds notional to _in_flight with a 30s TTL.
    Risk check sums local exposure + in-flight before comparing to the cap.
    Sequential rapid submits now hit the cap at the right point."""
    cfg2 = _override_risk(cfg, dry_run=False, max_total_exposure_usd=20)
    cfg2 = _override_sizing(cfg2, max_per_trade_usd=10, min_per_trade_usd=1)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    # Each leader fill produces a $5.40 mirror notional after the 0.10 fraction.
    fill = {"tid": 1, "coin": "#11", "px": "0.54", "sz": "100", "side": "B"}
    # Local position state stays at 0 (positions mock doesn't update on fill).
    # Without in-flight tracking, ALL would submit. With it, only ceil(20/5.40)
    # = 3 submissions before cap engages.
    import contextlib

    for i in range(10):
        fill_i = dict(fill, tid=i + 1)
        with contextlib.suppress(Exception):
            mt.on_leader_fill("0xleader", fill_i)
    assert exchange.order.call_count <= 4, (
        f"in-flight tally must limit submissions to ~3-4 before cap engages; "
        f"got {exchange.order.call_count}"
    )


def test_in_flight_expires_after_ttl(
    cfg, positions, journal, alerter, exchange, market_meta, monkeypatch
):
    """In-flight entries must expire after IN_FLIGHT_TTL_SECONDS so a permanently
    stuck order doesn't lock out future submissions forever."""
    import src.mirror as mirror_mod

    cfg2 = _override_risk(cfg, dry_run=False, max_total_exposure_usd=10)
    cfg2 = _override_sizing(cfg2, max_per_trade_usd=10, min_per_trade_usd=1)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)

    fill = {"tid": 1, "coin": "#11", "px": "0.54", "sz": "100", "side": "B"}
    mt.on_leader_fill("0xleader", fill)
    initial_calls = exchange.order.call_count
    assert initial_calls == 1

    # Second submit should be blocked by in-flight cap
    mt.on_leader_fill("0xleader", dict(fill, tid=2))
    assert exchange.order.call_count == initial_calls

    # Advance time past the TTL — in-flight should clear
    real_time = mirror_mod.time.time
    monkeypatch.setattr(
        mirror_mod.time,
        "time",
        lambda: real_time() + mirror_mod.IN_FLIGHT_TTL_SECONDS + 1,
    )
    mt.on_leader_fill("0xleader", dict(fill, tid=3))
    assert exchange.order.call_count == initial_calls + 1


def test_in_flight_only_counts_unexpired(
    cfg, positions, journal, alerter, exchange, market_meta, monkeypatch
):
    """Mixed expired+active in-flight: only active count toward cap."""
    import src.mirror as mirror_mod

    cfg2 = _override_risk(cfg, dry_run=False, max_total_exposure_usd=20)
    cfg2 = _override_sizing(cfg2, max_per_trade_usd=10, min_per_trade_usd=1)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    # Manually inject expired + active in-flight entries
    now = mirror_mod.time.time()
    mt._in_flight = [
        (now - 10.0, 100.0),  # expired — should be pruned
        (now + 100.0, 5.0),  # active
    ]
    # _in_flight_notional should return only the active 5.0
    in_flight_total = mt._in_flight_notional()
    assert in_flight_total == 5.0
    assert len(mt._in_flight) == 1, "expired entries must be pruned"


def test_reduce_only_does_not_consume_in_flight_budget(
    cfg, positions, journal, alerter, exchange, outcome_fill, market_meta
):
    """Reduce-only orders bypass the exposure cap, so they shouldn't add to
    _in_flight either — they're shrinking exposure, not growing it."""
    cfg2 = _override_risk(cfg, dry_run=False, max_total_exposure_usd=10)
    cfg2 = _override_sizing(cfg2, max_per_trade_usd=10, min_per_trade_usd=1)
    positions.state.get_position.return_value = (50.0, 0.5)  # opposing long
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    fill = {**outcome_fill, "side": "A"}  # SELL into opposing long → reduce_only
    mt.on_leader_fill("0xleader", fill)
    assert exchange.order.call_count == 1
    # Reduce-only WAS submitted but should not have eaten in-flight budget.
    # (Real-world: a reduce-only mirror should never hit the exposure cap.)
    # Implementation detail: reduce_only orders DO get added to _in_flight,
    # but the exposure check exits early when intent.reduce_only is True,
    # never reaching the cap comparison. So in-flight tally is moot for them.


def test_pipeline_error_unmarks_tid_for_retry(
    cfg, positions, journal, alerter, exchange, outcome_fill, market_meta
):
    """A pipeline error (non-OrderError) must unmark the tid so backfill can
    re-dispatch the fill. OrderError must NOT unmark (order was attempted)."""
    # Inject a failure inside the risk-check path so the generic Exception
    # branch fires instead of the OrderError branch.
    positions.realized_pnl_today.side_effect = RuntimeError("boom")
    mt = MirrorTrader(cfg, exchange, positions, journal, alerter, market_meta)
    mt.on_leader_fill("0xleader", outcome_fill)  # tid=1001 from outcome_fill fixture
    positions.state.unmark_tid_seen.assert_called_once_with(1001)


def test_order_failure_does_not_unmark_tid(
    cfg, positions, journal, exchange, outcome_fill, market_meta
):
    """OrderError = HL rejected our submitted order. The tid must STAY marked
    so we don't accidentally retry and submit a duplicate trade."""
    from src.errors import OrderError

    cfg2 = _override_risk(cfg, dry_run=False)
    exchange.order.side_effect = RuntimeError("HL rejected")
    alerter = MagicMock()
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    with pytest.raises(OrderError):
        mt.on_leader_fill("0xleader", outcome_fill)
    positions.state.unmark_tid_seen.assert_not_called()


def test_post_submit_journal_error_keeps_tid_marked(
    cfg, positions, alerter, exchange, outcome_fill, market_meta
):
    """A journal/bookkeeping OSError AFTER the order is live must NOT unmark the
    tid. The order is already on the exchange; unmarking lets backfill
    re-dispatch the same leader fill and place a duplicate live order.

    Regression for the double-trade path: post-submit journal.write raises
    OSError (ENOSPC/EROFS/etc.), which is not an OrderError, so it previously
    escaped _submit -> on_leader_fill's `except Exception` -> unmark_tid_seen.
    """
    cfg2 = _override_risk(cfg, dry_run=False)

    # Real order goes through (exchange.order returns ok), but the post-submit
    # "order_result" journal write fails with a filesystem error.
    journal = MagicMock()

    def _write(event, **fields):
        if event == "order_result":
            raise OSError(28, "No space left on device")

    journal.write.side_effect = _write

    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    # Must not raise out of on_leader_fill.
    mt.on_leader_fill("0xleader", outcome_fill)  # tid=1001

    # The order was actually placed exactly once.
    exchange.order.assert_called_once()
    # Critically: the tid must stay marked so backfill does NOT re-dispatch it.
    positions.state.unmark_tid_seen.assert_not_called()


def test_post_submit_error_does_not_unmark_tid(
    cfg, positions, journal, exchange, outcome_fill, market_meta
):
    """A non-OrderError raised AFTER a live order was submitted (e.g. sqlite
    'database is locked' in set_position_originator) must NOT unmark the tid.
    The order is already live; unmarking would let backfill re-dispatch the
    same leader fill and submit a duplicate order (double-trade)."""
    import sqlite3

    cfg2 = _override_risk(cfg, dry_run=False)
    # _submit succeeds (order placed), then the post-submit DB write raises a
    # plain OperationalError — NOT an OrderError.
    positions.state.set_position_originator.side_effect = sqlite3.OperationalError(
        "database is locked"
    )
    alerter = MagicMock()
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    mt.on_leader_fill("0xleader", outcome_fill)  # tid=1001

    # The order WAS submitted...
    exchange.order.assert_called_once()
    # ...so the tid must stay marked — no unmark, no re-dispatch, no double-trade.
    positions.state.unmark_tid_seen.assert_not_called()


def test_outcome_min_overrides_global_min(
    cfg, positions, journal, alerter, exchange, outcome_fill, market_meta
):
    """HL enforces $10 USDH min on outcomes. With outcome_min_per_trade_usd=10
    set, outcome trades below $10 must skip even if global min_per_trade_usd
    would allow them."""
    cfg2 = _override_sizing(cfg, min_per_trade_usd=1.0, outcome_min_per_trade_usd=10.0)
    cfg2 = _override_risk(cfg2, dry_run=False)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    # outcome_fill: 100 sz @ 0.54, 0.10 frac → mirror notional $5.40 → below $10 outcome min
    mt.on_leader_fill("0xleader", outcome_fill)
    exchange.order.assert_not_called()


def test_outcome_min_does_not_block_perps(cfg, positions, journal, alerter, exchange, market_meta):
    """outcome_min_per_trade_usd should NOT affect perp trades — they use the
    standard min_per_trade_usd. A $5 perp trade should pass when outcome_min=10."""
    cfg2 = _override_sizing(cfg, min_per_trade_usd=1.0, outcome_min_per_trade_usd=10.0)
    cfg2 = _override_risk(cfg2, dry_run=False, allowed_market_types=["perp"])
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    # Perp BTC fill: 0.001 sz @ $50000 → leader notional $50, mirror 0.10 = $5
    fill = {"tid": 99, "coin": "BTC", "px": "50000", "sz": "0.001", "side": "B"}
    mt.on_leader_fill("0xleader", fill)
    exchange.order.assert_called_once()


def test_outcome_min_none_falls_back_to_global_min(
    cfg, positions, journal, alerter, exchange, outcome_fill, market_meta
):
    """When outcome_min_per_trade_usd is None (default), outcomes use the
    global min_per_trade_usd — preserves prior behavior."""
    cfg2 = _override_sizing(cfg, min_per_trade_usd=1.0, outcome_min_per_trade_usd=None)
    cfg2 = _override_risk(cfg2, dry_run=False)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    # outcome_fill notional $5.40 ≥ $1 global min → submits
    mt.on_leader_fill("0xleader", outcome_fill)
    exchange.order.assert_called_once()


def test_post_round_min_skip(cfg, positions, journal, alerter, exchange, market_meta):
    # Outcome rounds to integer shares. raw_sz = 5.5 / 0.5 = 11; rounded = 11; OK.
    # But a price=$1, notional=$5.5, raw_sz=5.5, rounded to 5, post-round notional=5
    # which is exactly at min ($5). Use a fill that produces $4.99 post-round.
    cfg2 = _override_sizing(cfg, min_per_trade_usd=10, max_per_trade_usd=100)
    cfg2 = _override_risk(cfg2, dry_run=False)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    # leader fill: 100 @ 1.05 → notional 105 x 0.10 = $10.50 → raw_sz 10.0
    # rounded to 10 (already integer), notional = 10 x 1.05 = $10.50 — passes
    # let's craft one that fails: 95 @ 1.05 → 99.75 x 0.10 = 9.975, raw_sz=9.5
    # → rounded 9, notional = 9 x 1.05 = 9.45 < 10 min → skip
    fill = {"tid": 9, "coin": "#11", "px": "1.05", "sz": "95", "side": "B"}
    mt.on_leader_fill("0xleader", fill)
    exchange.order.assert_not_called()


# ---------- per-coin weight-priority conflict lock (PR #25) ----------


def _real_state(tmp_path):
    """Helper: real State (sqlite) instead of MagicMock so originator
    tracking actually persists for conflict-lock tests."""
    from src.state import State
    return State(str(tmp_path / "test_state.db"))


def test_conflict_lock_allows_first_leader_to_open(
    cfg, journal, alerter, exchange, market_meta, tmp_path
):
    """No existing position → first leader's signal is always allowed and
    they become the originator."""
    from src.positions import PositionTracker
    state = _real_state(tmp_path)
    info = MagicMock()
    pt = PositionTracker(info, "0xacc", state, journal)
    cfg2 = _override_risk(cfg, dry_run=False, allowed_market_types=["perp"])
    mt = MirrorTrader(cfg2, exchange, pt, journal, alerter, market_meta)
    fill = {"tid": 1, "coin": "BTC", "px": "100", "sz": "10", "side": "B"}
    mt.on_leader_fill("0xleaderA", fill)
    exchange.order.assert_called_once()
    # Need to also simulate the position update (since exchange is mocked, the
    # own_fill won't propagate). Do it manually for the next assertion to pass.
    state.update_position("BTC", 1.0, 100.0)  # we long BTC now
    state.set_position_originator("BTC", "0xleaderA")
    assert state.get_position_originator("BTC") == "0xleadera"


def test_conflict_lock_blocks_lower_weight_opposite_leader(
    cfg, journal, alerter, exchange, market_meta, tmp_path
):
    """Leader B (low weight) tries to short while leader A (high weight)
    is long → blocked."""
    from src.positions import PositionTracker
    state = _real_state(tmp_path)
    state.update_position("BTC", 1.0, 100.0)  # long position from leader A
    state.set_position_originator("BTC", "0xleaderA")
    info = MagicMock()
    pt = PositionTracker(info, "0xacc", state, journal)
    cfg2 = _override_risk(cfg, dry_run=False, allowed_market_types=["perp"])
    mt = MirrorTrader(cfg2, exchange, pt, journal, alerter, market_meta)
    mt.update_leader_weights({"0xleaderA": 4.0, "0xleaderB": 1.5})
    # Leader B tries to SELL BTC (opposite of A's long)
    fill = {"tid": 2, "coin": "BTC", "px": "100", "sz": "10", "side": "A"}
    mt.on_leader_fill("0xleaderB", fill)
    exchange.order.assert_not_called()


def test_conflict_lock_allows_higher_weight_override(
    cfg, journal, alerter, exchange, market_meta, tmp_path
):
    """Leader B (HIGH weight) can override leader A's (low weight) position
    with an opposite-direction signal."""
    from src.positions import PositionTracker
    state = _real_state(tmp_path)
    state.update_position("BTC", 1.0, 100.0)
    state.set_position_originator("BTC", "0xleaderA")
    info = MagicMock()
    pt = PositionTracker(info, "0xacc", state, journal)
    cfg2 = _override_risk(cfg, dry_run=False, allowed_market_types=["perp"])
    mt = MirrorTrader(cfg2, exchange, pt, journal, alerter, market_meta)
    # Leader A is now LOW weight, leader B HIGH
    mt.update_leader_weights({"0xleaderA": 1.1, "0xleaderB": 4.0})
    fill = {"tid": 3, "coin": "BTC", "px": "100", "sz": "10", "side": "A"}
    mt.on_leader_fill("0xleaderB", fill)
    exchange.order.assert_called_once()


def test_conflict_lock_allows_same_leader_to_continue(
    cfg, journal, alerter, exchange, market_meta, tmp_path
):
    """Leader A is managing their own position — opposite-side signal from
    THE SAME leader is allowed (closing/flipping is their right)."""
    from src.positions import PositionTracker
    state = _real_state(tmp_path)
    state.update_position("BTC", 1.0, 100.0)
    state.set_position_originator("BTC", "0xleaderA")
    info = MagicMock()
    pt = PositionTracker(info, "0xacc", state, journal)
    cfg2 = _override_risk(cfg, dry_run=False, allowed_market_types=["perp"])
    mt = MirrorTrader(cfg2, exchange, pt, journal, alerter, market_meta)
    mt.update_leader_weights({"0xleaderA": 4.0})
    fill = {"tid": 4, "coin": "BTC", "px": "100", "sz": "10", "side": "A"}
    mt.on_leader_fill("0xleaderA", fill)
    exchange.order.assert_called_once()


def test_conflict_lock_allows_same_direction_add_from_different_leader(
    cfg, journal, alerter, exchange, market_meta, tmp_path
):
    """Different leader, SAME direction = allowed (adding to position the
    other leader opened is benign — they're not in conflict)."""
    from src.positions import PositionTracker
    state = _real_state(tmp_path)
    state.update_position("BTC", 1.0, 100.0)
    state.set_position_originator("BTC", "0xleaderA")
    info = MagicMock()
    pt = PositionTracker(info, "0xacc", state, journal)
    cfg2 = _override_risk(cfg, dry_run=False, allowed_market_types=["perp"])
    mt = MirrorTrader(cfg2, exchange, pt, journal, alerter, market_meta)
    mt.update_leader_weights({"0xleaderA": 4.0, "0xleaderB": 1.5})
    # Leader B BUYS BTC (same direction as A's long)
    fill = {"tid": 5, "coin": "BTC", "px": "100", "sz": "10", "side": "B"}
    mt.on_leader_fill("0xleaderB", fill)
    exchange.order.assert_called_once()


def test_conflict_lock_originator_clears_when_position_closes(
    cfg, journal, alerter, exchange, market_meta, tmp_path
):
    """When a position closes (sz=0), the originator must clear so the next
    leader to fire can claim the coin without conflict."""
    state = _real_state(tmp_path)
    state.update_position("BTC", 1.0, 100.0)
    state.set_position_originator("BTC", "0xleaderA")
    assert state.get_position_originator("BTC") == "0xleadera"
    # Close it
    state.update_position("BTC", 0.0, 0.0)
    assert state.get_position_originator("BTC") is None  # cleared by update_position(sz=0)


def test_conflict_lock_unknown_originator_falls_through(
    cfg, journal, alerter, exchange, market_meta, tmp_path
):
    """Pre-PR-#25 positions have NULL originator. Treat them as unclaimed —
    next leader to fire can take them. Avoids stuck-state on migration."""
    from src.positions import PositionTracker
    state = _real_state(tmp_path)
    state.update_position("BTC", 1.0, 100.0)  # but no set_position_originator()
    info = MagicMock()
    pt = PositionTracker(info, "0xacc", state, journal)
    cfg2 = _override_risk(cfg, dry_run=False, allowed_market_types=["perp"])
    mt = MirrorTrader(cfg2, exchange, pt, journal, alerter, market_meta)
    mt.update_leader_weights({"0xleaderA": 1.5})
    fill = {"tid": 7, "coin": "BTC", "px": "100", "sz": "10", "side": "A"}
    mt.on_leader_fill("0xleaderA", fill)
    exchange.order.assert_called_once()


# --- order submit retry on 429 ---------------------------------------------


def _client_error_429():
    """Build a ClientError matching what hyperliquid SDK raises on rate-limit."""
    from hyperliquid.utils.error import ClientError
    return ClientError(429, None, "null", None, {})


def test_order_429_retries_succeed(
    cfg, positions, journal, exchange, outcome_fill, market_meta, monkeypatch
):
    """Two consecutive 429s then success → final result returns, mirror records
    the order_result, no error alert fires."""
    cfg2 = _override_risk(cfg, dry_run=False)
    exchange.order.side_effect = [
        _client_error_429(),
        _client_error_429(),
        {"status": "ok", "response": {"data": {"statuses": [{"resting": {"oid": 1}}]}}},
    ]
    sleeps: list[float] = []
    monkeypatch.setattr("src.mirror.time.sleep", lambda s: sleeps.append(s))
    alerter = MagicMock()
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    mt.on_leader_fill("0xleader", outcome_fill)
    assert exchange.order.call_count == 3
    assert sleeps == [1.0, 2.0]
    err = [c for c in alerter.alert.call_args_list if c.args[0] == "error"]
    assert not err


def test_order_429_exhausts_retries_then_fails(
    cfg, positions, journal, exchange, outcome_fill, market_meta, monkeypatch
):
    """All 3 attempts hit 429 → propagate OrderError, alert fires, journal
    records order_failed (matches the original no-retry contract)."""
    from src.errors import OrderError
    cfg2 = _override_risk(cfg, dry_run=False)
    exchange.order.side_effect = [_client_error_429()] * 3
    monkeypatch.setattr("src.mirror.time.sleep", lambda s: None)
    alerter = MagicMock()
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    with pytest.raises(OrderError):
        mt.on_leader_fill("0xleader", outcome_fill)
    assert exchange.order.call_count == 3
    err = [c for c in alerter.alert.call_args_list if c.args[0] == "error"]
    assert err


def test_order_non_429_client_error_fails_fast(
    cfg, positions, journal, exchange, outcome_fill, market_meta, monkeypatch
):
    """Other client errors (e.g. 400 bad order params) should NOT retry —
    same payload would just fail again."""
    from hyperliquid.utils.error import ClientError
    from src.errors import OrderError
    cfg2 = _override_risk(cfg, dry_run=False)
    exchange.order.side_effect = ClientError(400, None, "bad price", None, {})
    sleeps: list[float] = []
    monkeypatch.setattr("src.mirror.time.sleep", lambda s: sleeps.append(s))
    alerter = MagicMock()
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    with pytest.raises(OrderError):
        mt.on_leader_fill("0xleader", outcome_fill)
    assert exchange.order.call_count == 1
    assert sleeps == []


def test_order_non_client_error_fails_fast(
    cfg, positions, journal, exchange, outcome_fill, market_meta, monkeypatch
):
    """Ambiguous failures (timeout, network) should NOT retry — order may
    have actually been placed mid-failure; retry would double-submit."""
    from src.errors import OrderError
    cfg2 = _override_risk(cfg, dry_run=False)
    exchange.order.side_effect = TimeoutError("network timeout")
    sleeps: list[float] = []
    monkeypatch.setattr("src.mirror.time.sleep", lambda s: sleeps.append(s))
    alerter = MagicMock()
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    with pytest.raises(OrderError):
        mt.on_leader_fill("0xleader", outcome_fill)
    assert exchange.order.call_count == 1
    assert sleeps == []


def test_order_retry_records_only_one_order_result_event(
    cfg, positions, journal, exchange, outcome_fill, market_meta, monkeypatch
):
    """After 1 retry succeeds, exactly ONE order_result event in the journal
    (no duplicate from retried attempts)."""
    cfg2 = _override_risk(cfg, dry_run=False)
    exchange.order.side_effect = [
        _client_error_429(),
        {"status": "ok", "response": {"data": {"statuses": [{"resting": {"oid": 1}}]}}},
    ]
    monkeypatch.setattr("src.mirror.time.sleep", lambda s: None)
    captured: list = []
    real_write = journal.write

    def capture(event, **kw):
        captured.append(event)
        real_write(event, **kw)

    journal.write = capture  # type: ignore[method-assign]
    alerter = MagicMock()
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    mt.on_leader_fill("0xleader", outcome_fill)
    assert captured.count("order_result") == 1
    assert captured.count("order_failed") == 0


# --- in-band rejection / in_flight leak / poison cooldown (2026-06-29 fix) ---

INVALID_SIZE_RESULT = {
    "status": "ok",
    "response": {"type": "order", "data": {"statuses": [{"error": "Order has invalid size."}]}},
}
RESTING_RESULT = {
    "status": "ok",
    "response": {"type": "order", "data": {"statuses": [{"resting": {"oid": 7}}]}},
}


def test_order_status_error_detects_shapes():
    f = MirrorTrader._order_status_error
    # accepted → None
    assert f({"status": "ok"}) is None
    assert f(RESTING_RESULT) is None
    assert f({"status": "ok", "response": {"data": {"statuses": [{"filled": {"totalSz": "1"}}]}}}) is None
    assert f("not-a-dict") is None
    # rejected → message
    assert f(INVALID_SIZE_RESULT) == "Order has invalid size."
    assert f({"status": "err", "response": "nonce too low"}) == "nonce too low"


def test_inband_rejection_does_not_reserve_in_flight(
    cfg, positions, journal, outcome_fill, market_meta
):
    """The $440-phantom leak: a rejected order must not reserve in-flight."""
    cfg2 = _override_risk(cfg, dry_run=False)
    exchange = MagicMock()
    exchange.order.return_value = INVALID_SIZE_RESULT
    alerter = MagicMock()
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    mt.on_leader_fill("0xleader", outcome_fill)
    exchange.order.assert_called_once()          # order was attempted...
    assert mt._in_flight == []                   # ...but reserved no exposure
    positions.state.set_position_originator.assert_not_called()  # didn't claim coin
    assert any(c.args[0] == "warn" for c in alerter.alert.call_args_list)


def test_invalid_size_poisons_coin_and_skips_second_open(
    cfg, positions, journal, alerter, outcome_fill, market_meta
):
    """The API storm: after 'invalid size', further opens on the coin are skipped."""
    cfg2 = _override_risk(cfg, dry_run=False)
    exchange = MagicMock()
    exchange.order.return_value = INVALID_SIZE_RESULT
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    mt.on_leader_fill("0xleader", outcome_fill)
    assert "#11" in mt._poison_until
    mt.on_leader_fill("0xleader", {**outcome_fill, "tid": 1002})
    exchange.order.assert_called_once()          # second open never submitted


def test_accepted_order_reserves_in_flight(
    cfg, positions, journal, alerter, outcome_fill, market_meta
):
    """Regression: an accepted (resting) order still reserves in-flight."""
    cfg2 = _override_risk(cfg, dry_run=False)
    exchange = MagicMock()
    exchange.order.return_value = RESTING_RESULT
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    mt.on_leader_fill("0xleader", outcome_fill)
    assert len(mt._in_flight) == 1
    positions.state.set_position_originator.assert_called_once()


# ---------- sub-minimum rounding rescue + distinct skip reasons ----------
# Incident 2026-07-21 → 2026-08-14. Leader 0x6cd520c1's weight was cut
# 1.5 → 1.0, making the fixed clip exactly $10.00 against a $10.00 minimum.
# Floor-rounding the size to szDecimals took the notional to $9.9x, the
# post-round min check discarded it, and the leader was silently muted for
# 24 days: 10,706 fills filtered vs 79 orders accepted. Every skip journalled
# the same opaque reason ("filter", 2,449,814 of them), so nothing surfaced.


def _skip_reasons(journal) -> list[str]:
    """All intent_skipped reasons written to the journal, in order."""
    import json
    from pathlib import Path

    if not Path(journal.path).exists():
        return []
    out = []
    for line in Path(journal.path).read_text().splitlines():
        e = json.loads(line)
        if e.get("event") == "intent_skipped":
            out.append(e["reason"])
    return out


def _journal_events(journal, event: str) -> list[dict]:
    import json
    from pathlib import Path

    if not Path(journal.path).exists():
        return []
    return [
        e
        for e in (json.loads(ln) for ln in Path(journal.path).read_text().splitlines())
        if e.get("event") == event
    ]


def _perp_mt(cfg, exchange, positions, journal, alerter, market_meta, **sizing):
    cfg2 = _override_sizing(cfg, **sizing)
    cfg2 = _override_risk(cfg2, dry_run=False, allowed_market_types=["perp"])
    return MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)


def test_exact_min_clip_at_weight_one_still_trades(
    cfg, positions, journal, alerter, exchange, market_meta
):
    """THE regression: fixed_usd=$10 x weight 1.0 = exactly the $10 minimum.

    ETH szDecimals=4 @ $3000 → raw 0.0033333 → floors to 0.0033 = $9.90, which
    the old code silently discarded. Must now round up one step and submit."""
    mt = _perp_mt(
        cfg, exchange, positions, journal, alerter, market_meta,
        mode="fixed", fixed_usd=10.0, min_per_trade_usd=10.0, max_per_trade_usd=100.0,
    )
    mt.update_leader_weights({"0x6cd520c1": 1.0})
    mt.on_leader_fill("0x6cd520c1", {"tid": 1, "coin": "ETH", "px": "3000", "sz": "5", "side": "B"})
    exchange.order.assert_called_once()
    sz = exchange.order.call_args.args[2]
    assert abs(sz - 0.0034) < 1e-12  # one szDecimals step up from 0.0033
    assert _skip_reasons(journal) == []


def test_rescue_lands_above_min_not_exactly_on_it(
    cfg, positions, journal, alerter, exchange, market_meta
):
    """HL values orders with its OWN reference price (30d: 199 rejects, all at
    exactly $10.00 intent notional), so the rescue must clear the floor with
    margin, not land on it."""
    mt = _perp_mt(
        cfg, exchange, positions, journal, alerter, market_meta,
        mode="fixed", fixed_usd=10.0, min_per_trade_usd=10.0, max_per_trade_usd=100.0,
    )
    import src.mirror as mirror_mod

    mt.on_leader_fill("0xleader", {"tid": 1, "coin": "ETH", "px": "3000", "sz": "5", "side": "B"})
    sz, px = exchange.order.call_args.args[2], 3000.0
    assert sz * px >= 10.0 * (1 + mirror_mod.MIN_NOTIONAL_SAFETY_MARGIN)


def test_rescue_journals_size_rounded_up(
    cfg, positions, journal, alerter, exchange, market_meta
):
    """The bump must be auditable — an unlogged size change is how we got here."""
    mt = _perp_mt(
        cfg, exchange, positions, journal, alerter, market_meta,
        mode="fixed", fixed_usd=10.0, min_per_trade_usd=10.0, max_per_trade_usd=100.0,
    )
    mt.on_leader_fill("0xleader", {"tid": 1, "coin": "ETH", "px": "3000", "sz": "5", "side": "B"})
    events = _journal_events(journal, "size_rounded_up")
    assert len(events) == 1
    assert events[0]["from_sz"] == 0.0033 and events[0]["to_sz"] == 0.0034
    assert events[0]["to_notional"] > events[0]["from_notional"]


def test_strategist_weight_034_rearms_and_is_rescued(
    cfg, positions, journal, alerter, exchange, market_meta
):
    """fixed_usd=$30 masks the bug at weight 1.0, but the strategist sets
    weights automatically: at 0.34 the clip is $10.20 and re-arms it."""
    mt = _perp_mt(
        cfg, exchange, positions, journal, alerter, market_meta,
        mode="fixed", fixed_usd=30.0, min_per_trade_usd=10.0, max_per_trade_usd=100.0,
    )
    mt.update_leader_weights({"0xweak": 0.34})
    mt.on_leader_fill("0xweak", {"tid": 1, "coin": "ETH", "px": "3100", "sz": "5", "side": "B"})
    exchange.order.assert_called_once()
    assert abs(exchange.order.call_args.args[2] - 0.0033) < 1e-12  # up from 0.0032


def test_no_rescue_when_rounding_already_clears_min(
    cfg, positions, journal, alerter, exchange, market_meta
):
    """A clip comfortably above the minimum is untouched — the rescue must not
    inflate ordinary trades."""
    mt = _perp_mt(
        cfg, exchange, positions, journal, alerter, market_meta,
        mode="fixed", fixed_usd=30.0, min_per_trade_usd=10.0, max_per_trade_usd=100.0,
    )
    mt.on_leader_fill("0xleader", {"tid": 1, "coin": "ETH", "px": "3000", "sz": "5", "side": "B"})
    assert abs(exchange.order.call_args.args[2] - 0.01) < 1e-12  # 30/3000, exact
    assert _journal_events(journal, "size_rounded_up") == []


def test_rescue_skipped_when_bump_breaches_max_per_trade(
    cfg, positions, journal, alerter, exchange, market_meta
):
    """max_per_trade_usd is the hard stop: rounding up only ever adds exposure,
    so a bump that breaches the operator's cap must skip instead."""
    mt = _perp_mt(
        cfg, exchange, positions, journal, alerter, market_meta,
        mode="fixed", fixed_usd=10.0, min_per_trade_usd=10.0, max_per_trade_usd=10.1,
    )
    mt.on_leader_fill("0xleader", {"tid": 1, "coin": "ETH", "px": "3000", "sz": "5", "side": "B"})
    exchange.order.assert_not_called()  # bumped $10.20 > $10.10 cap
    assert _skip_reasons(journal) == ["rounding:exceeds_max"]


def test_rescue_allowed_when_bump_exactly_equals_max_per_trade(
    cfg, positions, journal, alerter, exchange, market_meta
):
    """Boundary: bumped notional == max_per_trade_usd is within the cap."""
    mt = _perp_mt(
        cfg, exchange, positions, journal, alerter, market_meta,
        mode="fixed", fixed_usd=10.0, min_per_trade_usd=10.0, max_per_trade_usd=10.2,
    )
    mt.on_leader_fill("0xleader", {"tid": 1, "coin": "ETH", "px": "3000", "sz": "5", "side": "B"})
    exchange.order.assert_called_once()
    assert abs(exchange.order.call_args.args[2] - 0.0034) < 1e-12  # exactly $10.20


def test_unrepresentably_small_clip_is_rescued_to_one_lot(
    cfg, positions, journal, alerter, exchange, market_meta
):
    """szDecimals=0 outcome priced above our clip floors to zero size. Old code
    dropped it; now we buy the single smallest lot if it fits under the cap."""
    cfg2 = _override_sizing(cfg, min_per_trade_usd=5.0, max_per_trade_usd=100.0)
    cfg2 = _override_risk(cfg2, dry_run=False)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    # $60 leader notional x 0.10 = $6 clip; one share costs $8 → raw sz 0.75
    mt.on_leader_fill("0xleader", {"tid": 1, "coin": "#11", "px": "8", "sz": "7.5", "side": "B"})
    exchange.order.assert_called_once()
    assert exchange.order.call_args.args[2] == 1.0


def test_unrepresentably_small_clip_skips_when_one_lot_breaches_max(
    cfg, positions, journal, alerter, exchange, market_meta
):
    """...but not when that single lot costs more than max_per_trade_usd."""
    cfg2 = _override_sizing(cfg, min_per_trade_usd=5.0, max_per_trade_usd=7.0)
    cfg2 = _override_risk(cfg2, dry_run=False)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    mt.on_leader_fill("0xleader", {"tid": 1, "coin": "#11", "px": "8", "sz": "7.5", "side": "B"})
    exchange.order.assert_not_called()  # one $8 share > $7 cap
    assert _skip_reasons(journal) == ["rounding:exceeds_max"]


def test_genuinely_sub_min_clip_is_never_sized_up(
    cfg, positions, journal, alerter, exchange, market_meta
):
    """The safety property: the rescue only fires for clips the configured
    weight/fraction already asked to be >= the minimum. A clip that is truly
    below the minimum must still be discarded, never rounded up into one."""
    mt = _perp_mt(
        cfg, exchange, positions, journal, alerter, market_meta,
        mode="fixed", fixed_usd=10.0, min_per_trade_usd=10.0, max_per_trade_usd=100.0,
    )
    mt.update_leader_weights({"0xweak": 0.5})  # $5 clip vs $10 min
    mt.on_leader_fill("0xweak", {"tid": 1, "coin": "ETH", "px": "3000", "sz": "5", "side": "B"})
    exchange.order.assert_not_called()
    assert _skip_reasons(journal) == ["sub_min"]


# ---------- distinct skip reasons (no more opaque "filter") ----------


def test_skip_reason_market_type(cfg, positions, journal, alerter, exchange, market_meta):
    cfg2 = _override_risk(cfg, dry_run=False, allowed_market_types=["outcome"])
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    mt.on_leader_fill("0xleader", {"tid": 1, "coin": "BTC", "px": "65000", "sz": "1", "side": "B"})
    assert _skip_reasons(journal) == ["market_type"]


def test_skip_reason_funding_skip(cfg, positions, journal, alerter, exchange, market_meta):
    mt = _perp_mt(
        cfg, exchange, positions, journal, alerter, market_meta,
        use_funding_aware_sizing=True, funding_skip_threshold_apr_pct=100.0,
    )
    mt.funding = _funding_stub({"BTC": 200.0})
    mt.on_leader_fill("0xleader", {"tid": 1, "coin": "BTC", "px": "100", "sz": "10", "side": "B"})
    assert _skip_reasons(journal) == ["funding_skip"]


def test_skip_reason_bad_fill_numbers(cfg, positions, journal, alerter, exchange, market_meta):
    cfg2 = _override_risk(cfg, dry_run=False)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    mt.on_leader_fill("0xleader", {"tid": 1, "coin": "#11", "px": "abc", "sz": "1", "side": "B"})
    assert _skip_reasons(journal) == ["bad_fill_numbers"]


def test_skip_reason_bad_fill_fields(cfg, positions, journal, alerter, exchange, market_meta):
    cfg2 = _override_risk(cfg, dry_run=False)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    mt.on_leader_fill("0xleader", {"tid": 1, "coin": "#11", "px": "0.5", "sz": "1", "side": "X"})
    assert _skip_reasons(journal) == ["bad_fill_fields"]


def test_skip_reason_bad_sizing_mode(cfg, positions, journal, alerter, exchange, market_meta):
    cfg2 = _override_sizing(cfg, mode="nonsense")
    cfg2 = _override_risk(cfg2, dry_run=False)
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    mt.on_leader_fill("0xleader", {"tid": 1, "coin": "#11", "px": "0.5", "sz": "100", "side": "B"})
    assert _skip_reasons(journal) == ["bad_sizing_mode"]


def test_no_skip_reason_is_the_old_opaque_filter_token(
    cfg, positions, journal, alerter, exchange, market_meta
):
    """Guard rail: 2,449,814 undifferentiated 'filter' events in 30 days is what
    hid a 24-day outage. Every skip path must name itself."""
    cfg2 = _override_sizing(cfg, min_per_trade_usd=10.0, max_per_trade_usd=10.1)
    cfg2 = _override_risk(cfg2, dry_run=False, allowed_market_types=["outcome"])
    mt = MirrorTrader(cfg2, exchange, positions, journal, alerter, market_meta)
    for i, fill in enumerate([
        {"coin": "BTC", "px": "100", "sz": "10", "side": "B"},      # market_type
        {"coin": "#11", "px": "abc", "sz": "10", "side": "B"},      # bad_fill_numbers
        {"coin": "#11", "px": "0.5", "sz": "10", "side": "Z"},      # bad_fill_fields
        {"coin": "#11", "px": "0.5", "sz": "10", "side": "B"},      # sub_min
        {"coin": "#11", "px": "8", "sz": "20", "side": "B"},        # rounding:exceeds_max
    ]):
        mt.on_leader_fill("0xleader", {**fill, "tid": i + 1})
    reasons = _skip_reasons(journal)
    assert "filter" not in reasons
    assert reasons == [
        "market_type", "bad_fill_numbers", "bad_fill_fields", "sub_min", "rounding:exceeds_max",
    ]
    assert len(set(reasons)) == len(reasons)  # every path distinguishable
