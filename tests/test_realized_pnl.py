"""Tests for scripts/realized_pnl.py — realized PnL by surface.

The script is read-only, but it produces the number a weight decision gets made
on, so a wrong answer here moves real money. Three things are pinned hardest:

  - pagination (a silent 2000-fill cap that drops the NEWEST fills — i.e. the
    post-fix window the whole item is about),
  - fee-token honesty (outcome legs pay in the outcome token; summing those
    into dollars invents a number),
  - INV 4 (a failed fetch is UNKNOWN and must abort, never report as flat).
"""

from __future__ import annotations

import json

import pytest

from scripts.realized_pnl import (
    HL_FILL_PAGE_LIMIT,
    MIN_CLOSING_FILLS_FOR_A_VERDICT,
    SURFACE_BASE,
    SURFACE_HIP3,
    SURFACE_OUTCOME,
    SURFACE_SPOT,
    aggregate,
    build_report,
    classify_surface,
    fetch_fills,
    main,
    parse_since,
    sample_verdict,
)


def _fill(coin="SOL", px="100", sz="1", pnl="0", fee="0.045", t=1_000, tid=None,
          fee_token="USDC"):
    return {
        "coin": coin, "px": px, "sz": sz, "closedPnl": pnl, "fee": fee,
        "time": t, "tid": tid if tid is not None else t, "feeToken": fee_token,
    }


class FakeInfo:
    """Stands in for hyperliquid.Info, serving fills from a fixed list.

    Mimics the real endpoint's contract exactly: ascending by time, at most
    HL_FILL_PAGE_LIMIT rows, `startTime` INCLUSIVE (so pages overlap).
    """

    def __init__(self, fills, fail_on_call=None, bad_shape=False):
        self.fills = sorted(fills, key=lambda f: f["time"])
        self.calls = 0
        self.fail_on_call = fail_on_call
        self.bad_shape = bad_shape

    def post(self, _path, payload):
        self.calls += 1
        if self.fail_on_call == self.calls:
            raise RuntimeError("boom")
        if self.bad_shape:
            return {"err": "nope"}
        start = payload["startTime"]
        return [f for f in self.fills if f["time"] >= start][:HL_FILL_PAGE_LIMIT]


# --------------------------------------------------------------------------
# surface classification
# --------------------------------------------------------------------------

@pytest.mark.parametrize("coin,surface,detail", [
    ("SOL", SURFACE_BASE, ""),
    ("XMR", SURFACE_BASE, ""),
    ("xyz:SP500", SURFACE_HIP3, "xyz"),
    ("para:FOO", SURFACE_HIP3, "para"),
    ("#21", SURFACE_OUTCOME, ""),
    ("#1420", SURFACE_OUTCOME, ""),
    ("+21", SURFACE_OUTCOME, ""),
    ("@230", SURFACE_SPOT, ""),
    ("PURR/USDC", SURFACE_SPOT, ""),
    ("", SURFACE_SPOT, ""),
])
def test_classify_surface(coin, surface, detail):
    assert classify_surface(coin) == (surface, detail)


def test_classify_is_not_hardcoded_to_xyz():
    """INV 1's rule: enumerate dexes, never special-case `xyz`.

    A dex we have never seen must still bucket as HIP-3 and carry its own name,
    or the next builder dex lands silently in `base` and corrupts base's net.
    """
    assert classify_surface("brandnew:ETH") == (SURFACE_HIP3, "brandnew")


# --------------------------------------------------------------------------
# --since parsing
# --------------------------------------------------------------------------

def test_parse_since_iso_z():
    # Cross-checked against `date -u -d 2026-08-15T13:47:00Z +%s` = 1786801620.
    assert parse_since("2026-08-15T13:47:00Z") == 1786801620000


def test_parse_since_naive_is_utc_not_local():
    """The box is UTC and a local-time fallback would shift the window silently."""
    assert parse_since("2026-08-15T13:47:00") == parse_since("2026-08-15T13:47:00Z")


def test_parse_since_epoch_seconds_and_ms_agree():
    assert parse_since("1786801620") == parse_since("1786801620000") == 1786801620000


def test_parse_since_zero_is_all_history():
    assert parse_since("0") == 0


@pytest.mark.parametrize("raw", ["", "   ", "not-a-date", "2026-13-45"])
def test_parse_since_rejects_garbage(raw):
    """Refuse rather than default: a silent fallback reports the wrong window
    with full confidence."""
    with pytest.raises(ValueError):
        parse_since(raw)


# --------------------------------------------------------------------------
# pagination — the trap that would have made the post-fix window read EMPTY
# --------------------------------------------------------------------------

def test_fetch_paginates_past_the_2000_cap():
    fills = [_fill(t=i + 1, tid=i + 1) for i in range(HL_FILL_PAGE_LIMIT + 231)]
    info = FakeInfo(fills)
    got = fetch_fills(info, "0xabc", 0)
    assert got is not None
    assert len(got) == HL_FILL_PAGE_LIMIT + 231
    assert info.calls > 1


def test_fetch_dedupes_the_inclusive_boundary_fill():
    """startTime is inclusive, so the last fill of page N reappears on page N+1.
    Counting it twice would double-count its PnL and its fee."""
    fills = [_fill(t=i + 1, tid=i + 1) for i in range(HL_FILL_PAGE_LIMIT + 5)]
    info = FakeInfo(fills)
    got = fetch_fills(info, "0xabc", 0)
    assert len({f["tid"] for f in got}) == len(got)


def test_fetch_single_short_page_makes_one_call():
    info = FakeInfo([_fill(t=1), _fill(t=2)])
    assert len(fetch_fills(info, "0xabc", 0)) == 2
    assert info.calls == 1


def test_fetch_respects_since():
    info = FakeInfo([_fill(t=10, tid=1), _fill(t=200, tid=2)])
    got = fetch_fills(info, "0xabc", 100)
    assert [f["tid"] for f in got] == [2]


# --------------------------------------------------------------------------
# INV 4 — unreadable is UNKNOWN, never empty
# --------------------------------------------------------------------------

def test_fetch_failure_returns_none_not_empty():
    """None and [] mean different things. [] would render every surface flat
    and the report would look like a quiet day."""
    assert fetch_fills(FakeInfo([_fill()], fail_on_call=1), "0xabc", 0) is None


def test_fetch_failure_on_a_later_page_returns_none():
    """Partial data is a WRONG answer, not a smaller one — the dropped page is
    the most recent, which is the window under test."""
    fills = [_fill(t=i + 1, tid=i + 1) for i in range(HL_FILL_PAGE_LIMIT + 10)]
    assert fetch_fills(FakeInfo(fills, fail_on_call=2), "0xabc", 0) is None


def test_fetch_bad_shape_returns_none():
    assert fetch_fills(FakeInfo([_fill()], bad_shape=True), "0xabc", 0) is None


def test_fetch_stalled_pagination_returns_none():
    """A full page sharing one timestamp cannot advance the cursor. Walking past
    it would drop the rest of that timestamp; we abort instead."""
    fills = [_fill(t=5, tid=i) for i in range(HL_FILL_PAGE_LIMIT)]
    assert fetch_fills(FakeInfo(fills), "0xabc", 0) is None


def test_fetch_empty_history_is_empty_not_none():
    """The other direction of INV 4: a READABLE source reporting nothing really
    does mean nothing. Fail-open must not become never-answer."""
    got = fetch_fills(FakeInfo([]), "0xabc", 0)
    assert got == []
    assert got is not None


def test_main_aborts_when_fetch_fails(monkeypatch, capsys):
    monkeypatch.setattr("scripts.realized_pnl.Info", lambda *a, **k: object())
    monkeypatch.setattr("scripts.realized_pnl.fetch_fills", lambda *a, **k: None)
    assert main(["--address", "0xabc"]) == 1
    assert "ABORT" in capsys.readouterr().err


def test_main_requires_an_address(monkeypatch, capsys):
    monkeypatch.delenv("HL_ACCOUNT_ADDRESS", raising=False)
    assert main([]) == 2
    assert "account address" in capsys.readouterr().err


def test_main_rejects_a_bad_since(capsys):
    assert main(["--address", "0xabc", "--since", "garbage"]) == 2
    assert "bad timestamp" in capsys.readouterr().err


# --------------------------------------------------------------------------
# aggregation
# --------------------------------------------------------------------------

def test_aggregate_splits_by_surface():
    fills = [
        _fill(coin="SOL", px="100", sz="1", pnl="5", fee="0.045", t=10),
        _fill(coin="xyz:SP500", px="50", sz="2", pnl="-3", fee="0.020", t=11),
        _fill(coin="#21", px="0.3", sz="10", pnl="1", fee="0", t=12),
    ]
    st = aggregate(fills, 0)
    assert st[SURFACE_BASE].realized_usd == 5.0
    assert st[SURFACE_HIP3].realized_usd == -3.0
    assert st[SURFACE_OUTCOME].realized_usd == 1.0
    assert st[SURFACE_BASE].notional_usd == 100.0
    assert st[SURFACE_HIP3].notional_usd == 100.0


def test_net_is_realized_minus_fees():
    st = aggregate([_fill(coin="SOL", pnl="10", fee="0.5")], 0)
    assert st[SURFACE_BASE].realized_usd == 10.0
    assert st[SURFACE_BASE].fees_usd == 0.5
    assert st[SURFACE_BASE].net_usd == 9.5


def test_opening_and_closing_fills_are_counted_separately():
    """PnL books only on closes. A window of pure opens has sample size zero
    however busy it looks, and a reader must be able to see that."""
    st = aggregate([
        _fill(coin="SOL", pnl="0", t=1),
        _fill(coin="SOL", pnl="0", t=2),
        _fill(coin="SOL", pnl="4", t=3),
    ], 0)
    s = st[SURFACE_BASE]
    assert (s.fills, s.opening_fills, s.closing_fills) == (3, 2, 1)


def test_aggregate_applies_the_window():
    fills = [_fill(coin="SOL", pnl="100", t=10), _fill(coin="SOL", pnl="7", t=500)]
    assert aggregate(fills, 100)[SURFACE_BASE].realized_usd == 7.0
    assert aggregate(fills, 100)[SURFACE_BASE].fills == 1


def test_effective_bps_is_fees_over_notional():
    st = aggregate([_fill(coin="SOL", px="1000", sz="1", fee="0.45")], 0)
    assert st[SURFACE_BASE].effective_bps == pytest.approx(4.5)


def test_effective_bps_is_none_without_notional():
    assert aggregate([], 0)[SURFACE_BASE].effective_bps is None


def test_notional_uses_absolute_value():
    """Sells must add to notional, not subtract from it."""
    st = aggregate([_fill(coin="SOL", px="-100", sz="1")], 0)
    assert st[SURFACE_BASE].notional_usd == 100.0


def test_hip3_detail_splits_by_dex():
    """INV 2 — separate clearinghouses. The pooled hip3 row can hide one dex
    funding another's losses, so the per-dex notional must survive."""
    st = aggregate([
        _fill(coin="xyz:SP500", px="50", sz="2", t=1),
        _fill(coin="para:FOO", px="10", sz="1", t=2),
    ], 0)
    assert st[SURFACE_HIP3].detail_notional == {"xyz": 100.0, "para": 10.0}


def test_unparseable_fill_is_skipped_not_counted_as_zero(capsys):
    """INV 5: a dropped row gets its own visible reason. Coercing it to 0.0
    would silently dilute the mean."""
    st = aggregate([
        _fill(coin="SOL", px="oops", sz="1", pnl="5"),
        _fill(coin="SOL", px="100", sz="1", pnl="5"),
    ], 0)
    assert st[SURFACE_BASE].fills == 1
    assert st[SURFACE_BASE].realized_usd == 5.0
    assert "unparseable" in capsys.readouterr().err


# --------------------------------------------------------------------------
# fee-token honesty — outcome legs pay in the outcome token, not USDC
# --------------------------------------------------------------------------

def test_non_usdc_fee_is_not_summed_into_dollars():
    st = aggregate([_fill(coin="#21", px="0.3", sz="10", fee="0.004", fee_token="+21")], 0)
    s = st[SURFACE_OUTCOME]
    assert s.fees_usd == 0.0
    assert s.non_usdc_fee_fills == 1
    assert s.non_usdc_fee_tokens == {"+21": 0.004}
    assert s.fees_complete is False


def test_usdc_only_surface_reports_fees_complete():
    assert aggregate([_fill(coin="SOL", fee="0.045")], 0)[SURFACE_BASE].fees_complete


def test_mixed_fee_tokens_keep_the_usdc_part_exact():
    """The USDC fees on a surface are still real and still summable; only the
    foreign-token ones are held back."""
    st = aggregate([
        _fill(coin="#21", fee="0.5", fee_token="USDC", t=1),
        _fill(coin="#22", fee="0.004", fee_token="+22", t=2),
    ], 0)
    s = st[SURFACE_OUTCOME]
    assert s.fees_usd == 0.5
    assert s.non_usdc_fee_tokens == {"+22": 0.004}


def test_zero_non_usdc_fee_does_not_flag_the_surface():
    """A zero fee costs nothing in any denomination — flagging it would put a
    permanent asterisk on outcomes for no reason."""
    st = aggregate([_fill(coin="#21", fee="0", fee_token="+21")], 0)
    assert st[SURFACE_OUTCOME].fees_complete is True


def test_report_flags_incomplete_fees():
    fills = [_fill(coin="#21", px="0.3", sz="10", fee="0.004", fee_token="+21")]
    text, _ = build_report(fills, 0, 10_000)
    assert "fees INCOMPLETE" in text
    assert "UPPER bound" in text


# --------------------------------------------------------------------------
# sample sufficiency — criterion 4
# --------------------------------------------------------------------------

def test_no_closing_fills_is_insufficient():
    st = aggregate([_fill(coin="SOL", pnl="0")], 0)
    ok, why = sample_verdict(st[SURFACE_BASE])
    assert ok is False
    assert "no closing fills" in why


def test_too_few_closing_fills_is_insufficient():
    fills = [_fill(coin="SOL", pnl="5", t=i) for i in range(5)]
    ok, why = sample_verdict(aggregate(fills, 0)[SURFACE_BASE])
    assert ok is False
    assert "closing fills" in why


def test_noisy_sample_is_insufficient_even_when_large():
    """Enough fills, but the mean sits inside two standard errors of zero.
    This is the case that produced 'the surface that works' (INV 10)."""
    pnls = [10.0, -10.0] * 40
    fills = [_fill(coin="SOL", pnl=str(p), t=i) for i, p in enumerate(pnls)]
    ok, why = sample_verdict(aggregate(fills, 0)[SURFACE_BASE])
    assert ok is False
    assert "indistinguishable from zero" in why


def test_large_consistent_sample_is_sufficient():
    fills = [
        _fill(coin="SOL", pnl=str(5.0 + (i % 3) * 0.1), t=i)
        for i in range(MIN_CLOSING_FILLS_FOR_A_VERDICT + 20)
    ]
    ok, why = sample_verdict(aggregate(fills, 0)[SURFACE_BASE])
    assert ok is True
    assert "n=" in why


def test_verdict_counts_closing_fills_not_total_fills():
    """500 opens and 4 closes is a sample of 4."""
    fills = [_fill(coin="SOL", pnl="0", t=i) for i in range(500)]
    fills += [_fill(coin="SOL", pnl="5", t=1000 + i) for i in range(4)]
    ok, why = sample_verdict(aggregate(fills, 0)[SURFACE_BASE])
    assert ok is False
    assert "only 4 closing fills" in why


# --------------------------------------------------------------------------
# report assembly — criterion 2 (two windows, separately)
# --------------------------------------------------------------------------

def test_report_separates_history_from_post_fix():
    """The whole point of the item: pre-fix xyz measures the bugs, so it must
    never be pooled into the clean window."""
    fills = [
        _fill(coin="xyz:SP500", px="50", sz="2", pnl="-80", t=1_000),
        _fill(coin="xyz:SP500", px="50", sz="2", pnl="12", t=9_000),
    ]
    _, res = build_report(fills, 0, 5_000)
    assert res["full_history"][SURFACE_HIP3]["realized_usd"] == -68.0
    assert res["post_fix"][SURFACE_HIP3]["realized_usd"] == 12.0


def test_report_renders_both_window_headings():
    text, _ = build_report([_fill(coin="SOL", pnl="5")], 0, 10_000)
    assert "FULL HISTORY" in text
    assert "POST-FIX WINDOW" in text


def test_report_states_sufficiency_for_every_surface_present():
    text, _ = build_report([_fill(coin="SOL", pnl="5", t=1)], 0, 10_000)
    assert "Is the sample big enough to conclude anything?" in text


def test_report_json_is_serialisable_and_omits_private_fields():
    _, res = build_report([_fill(coin="SOL", pnl="5")], 0, 10_000)
    blob = json.dumps(res)
    assert "_closed" not in blob
    assert res["full_history"][SURFACE_BASE]["sample_sufficient"] is False


def test_report_handles_no_fills_at_all():
    text, res = build_report([], 0, 10_000)
    assert "TOTAL" in text
    assert res["full_history"] == {}


def test_empty_post_fix_window_is_visible_not_silent():
    """A window with nothing in it must still render, so 'no data yet' cannot be
    mistaken for 'flat'."""
    text, res = build_report([_fill(coin="SOL", pnl="5", t=100)], 0, 10_000)
    assert res["post_fix"] == {}
    assert "POST-FIX WINDOW" in text


def test_main_end_to_end(monkeypatch, capsys, tmp_path):
    fills = [
        _fill(coin="SOL", px="100", sz="1", pnl="5", fee="0.045", t=1_000, tid=1),
        _fill(coin="xyz:SP500", px="50", sz="2", pnl="-3", fee="0.02", t=9_000, tid=2),
    ]
    monkeypatch.setattr("scripts.realized_pnl.Info", lambda *a, **k: FakeInfo(fills))
    out = tmp_path / "r.json"
    rc = main(["--address", "0xabc", "--since", "0",
               "--post-fix-since", "1970-01-01T00:00:05Z", "--json", str(out)])
    assert rc == 0
    text = capsys.readouterr().out
    assert "FULL HISTORY" in text and "POST-FIX WINDOW" in text
    saved = json.loads(out.read_text())
    assert saved["full_history"][SURFACE_BASE]["net_usd"] == pytest.approx(4.955)
    assert saved["post_fix"][SURFACE_HIP3]["realized_usd"] == -3.0


def test_main_fetches_once_for_both_windows(monkeypatch):
    """INV 7 — HL 429s on back-to-back /info calls. Two windows must not mean
    two fetches."""
    info = FakeInfo([_fill(coin="SOL", pnl="5", t=1_000)])
    monkeypatch.setattr("scripts.realized_pnl.Info", lambda *a, **k: info)
    main(["--address", "0xabc", "--since", "0", "--post-fix-since", "1970-01-01T00:00:05Z"])
    assert info.calls == 1
