"""Tests for the shared `userFillsByTime` pager.

The defect being pinned: HL caps a response at 2,000 rows returned
OLDEST-first, so an unpaginated 30-day read of a busy wallet returns its first
two days and nothing says so. That made `trades=0` unfalsifiable — it could
mean "inactive" or "we stopped reading" and there was no way to tell.

Every give-up path is asserted to return None rather than a short list: a
truncated history is a WRONG answer, not a smaller one, because the part
dropped is always the most recent (INV 4).
"""

from __future__ import annotations

import pytest

from src.hl_fills import HL_FILL_PAGE_LIMIT, paginate_user_fills


def _fill(t: int, tid: int | None = None, coin: str = "SOL") -> dict:
    return {"coin": coin, "time": t, "tid": tid if tid is not None else t, "px": "1"}


class FakePages:
    """Mimics `userFillsByTime`: ascending by time, <= page_limit rows,
    `startTime` INCLUSIVE (so consecutive pages overlap by the boundary fill)."""

    def __init__(self, fills, page_limit=HL_FILL_PAGE_LIMIT, fail_on_call=None,
                 bad_shape_on_call=None):
        self.fills = sorted(fills, key=lambda f: f["time"])
        self.page_limit = page_limit
        self.fail_on_call = fail_on_call
        self.bad_shape_on_call = bad_shape_on_call
        self.calls = 0
        self.cursors: list[int] = []

    def __call__(self, start_ms):
        self.calls += 1
        self.cursors.append(start_ms)
        if self.fail_on_call == self.calls:
            return None
        if self.bad_shape_on_call == self.calls:
            return {"error": "nope"}
        return [f for f in self.fills if f["time"] >= start_ms][: self.page_limit]


# ---------------------------------------------------------------------------
# the headline: reading past the 2,000-row cap
# ---------------------------------------------------------------------------

def test_paginates_past_the_page_cap():
    fills = [_fill(t=i + 1) for i in range(HL_FILL_PAGE_LIMIT + 317)]
    pages = FakePages(fills)
    got = paginate_user_fills(pages, 0)
    assert got is not None
    assert len(got) == HL_FILL_PAGE_LIMIT + 317
    assert pages.calls > 1


def test_recovers_the_fills_a_single_call_would_have_hidden():
    """The 0x7177edd4 shape: the visible slice is one coin, the hidden tail is
    the coin that decides whether the wallet is copyable at all."""
    old = [_fill(t=i + 1, coin="#10411") for i in range(HL_FILL_PAGE_LIMIT)]
    new = [_fill(t=HL_FILL_PAGE_LIMIT + i + 1, coin="xyz:UNITREE") for i in range(40)]
    got = paginate_user_fills(FakePages(old + new), 0)
    coins = {f["coin"] for f in got}
    assert coins == {"#10411", "xyz:UNITREE"}
    assert sum(1 for f in got if f["coin"] == "xyz:UNITREE") == 40


def test_single_short_page_makes_exactly_one_call():
    pages = FakePages([_fill(t=1), _fill(t=2)])
    assert len(paginate_user_fills(pages, 0)) == 2
    assert pages.calls == 1


def test_preserves_oldest_first_order():
    fills = [_fill(t=i + 1) for i in range(HL_FILL_PAGE_LIMIT + 9)]
    got = paginate_user_fills(FakePages(fills), 0)
    assert [f["time"] for f in got] == sorted(f["time"] for f in got)


def test_respects_since():
    pages = FakePages([_fill(t=10, tid=1), _fill(t=200, tid=2)])
    assert [f["tid"] for f in paginate_user_fills(pages, 100)] == [2]


def test_empty_history_is_empty_list_not_none():
    """Nothing to read is a FACT — distinct from a failed read (INV 4)."""
    got = paginate_user_fills(FakePages([]), 0)
    assert got == []


# ---------------------------------------------------------------------------
# de-dupe: startTime is inclusive, so pages overlap by construction
# ---------------------------------------------------------------------------

def test_dedupes_the_inclusive_boundary_fill():
    fills = [_fill(t=i + 1) for i in range(HL_FILL_PAGE_LIMIT + 5)]
    got = paginate_user_fills(FakePages(fills), 0)
    assert len({f["tid"] for f in got}) == len(got)


def test_boundary_fill_appears_exactly_once_by_tid():
    fills = [_fill(t=i + 1) for i in range(HL_FILL_PAGE_LIMIT + 3)]
    got = paginate_user_fills(FakePages(fills), 0)
    boundary_tid = HL_FILL_PAGE_LIMIT
    assert [f["tid"] for f in got].count(boundary_tid) == 1


def test_fills_without_tid_are_kept_not_dropped():
    """Under-reporting is the failure mode we are fixing; a duplicate is at
    least visible, a dropped fill is not."""
    page = [{"coin": "SOL", "time": 1}, {"coin": "SOL", "time": 2}]
    got = paginate_user_fills(lambda _s: page, 0)
    assert len(got) == 2


def test_non_dict_rows_are_skipped():
    got = paginate_user_fills(lambda _s: [_fill(t=1), "garbage", _fill(t=2)], 0)
    assert len(got) == 2


# ---------------------------------------------------------------------------
# INV 4 — unreadable is UNKNOWN, never a short list
# ---------------------------------------------------------------------------

def test_first_page_unreadable_returns_none():
    assert paginate_user_fills(FakePages([_fill(t=1)], fail_on_call=1), 0) is None


def test_later_page_unreadable_returns_none_not_partial():
    """The dropped page is always the most recent — the window every decision
    is actually about."""
    fills = [_fill(t=i + 1) for i in range(HL_FILL_PAGE_LIMIT + 10)]
    assert paginate_user_fills(FakePages(fills, fail_on_call=2), 0) is None


def test_malformed_body_returns_none():
    assert paginate_user_fills(FakePages([_fill(t=1)], bad_shape_on_call=1), 0) is None


def test_pagination_stall_returns_none():
    """A full page sharing one millisecond cannot advance the cursor. Stepping
    +1ms past it would silently drop the rest of that millisecond."""
    fills = [_fill(t=7, tid=i) for i in range(HL_FILL_PAGE_LIMIT)]
    assert paginate_user_fills(FakePages(fills), 0) is None


def test_unparseable_trailing_time_returns_none():
    page = [_fill(t=i + 1) for i in range(HL_FILL_PAGE_LIMIT - 1)]
    page.append({"coin": "SOL", "time": "not-a-number", "tid": 99999})
    assert paginate_user_fills(lambda _s: page, 0) is None


def test_page_cap_exhausted_returns_none_not_truncated():
    """The cap must not become a politer version of the original bug."""
    fills = [_fill(t=i + 1) for i in range(HL_FILL_PAGE_LIMIT * 3)]
    assert paginate_user_fills(FakePages(fills), 0, max_pages=2) is None


def test_page_cap_not_tripped_when_history_ends_exactly_at_the_cap():
    """Fail-open must not become never-act: a walk that genuinely finished on
    its last allowed page is a complete answer, not an exhausted one."""
    fills = [_fill(t=i + 1) for i in range(HL_FILL_PAGE_LIMIT + 5)]
    got = paginate_user_fills(FakePages(fills), 0, max_pages=2)
    assert got is not None
    assert len(got) == HL_FILL_PAGE_LIMIT + 5


# ---------------------------------------------------------------------------
# rate limiting (INV 7) — the delay is paid only when there IS a next page
# ---------------------------------------------------------------------------

def test_no_delay_is_paid_for_a_single_short_page():
    slept: list[float] = []
    paginate_user_fills(FakePages([_fill(t=1)]), 0, page_delay_s=0.5,
                        sleep=slept.append)
    assert slept == []


def test_delay_is_paid_between_pages():
    fills = [_fill(t=i + 1) for i in range(HL_FILL_PAGE_LIMIT + 5)]
    slept: list[float] = []
    paginate_user_fills(FakePages(fills), 0, page_delay_s=0.5, sleep=slept.append)
    assert slept == [0.5]


# ---------------------------------------------------------------------------
# cursor walk
# ---------------------------------------------------------------------------

def test_cursor_advances_to_last_fill_time():
    fills = [_fill(t=i + 1) for i in range(HL_FILL_PAGE_LIMIT + 5)]
    pages = FakePages(fills)
    paginate_user_fills(pages, 0)
    assert pages.cursors == [0, HL_FILL_PAGE_LIMIT]
