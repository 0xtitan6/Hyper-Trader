"""Tests for src/leader_reconcile.py — leader exit detection + auto-close."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import json

from src.leader_reconcile import (
    STATUS_CLOSED,
    STATUS_DROPPED,
    STATUS_FLIPPED,
    STATUS_OK,
    STATUS_ORPHAN,
    STATUS_UNKNOWN,
    LeaderReconciler,
)


def _journal_events(journal) -> list[dict]:
    """Parsed journal lines, or [] if nothing was ever written."""
    try:
        with open(journal.path) as f:
            return [json.loads(ln) for ln in f if ln.strip()]
    except FileNotFoundError:
        return []


# --- helpers ---------------------------------------------------------------


def _mock_info(leader_books: dict[str, dict[str, float]]) -> MagicMock:
    """Build an Info mock whose user_state(addr) returns asset positions for
    that address as if from HL. `leader_books` is {address_lower: {coin: szi}}.
    """
    info = MagicMock()

    def user_state(address: str) -> dict:
        book = leader_books.get(address.lower(), {})
        return {
            "assetPositions": [
                {"position": {"coin": c, "szi": str(s)}} for c, s in book.items()
            ]
        }

    info.user_state.side_effect = user_state
    info.all_mids.return_value = {"BTC": "60000.0", "ZEC": "650.0", "TAO": "275.0"}
    return info


def _make_reconciler(
    state,
    journal,
    leader_books: dict[str, dict[str, float]],
    *,
    auto_close: bool = False,
    debounce: int = 2,
    exchange: MagicMock | None = None,
    market_meta=None,
    manual_holdings: list[str] | None = None,
) -> LeaderReconciler:
    return LeaderReconciler(
        info=_mock_info(leader_books),
        state=state,
        journal=journal,
        alerter=MagicMock(),
        exchange=exchange,
        market_meta=market_meta,
        auto_close=auto_close,
        debounce_cycles=debounce,
        slippage_bps=50.0,
        manual_holdings=manual_holdings,
    )


# --- classification --------------------------------------------------------


def test_ok_when_originator_still_short(state, journal):
    state.update_position("BTC", -0.5, 60000.0)
    state.set_position_originator("BTC", "0xABC")
    r = _make_reconciler(state, journal, {"0xabc": {"BTC": -0.5}})
    status = r.reconcile(["0xABC"])
    assert status["BTC"] == STATUS_OK


def test_closed_when_originator_flat(state, journal):
    state.update_position("BTC", -0.5, 60000.0)
    state.set_position_originator("BTC", "0xABC")
    r = _make_reconciler(state, journal, {"0xabc": {}})
    status = r.reconcile(["0xABC"])
    assert status["BTC"] == STATUS_CLOSED


def test_flipped_when_originator_reverses(state, journal):
    state.update_position("BTC", -0.5, 60000.0)
    state.set_position_originator("BTC", "0xABC")
    # Originator now LONG
    r = _make_reconciler(state, journal, {"0xabc": {"BTC": 1.0}})
    status = r.reconcile(["0xABC"])
    assert status["BTC"] == STATUS_FLIPPED


def test_orphan_when_no_originator_and_no_follower_holds_same_dir(state, journal):
    # Pre-PR-#25 position: originator unset
    state.update_position("BTC", -0.5, 60000.0)
    # None of the followed leaders is short BTC
    r = _make_reconciler(
        state, journal, {"0xabc": {"BTC": 1.0}, "0xdef": {"ETH": -2.0}}
    )
    status = r.reconcile(["0xABC", "0xDEF"])
    assert status["BTC"] == STATUS_ORPHAN


def test_orphan_recovers_to_ok_if_another_leader_holds_same_dir(state, journal):
    state.update_position("BTC", -0.5, 60000.0)
    # Originator unset, but 0xdef holds the short
    r = _make_reconciler(
        state, journal, {"0xabc": {"ETH": 1.0}, "0xdef": {"BTC": -2.0}}
    )
    status = r.reconcile(["0xABC", "0xDEF"])
    assert status["BTC"] == STATUS_OK


def test_zero_size_position_not_reported(state, journal):
    # A zeroed historical position should be ignored
    state.update_position("BTC", 0.0, 0.0)
    r = _make_reconciler(state, journal, {"0xabc": {}})
    status = r.reconcile(["0xABC"])
    assert "BTC" not in status


# --- debounce --------------------------------------------------------------


def test_debounce_holds_off_action_on_first_cycle(state, journal):
    state.update_position("BTC", -0.5, 60000.0)
    state.set_position_originator("BTC", "0xABC")
    r = _make_reconciler(state, journal, {"0xabc": {}}, auto_close=False, debounce=2)
    r.reconcile(["0xABC"])
    # First detection should not yet emit `leader_exit_detected`
    assert r.alerter.alert.call_count == 0  # no alert yet
    assert r._stale_counts["BTC"] == 1


def test_debounce_fires_action_on_second_consecutive_cycle(state, journal):
    state.update_position("BTC", -0.5, 60000.0)
    state.set_position_originator("BTC", "0xABC")
    r = _make_reconciler(state, journal, {"0xabc": {}}, auto_close=False, debounce=2)
    r.reconcile(["0xABC"])
    r.reconcile(["0xABC"])
    assert r.alerter.alert.call_count == 1
    # Counter reset after acting so we don't re-spam on cycle 3
    assert r._stale_counts.get("BTC", 0) == 0


def test_debounce_resets_on_recovery(state, journal):
    state.update_position("BTC", -0.5, 60000.0)
    state.set_position_originator("BTC", "0xABC")
    # Cycle 1: stale (originator flat)
    r = _make_reconciler(state, journal, {"0xabc": {}}, debounce=2)
    r.reconcile(["0xABC"])
    assert r._stale_counts["BTC"] == 1
    # Cycle 2: originator back to holding short — should reset counter
    r.info = _mock_info({"0xabc": {"BTC": -0.5}})
    r.reconcile(["0xABC"])
    assert "BTC" not in r._stale_counts
    assert r.alerter.alert.call_count == 0


# --- alert / journal behavior ----------------------------------------------


def test_stale_emits_alert_and_journal(state, journal):
    state.update_position("BTC", -0.5, 60000.0)
    state.set_position_originator("BTC", "0xABC")
    r = _make_reconciler(state, journal, {"0xabc": {}}, auto_close=False, debounce=1)
    r.reconcile(["0xABC"])
    r.alerter.alert.assert_called_once()
    level, msg = r.alerter.alert.call_args.args
    assert level == "error"
    assert "BTC" in msg
    assert "closed" in msg
    # journal entry written
    with open(journal.path) as f:
        lines = f.readlines()
    assert any("leader_exit_detected" in line for line in lines)


# --- auto-close ------------------------------------------------------------


def test_auto_close_submits_reduce_only_buy_for_short(state, journal, market_meta):
    state.update_position("BTC", -0.5, 60000.0)
    state.set_position_originator("BTC", "0xABC")
    exchange = MagicMock()
    exchange.order.return_value = {"status": "ok"}
    r = _make_reconciler(
        state,
        journal,
        {"0xabc": {}},
        auto_close=True,
        debounce=1,
        exchange=exchange,
        market_meta=market_meta,
    )
    r.reconcile(["0xABC"])
    exchange.order.assert_called_once()
    args = exchange.order.call_args
    # Positional: coin, is_buy, sz, limit_px
    assert args.args[0] == "BTC"
    assert args.args[1] is True  # BUY to close a short
    assert args.args[2] == 0.5  # abs of our short size
    assert args.kwargs["reduce_only"] is True
    assert args.kwargs["order_type"] == {"limit": {"tif": "Ioc"}}


def test_auto_close_submits_reduce_only_sell_for_long(state, journal, market_meta):
    state.update_position("ETH", 2.0, 3500.0)
    state.set_position_originator("ETH", "0xABC")
    exchange = MagicMock()
    exchange.order.return_value = {"status": "ok"}
    r = _make_reconciler(
        state,
        journal,
        {"0xabc": {}},
        auto_close=True,
        debounce=1,
        exchange=exchange,
        market_meta=market_meta,
    )
    info = r.info
    info.all_mids.return_value = {"ETH": "3700.0"}
    r.reconcile(["0xABC"])
    exchange.order.assert_called_once()
    args = exchange.order.call_args
    assert args.args[0] == "ETH"
    assert args.args[1] is False  # SELL to close a long
    assert args.args[2] == 2.0
    assert args.kwargs["reduce_only"] is True


def test_auto_close_disabled_does_not_call_exchange(state, journal, market_meta):
    state.update_position("BTC", -0.5, 60000.0)
    state.set_position_originator("BTC", "0xABC")
    exchange = MagicMock()
    r = _make_reconciler(
        state,
        journal,
        {"0xabc": {}},
        auto_close=False,
        debounce=1,
        exchange=exchange,
        market_meta=market_meta,
    )
    r.reconcile(["0xABC"])
    exchange.order.assert_not_called()


# --- failure handling ------------------------------------------------------


def test_unknown_when_originator_fetch_fails(state, journal):
    """If the originator's user_state errors but at least one other fetch
    succeeds, we don't act — wait for the next cycle."""
    state.update_position("BTC", -0.5, 60000.0)
    state.set_position_originator("BTC", "0xABC")
    info = MagicMock()

    def user_state(address: str) -> dict:
        if address.lower() == "0xabc":
            raise OSError("network down")
        return {"assetPositions": []}

    info.user_state.side_effect = user_state
    info.all_mids.return_value = {"BTC": "60000.0"}
    r = LeaderReconciler(
        info=info,
        state=state,
        journal=journal,
        alerter=MagicMock(),
        debounce_cycles=1,
    )
    status = r.reconcile(["0xABC", "0xDEF"])
    assert status["BTC"] == STATUS_UNKNOWN
    r.alerter.alert.assert_not_called()


def test_all_fetches_fail_returns_empty_no_action(state, journal):
    """When every leader fetch fails, we abort the cycle and act on nothing."""
    state.update_position("BTC", -0.5, 60000.0)
    state.set_position_originator("BTC", "0xABC")
    info = MagicMock()
    info.user_state.side_effect = OSError("network down")
    r = LeaderReconciler(
        info=info,
        state=state,
        journal=journal,
        alerter=MagicMock(),
        debounce_cycles=1,
    )
    status = r.reconcile(["0xABC"])
    assert status == {}
    r.alerter.alert.assert_not_called()


def test_auto_close_handles_order_exception(state, journal, market_meta):
    state.update_position("BTC", -0.5, 60000.0)
    state.set_position_originator("BTC", "0xABC")
    exchange = MagicMock()
    exchange.order.side_effect = RuntimeError("rejected")
    r = _make_reconciler(
        state,
        journal,
        {"0xabc": {}},
        auto_close=True,
        debounce=1,
        exchange=exchange,
        market_meta=market_meta,
    )
    # Should not raise out of reconcile()
    r.reconcile(["0xABC"])
    # Alert about the failure should be emitted
    assert any(
        "auto-close order failed" in str(call.args[1])
        for call in r.alerter.alert.call_args_list
    )


# --- manual holdings -------------------------------------------------------


def test_manual_holdings_skipped_entirely(state, journal):
    """Coin in manual_holdings never appears in status — no classification at
    all, no debounce counter incremented, no alert."""
    state.update_position("#1420", 31.0, 0.6372)
    # No originator set — would normally be ORPHAN
    r = _make_reconciler(
        state, journal, {"0xabc": {}}, debounce=1, manual_holdings=["#1420"]
    )
    status = r.reconcile(["0xABC"])
    assert "#1420" not in status
    assert r._stale_counts == {}
    r.alerter.alert.assert_not_called()


def test_manual_holdings_case_insensitive(state, journal):
    state.update_position("xyz:SPCX", 0.19, 200.0)
    r = _make_reconciler(
        state, journal, {"0xabc": {}}, debounce=1, manual_holdings=["XYZ:spcx"]
    )
    status = r.reconcile(["0xABC"])
    assert "xyz:SPCX" not in status


def test_manual_holdings_does_not_block_other_coins(state, journal):
    """Non-manual positions still get classified normally."""
    state.update_position("#1420", 31.0, 0.6372)
    state.update_position("BTC", -0.5, 60000.0)
    state.set_position_originator("BTC", "0xABC")
    r = _make_reconciler(
        state, journal, {"0xabc": {}}, debounce=1, manual_holdings=["#1420"]
    )
    status = r.reconcile(["0xABC"])
    assert "#1420" not in status
    assert status["BTC"] == STATUS_CLOSED


def test_manual_holdings_blocks_auto_close(state, journal, market_meta):
    """Even with auto_close=True, manual holdings are never submitted to
    exchange. This is the live bug from 2026-06-02."""
    state.update_position("#1420", 31.0, 0.6372)
    exchange = MagicMock()
    r = _make_reconciler(
        state,
        journal,
        {"0xabc": {}},
        auto_close=True,
        debounce=1,
        exchange=exchange,
        market_meta=market_meta,
        manual_holdings=["#1420"],
    )
    r.reconcile(["0xABC"])
    exchange.order.assert_not_called()


def test_manual_holdings_none_defaults_to_empty(state, journal):
    """Passing manual_holdings=None preserves prior behavior (no skips)."""
    state.update_position("BTC", -0.5, 60000.0)
    state.set_position_originator("BTC", "0xABC")
    r = _make_reconciler(state, journal, {"0xabc": {}}, debounce=1, manual_holdings=None)
    status = r.reconcile(["0xABC"])
    assert status["BTC"] == STATUS_CLOSED


# --- reset utility ---------------------------------------------------------


def test_reset_debounce_all(state, journal):
    state.update_position("BTC", -0.5, 60000.0)
    state.set_position_originator("BTC", "0xABC")
    r = _make_reconciler(state, journal, {"0xabc": {}}, debounce=3)
    r.reconcile(["0xABC"])
    assert r._stale_counts["BTC"] == 1
    r.reset_debounce()
    assert r._stale_counts == {}


def test_reset_debounce_single_coin(state, journal):
    state.update_position("BTC", -0.5, 60000.0)
    state.update_position("ETH", 2.0, 3500.0)
    state.set_position_originator("BTC", "0xABC")
    state.set_position_originator("ETH", "0xABC")
    r = _make_reconciler(state, journal, {"0xabc": {}}, debounce=3)
    r.reconcile(["0xABC"])
    assert set(r._stale_counts) == {"BTC", "ETH"}
    r.reset_debounce("BTC")
    assert set(r._stale_counts) == {"ETH"}


# --- HIP-3 leader books (incident 2026-08-15 14:34) -------------------------
# `user_state` returns BASE-dex positions only, so a leader's entire xyz book
# was invisible and every xyz mirror classified as `orphan` -- six simultaneous
# "Leader exit detected ... orphan" on positions the leader still held. The
# only reason the book survived is that _fetch_mid has no xyz mid, so the
# auto-close failed. That is an accident, not a safeguard: fixing the mid
# without this would have force-closed the whole surface.


def _hip3_reconciler(state, journal, base_book, dex_books, *, dexes=("xyz",), fail_dex=()):
    info = MagicMock()
    info.user_state.return_value = {
        "assetPositions": [
            {"position": {"coin": c, "szi": str(s)}} for c, s in base_book.items()
        ]
    }

    def _post(_path, payload):
        t = payload.get("type")
        if t == "perpDexs":
            return [{"name": d} for d in dexes]
        if t == "clearinghouseState":
            d = payload.get("dex")
            if d in fail_dex:
                raise RuntimeError(f"dex {d} down")
            return {
                "assetPositions": [
                    {"position": {"coin": c, "szi": str(s)}}
                    for c, s in dex_books.get(d, {}).items()
                ]
            }
        return {}

    info.post.side_effect = _post
    return LeaderReconciler(
        info=info, state=state, journal=journal, alerter=MagicMock(),
        exchange=None, market_meta=None, auto_close=False,
        debounce_cycles=2, slippage_bps=50.0, manual_holdings=None,
    )


def test_leader_hip3_position_is_not_an_orphan(state, journal):
    """The regression: leader still holds xyz:SKHX, so our mirror is OK."""
    state.update_position("xyz:SKHX", 0.02, 1000.6)
    state.set_position_originator("xyz:SKHX", "0xlead")
    lr = _hip3_reconciler(state, journal, {"BTC": 1.0}, {"xyz": {"xyz:SKHX": 0.5}})
    assert lr.reconcile(["0xlead"]).get("xyz:SKHX") == STATUS_OK


def test_unreadable_dex_skips_the_whole_cycle(state, journal):
    """Sole leader unreadable -> skip entirely. Even safer than UNKNOWN: the
    position is never classified, so nothing can auto-close it."""
    state.update_position("xyz:SKHX", 0.02, 1000.6)
    state.set_position_originator("xyz:SKHX", "0xlead")
    lr = _hip3_reconciler(state, journal, {"BTC": 1.0}, {}, fail_dex=("xyz",))
    out = lr.reconcile(["0xlead"])
    assert out == {}  # cycle skipped
    assert out.get("xyz:SKHX") != STATUS_ORPHAN


def test_unreadable_dex_is_unknown_when_another_leader_succeeds(state, journal):
    """With a readable leader present the cycle proceeds, so the leader whose
    dex failed must land on UNKNOWN -- never ORPHAN, which would auto-close."""
    state.update_position("xyz:SKHX", 0.02, 1000.6)
    state.set_position_originator("xyz:SKHX", "0xbad")
    info = MagicMock()
    info.user_state.return_value = {"assetPositions": []}

    def _post(_path, payload):
        t = payload.get("type")
        if t == "perpDexs":
            return [{"name": "xyz"}]
        if t == "clearinghouseState":
            if payload.get("user") == "0xbad":
                raise RuntimeError("dex down for this leader")
            return {"assetPositions": []}
        return {}

    info.post.side_effect = _post
    lr = LeaderReconciler(
        info=info, state=state, journal=journal, alerter=MagicMock(),
        exchange=None, market_meta=None, auto_close=False,
        debounce_cycles=2, slippage_bps=50.0, manual_holdings=None,
    )
    assert lr.reconcile(["0xbad", "0xgood"]).get("xyz:SKHX") == STATUS_UNKNOWN


def test_genuinely_closed_hip3_position_still_detected(state, journal):
    """Fail-safe must not become never-close: leader flat on a readable dex."""
    state.update_position("xyz:SKHX", 0.02, 1000.6)
    state.set_position_originator("xyz:SKHX", "0xlead")
    lr = _hip3_reconciler(state, journal, {"BTC": 1.0}, {"xyz": {}})
    assert lr.reconcile(["0xlead"]).get("xyz:SKHX") == STATUS_CLOSED


# --- dropped-leader orphans (BACKLOG P1) -----------------------------------
#
# `reconcile()` only ever sees a leader EXIT their own position. Removing a
# leader from config/discovery leaves everything they opened stranded: the
# follower never unsubscribes, so the leader stays readable and their mirror
# classifies `ok` forever. Four such mirrors (JUP, JTO, AR, XMR from two
# leaders dropped in July) held 100% of base margin by 2026-08-15.
#
# `check_dropped_leaders` is detect-only: journal + one alert per coin, never
# a close.


def _dropped_reconciler(state, journal, **kw) -> LeaderReconciler:
    """A reconciler whose Info would EXPLODE if touched — check_dropped_leaders
    must be a pure state read (that is what makes it safe on startup)."""
    info = MagicMock()
    info.user_state.side_effect = AssertionError("must not hit the network")
    info.post.side_effect = AssertionError("must not hit the network")
    info.all_mids.side_effect = AssertionError("must not hit the network")
    kw.setdefault("auto_close", True)  # live config value; must still not close
    return LeaderReconciler(
        info=info,
        state=state,
        journal=journal,
        alerter=kw.pop("alerter", MagicMock()),
        exchange=kw.pop("exchange", None),
        market_meta=None,
        auto_close=kw.pop("auto_close"),
        debounce_cycles=2,
        slippage_bps=50.0,
        manual_holdings=kw.pop("manual_holdings", None),
        # Default to 1 so each test isolates ONE behaviour; the production
        # value (2) has its own tests below.
        dropped_confirm_passes=kw.pop("confirm", 1),
    )


def test_dropped_originator_is_flagged(state, journal):
    state.update_position("JUP", 12.0, 0.85)
    state.set_position_originator("JUP", "0xGONE")
    r = _dropped_reconciler(state, journal)
    assert r.check_dropped_leaders(["0xSTILLHERE"])["JUP"] == STATUS_DROPPED


def test_followed_originator_is_not_flagged(state, journal):
    state.update_position("JUP", 12.0, 0.85)
    state.set_position_originator("JUP", "0xABC")
    r = _dropped_reconciler(state, journal)
    assert r.check_dropped_leaders(["0xABC", "0xDEF"])["JUP"] == STATUS_OK


def test_dropped_check_is_case_insensitive(state, journal):
    """Addresses arrive lowercased from the follower but mixed-case from
    config — a case mismatch would flag every live position as dropped."""
    state.update_position("JUP", 12.0, 0.85)
    state.set_position_originator("JUP", "0xAbCdEf")
    r = _dropped_reconciler(state, journal)
    assert r.check_dropped_leaders(["0xABCDEF"])["JUP"] == STATUS_OK


def test_unknown_originator_is_unknown_not_dropped(state, journal):
    """INV 4: an unreadable originator means we do not KNOW whose position this
    is — it must never be reported as dropped."""
    state.update_position("JUP", 12.0, 0.85)  # no originator recorded
    r = _dropped_reconciler(state, journal)
    out = r.check_dropped_leaders(["0xABC"])
    assert out["JUP"] == STATUS_UNKNOWN
    assert out["JUP"] != STATUS_DROPPED


def test_empty_leader_set_is_unknown_not_dropped(state, journal, tmp_path):
    """INV 4: discovery returning nothing is 'we do not know the followed set',
    NOT 'every leader was dropped'. Flagging the whole book here is the same
    class of bug that tried to auto-close six live positions on 2026-08-15."""
    state.update_position("JUP", 12.0, 0.85)
    state.set_position_originator("JUP", "0xGONE")
    alerter = MagicMock()
    r = _dropped_reconciler(state, journal, alerter=alerter)
    assert r.check_dropped_leaders([])["JUP"] == STATUS_UNKNOWN
    assert r.check_dropped_leaders(None)["JUP"] == STATUS_UNKNOWN
    alerter.alert.assert_not_called()
    assert not _journal_events(journal)


def test_empty_leader_set_does_not_suppress_later_detection(state, journal):
    """Fail-open must not become never-act (INV 4, second direction): once a
    real followed set arrives, the orphan must still be flagged."""
    state.update_position("JUP", 12.0, 0.85)
    state.set_position_originator("JUP", "0xGONE")
    r = _dropped_reconciler(state, journal)
    assert r.check_dropped_leaders([])["JUP"] == STATUS_UNKNOWN
    assert r.check_dropped_leaders(["0xSTILLHERE"])["JUP"] == STATUS_DROPPED


def test_manual_holding_exempt_from_dropped_check(state, journal):
    """xyz:SPCX / #1420 / #1430 are operator trades with no originator at all."""
    state.update_position("xyz:SPCX", 1.0, 100.0)
    state.update_position("JUP", 12.0, 0.85)
    state.set_position_originator("JUP", "0xGONE")
    r = _dropped_reconciler(state, journal, manual_holdings=["XYZ:spcx"])
    out = r.check_dropped_leaders(["0xSTILLHERE"])
    assert "xyz:SPCX" not in out
    assert out["JUP"] == STATUS_DROPPED


def test_zero_size_position_not_flagged_as_dropped(state, journal):
    state.update_position("JUP", 0.0, 0.0)
    r = _dropped_reconciler(state, journal)
    assert "JUP" not in r.check_dropped_leaders(["0xSTILLHERE"])


def test_dropped_never_auto_closes_even_when_auto_close_on(state, journal):
    """AC-2: closing is a money action and stays with the operator. Live config
    has leader_exit_auto_close: true, so this is the load-bearing assertion."""
    state.update_position("JUP", 12.0, 0.85)
    state.set_position_originator("JUP", "0xGONE")
    exchange = MagicMock()
    r = _dropped_reconciler(state, journal, auto_close=True, exchange=exchange)
    for _ in range(5):  # well past debounce_cycles
        r.check_dropped_leaders(["0xSTILLHERE"])
    exchange.order.assert_not_called()


def test_dropped_does_not_disturb_reconcile_debounce(state, journal):
    """The drop check must not count as a reconcile cycle — otherwise a refresh
    landing next to the 5-min timer would satisfy the auto-close debounce with
    two 'cycles' seconds apart."""
    state.update_position("JUP", 12.0, 0.85)
    state.set_position_originator("JUP", "0xGONE")
    r = _dropped_reconciler(state, journal)
    for _ in range(5):
        r.check_dropped_leaders(["0xSTILLHERE"])
    assert r._stale_counts == {}


def test_dropped_alert_is_throttled_to_one_per_coin(state, journal):
    """AC-2: a dropped leader is a standing condition. Without throttling this
    re-fires on every leader refresh (10 min) forever."""
    state.update_position("JUP", 12.0, 0.85)
    state.set_position_originator("JUP", "0xGONE")
    alerter = MagicMock()
    r = _dropped_reconciler(state, journal, alerter=alerter)
    for _ in range(4):
        r.check_dropped_leaders(["0xSTILLHERE"])
    assert alerter.alert.call_count == 1
    assert len(_journal_events(journal)) == 1


def test_dropped_journal_reason_and_fields(state, journal):
    state.update_position("JUP", 12.0, 0.85)
    state.set_position_originator("JUP", "0xGONE")
    r = _dropped_reconciler(state, journal)
    r.check_dropped_leaders(["0xSTILLHERE"])
    (ev,) = _journal_events(journal)
    assert ev["event"] == "dropped_leader_orphan"
    assert ev["coin"] == "JUP"
    assert ev["originator"] == "0xgone"
    assert ev["our_sz"] == 12.0
    assert ev["our_avg_px"] == 0.85


def test_dropped_two_coins_alert_separately(state, journal):
    """Throttle is per coin, not global — JUP must not mute JTO."""
    state.update_position("JUP", 12.0, 0.85)
    state.set_position_originator("JUP", "0xGONE")
    state.update_position("JTO", 5.0, 2.10)
    state.set_position_originator("JTO", "0xALSOGONE")
    alerter = MagicMock()
    r = _dropped_reconciler(state, journal, alerter=alerter)
    r.check_dropped_leaders(["0xSTILLHERE"])
    r.check_dropped_leaders(["0xSTILLHERE"])
    assert alerter.alert.call_count == 2
    assert {e["coin"] for e in _journal_events(journal)} == {"JUP", "JTO"}


def test_readding_leader_rearms_the_alert(state, journal):
    """If the operator re-adds the leader and later drops them again, we must
    alert again — the throttle is not a permanent mute."""
    state.update_position("JUP", 12.0, 0.85)
    state.set_position_originator("JUP", "0xGONE")
    alerter = MagicMock()
    r = _dropped_reconciler(state, journal, alerter=alerter)
    r.check_dropped_leaders(["0xSTILLHERE"])          # dropped -> alert
    assert r.check_dropped_leaders(["0xGONE"])["JUP"] == STATUS_OK  # re-added
    r.check_dropped_leaders(["0xSTILLHERE"])          # dropped again -> alert
    assert alerter.alert.call_count == 2


def test_closing_the_position_rearms_the_alert(state, journal):
    state.update_position("JUP", 12.0, 0.85)
    state.set_position_originator("JUP", "0xGONE")
    alerter = MagicMock()
    r = _dropped_reconciler(state, journal, alerter=alerter)
    r.check_dropped_leaders(["0xSTILLHERE"])
    state.update_position("JUP", 0.0, 0.0)  # operator closed it
    assert "JUP" not in r.check_dropped_leaders(["0xSTILLHERE"])
    state.update_position("JUP", 3.0, 0.90)
    state.set_position_originator("JUP", "0xGONE")
    r.check_dropped_leaders(["0xSTILLHERE"])
    assert alerter.alert.call_count == 2


def test_hip3_mirror_of_dropped_leader_is_flagged(state, journal):
    """Drop detection is a state read, so it is not subject to INV 1 — an
    xyz:* mirror is flagged exactly like a base-dex one, with no dex fetch."""
    state.update_position("xyz:SP500", 0.5, 6100.0)
    state.set_position_originator("xyz:SP500", "0xGONE")
    r = _dropped_reconciler(state, journal)
    assert r.check_dropped_leaders(["0xSTILLHERE"])["xyz:SP500"] == STATUS_DROPPED


def test_reconcile_never_returns_dropped_status(state, journal):
    """The two paths stay separate: reconcile() classifies against fetched
    leader books and must keep its existing statuses only."""
    state.update_position("BTC", -0.5, 60000.0)
    state.set_position_originator("BTC", "0xABC")
    r = _make_reconciler(state, journal, {"0xabc": {}})
    assert r.reconcile(["0xABC"])["BTC"] == STATUS_CLOSED


def test_dropped_requires_confirmation_passes_before_alerting(state, journal):
    """Only 4 of our ~9 slots are auto-discovered and they rotate on rank — a
    leader can leave the top-4 for one refresh and come straight back. One
    observation is not enough to page the operator."""
    state.update_position("JUP", 12.0, 0.85)
    state.set_position_originator("JUP", "0xGONE")
    alerter = MagicMock()
    r = _dropped_reconciler(state, journal, alerter=alerter, confirm=2)
    assert r.check_dropped_leaders(["0xSTILLHERE"])["JUP"] == STATUS_DROPPED
    alerter.alert.assert_not_called()
    r.check_dropped_leaders(["0xSTILLHERE"])
    alerter.alert.assert_called_once()


def test_flapping_leader_never_alerts(state, journal):
    """Leader drops out of the top-N and returns, repeatedly. The confirmation
    counter must reset each time they come back."""
    state.update_position("JUP", 12.0, 0.85)
    state.set_position_originator("JUP", "0xFLAP")
    alerter = MagicMock()
    r = _dropped_reconciler(state, journal, alerter=alerter, confirm=2)
    for _ in range(6):
        r.check_dropped_leaders(["0xSTILLHERE"])   # out of the top-N
        r.check_dropped_leaders(["0xFLAP"])        # back in
    alerter.alert.assert_not_called()


def test_confirmation_does_not_become_never_alert(state, journal):
    """Fail-open must not become never-act (INV 4): a leader that stays gone
    still gets reported once the confirmation threshold is met."""
    state.update_position("JUP", 12.0, 0.85)
    state.set_position_originator("JUP", "0xFLAP")
    alerter = MagicMock()
    r = _dropped_reconciler(state, journal, alerter=alerter, confirm=2)
    r.check_dropped_leaders(["0xSTILLHERE"])
    r.check_dropped_leaders(["0xFLAP"])       # flap back — resets
    r.check_dropped_leaders(["0xSTILLHERE"])  # gone for good now
    r.check_dropped_leaders(["0xSTILLHERE"])
    alerter.alert.assert_called_once()


def test_confirm_passes_floored_at_one(state, journal):
    """A misconfigured 0 must not disable detection entirely (INV 5: a guard
    that silently drops everything is a bug, not safety)."""
    state.update_position("JUP", 12.0, 0.85)
    state.set_position_originator("JUP", "0xGONE")
    alerter = MagicMock()
    r = _dropped_reconciler(state, journal, alerter=alerter, confirm=0)
    r.check_dropped_leaders(["0xSTILLHERE"])
    alerter.alert.assert_called_once()


def test_empty_leader_set_does_not_advance_confirmation(state, journal):
    """An unknown followed set is not evidence of a drop — it must not count
    toward the confirmation threshold."""
    state.update_position("JUP", 12.0, 0.85)
    state.set_position_originator("JUP", "0xGONE")
    alerter = MagicMock()
    r = _dropped_reconciler(state, journal, alerter=alerter, confirm=2)
    for _ in range(5):
        r.check_dropped_leaders([])
    alerter.alert.assert_not_called()
    r.check_dropped_leaders(["0xSTILLHERE"])
    alerter.alert.assert_not_called()
    r.check_dropped_leaders(["0xSTILLHERE"])
    alerter.alert.assert_called_once()
