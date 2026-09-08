"""One paginated reader for Hyperliquid's `userFillsByTime`.

`userFillsByTime` caps every response at 2,000 rows and returns them
**oldest-first**. Ask for 30 days of a high-frequency wallet and you get the
first ~2 days of the window; the rest of the month is simply absent, with no
error and no marker that anything was cut.

Measured 2026-08-21 on `0x7177edd4` (leaderboard rank 2, 30,127 trades,
$4.38M volume, $776,961 of collateral on xyz):

    userFillsByTime(startTime = now-30d) -> 2000 fills, ALL of them #NNNNN
    userFills (most recent 2000)         -> xyz:UNITREE 798, xyz:CXMT 186, ...

The two windows do not share a single coin. `_is_perp_coin` reads `#NNNNN` as
non-perp, so with `score_perp_only: true` that wallet scored **0 perp trades**
and was rejected as `trades=0 < 50`, and `src.backtest` scored it at
0 trades / 0 closes / $0.00. Neither number was a finding about the leader —
both were an artifact of the cap. Every `trades=0` on a high-frequency wallet
was unfalsifiable until this module existed.

This is deliberately transport-agnostic: `leader_score` reads through
`InfoProto`, `backtest` reads through raw urllib, and `scripts/realized_pnl`
reads through a live `Info`. The backlog item requires all of them to share
ONE pager — discovery and the backtest disagreeing about what a leader did is
how a leader gets added on evidence the backtest cannot reproduce. Callers
supply the transport (and their own retry policy); the paging, the de-dupe and
the truncation rules live here, once.

INV 4: a page we could not read makes the whole window UNKNOWN, so this
returns `None`, never a short list. Partial history is not a smaller answer,
it is a WRONG one — the missing page is always the most recent, which is the
part every decision is made on. INV 5: every path that gives up logs its own
greppable reason; silent truncation is the defect being fixed here, so this
module must never introduce a quieter version of it.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Iterable

log = logging.getLogger(__name__)

# HL's hard server-side cap on one `userFillsByTime` response. A full page is
# the only signal that more history exists past it.
HL_FILL_PAGE_LIMIT = 2000

# Generous ceiling for offline/script use: 200 * 2000 = 400k fills.
DEFAULT_MAX_PAGES = 200


def paginate_user_fills(
    fetch_page: Callable[[int], Any],
    since_ms: int,
    *,
    label: str = "",
    page_limit: int = HL_FILL_PAGE_LIMIT,
    max_pages: int = DEFAULT_MAX_PAGES,
    page_delay_s: float = 0.0,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]] | None:
    """Every fill from `since_ms` to now, oldest-first. `None` if unknowable.

    `fetch_page(start_time_ms)` returns one raw HL response. It owns its own
    retry policy; returning `None` (or anything that is not a list) means it
    has already given up, and that ends the whole walk as UNKNOWN.

    Paging walks `startTime` forward to the last fill's `time`. That bound is
    INCLUSIVE, so consecutive pages always overlap by at least the boundary
    fill — hence the de-dupe on `tid`, which is unique per fill.

    Returns `None` — never a truncated list — when:
      - a page is unreadable (INV 4),
      - the cursor cannot advance because a whole page shares one millisecond
        (stepping +1ms past it would silently drop the remainder),
      - `max_pages` runs out with a full page still pending.

    `page_delay_s` is paid only BETWEEN pages, so the common case (one short
    page) costs nothing. It exists because scoring 60 candidates used to be 60
    /info calls and could now be several hundred, and INV 7 records HL 429-ing
    us over back-to-back /info calls.
    """
    out: list[dict[str, Any]] = []
    seen: set[Any] = set()
    cursor = since_ms

    for page_no in range(1, max_pages + 1):
        batch = fetch_page(cursor)
        if not isinstance(batch, list):
            # Covers the None the caller returns after its retries are spent,
            # and any malformed body. Either way we do not know the window.
            log.warning(
                "hl_fills: unreadable page %d for %s at startTime=%d (got %s) "
                "-> fills_page_unreadable",
                page_no, label or "?", cursor, type(batch).__name__,
            )
            return None
        if not batch:
            break

        out.extend(_dedupe(batch, seen))

        if len(batch) < page_limit:
            # A short page means HL had nothing more to give: window covered.
            break

        try:
            nxt = int(batch[-1].get("time", 0))
        except (TypeError, ValueError):
            log.warning(
                "hl_fills: page %d for %s has an unparseable trailing time "
                "-> fills_pagination_bad_cursor", page_no, label or "?",
            )
            return None

        if nxt <= cursor:
            # No forward progress: the full page shares one timestamp. Walking
            # by +1ms would drop whatever else happened in that millisecond,
            # which is exactly the silent truncation this module exists to end.
            log.warning(
                "hl_fills: pagination stalled for %s at startTime=%d (page %d "
                "did not advance) -> fills_pagination_stalled",
                label or "?", cursor, page_no,
            )
            return None
        cursor = nxt

        if page_delay_s > 0:
            sleep(page_delay_s)
    else:
        # Loop ran to `max_pages` with the last page still full, so history
        # remains. Returning what we have would be the original bug wearing a
        # bigger number, so refuse and say why.
        log.warning(
            "hl_fills: page cap %d exhausted for %s with more history pending "
            "(%d fills read) -> fills_pagination_cap_exhausted",
            max_pages, label or "?", len(out),
        )
        return None

    return out


def _dedupe(batch: Iterable[dict[str, Any]], seen: set[Any]) -> list[dict[str, Any]]:
    """Drop fills already returned by an earlier page, preserving HL's order.

    Fills without a `tid` are kept unconditionally: every real HL fill carries
    one, and dropping an unidentifiable fill would under-report. Duplicating it
    is the cheaper error of the two, and it is visible in the output.
    """
    kept: list[dict[str, Any]] = []
    for f in batch:
        if not isinstance(f, dict):
            continue
        tid = f.get("tid")
        if tid is not None:
            if tid in seen:
                continue
            seen.add(tid)
        kept.append(f)
    return kept
