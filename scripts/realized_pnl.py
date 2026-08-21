#!/usr/bin/env python
"""Realized PnL net of fees, split by trading surface, for an arbitrary window.

BACKLOG P3. Read-only. Places no orders, writes no config, imports nothing that
trades — safe to run while the bot is live.

WHY THIS EXISTS
---------------
INV 10: we judge on REALIZED PnL, not unrealized. On 2026-08-15 xyz was called
"the surface that works" off +$12.48 *unrealized* while its realized was
-$87.03. Unrealized is a marked opinion; realized is a fact. This script only
ever reports facts: `closedPnl` and `fee`, both booked by HL at fill time.

The second reason is the window. Realized-over-all-history says base +$96.73 /
xyz -$89.54, but xyz only became correctly tradeable on 2026-08-15 — szDecimals,
the per-dex cap and the reconcile HIP-3 fix all landed that day (INV 1, INV 2).
Every xyz fill before then was placed by a bot that was mis-sizing and having
its positions zeroed under it. Judging the surface on that history judges the
bugs, not the surface. Hence `--since`, and hence the post-fix window is broken
out separately by default.

WHAT "REALIZED" MEANS HERE
-------------------------
`realized = sum(closedPnl)`, `net = realized - fees`. `closedPnl` is non-zero
only on the closing portion of a fill, so opening fills contribute notional and
fees but no PnL. That is the correct accounting and it is also why `net` for a
young window is usually negative: the entry fees are booked immediately and the
PnL only lands when the position closes. A window that mostly OPENED positions
will look worse than it is. The report prints open/close fill counts so this is
visible rather than something you have to remember.

TWO TRAPS THIS SCRIPT EXISTS TO AVOID
-------------------------------------
1. `userFillsByTime` is capped at 2000 fills per response and the cap is SILENT
   — you get 2000 rows and no error. Measured 2026-08-16: a single call with
   startTime=0 returned 2000 fills ending 2026-08-09, dropping the most recent
   231. Those are exactly the fills a post-fix window is about, so the naive
   one-call version of this script would have reported the post-fix window as
   EMPTY and looked correct doing it. We paginate and dedupe on `tid`.

2. Fees are not all USDC. Outcome legs pay in the outcome token itself
   (`feeToken: "+21"`, `"+1420"`, `"+1430"`) and one spot fill paid `USDH`.
   Summing those into a dollar figure is inventing a number — we have no price
   for them here. They are counted and reported separately, and any surface
   carrying one is flagged, so a fee total is never quietly wrong. Measured
   2026-08-16: 7 such fills, 0.0087 raw token units, all on outcome/spot.

USAGE
    .venv/bin/python -m scripts.realized_pnl
    .venv/bin/python -m scripts.realized_pnl --since 2026-08-15T13:47:00Z
    .venv/bin/python -m scripts.realized_pnl --since 0 --json out.json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from hyperliquid.info import Info

from src.hl_fills import HL_FILL_PAGE_LIMIT, paginate_user_fills

# The reconcile HIP-3 fix (INV 1) — the point after which an xyz fill was placed
# by a bot that could actually size and hold an xyz position. Everything before
# this is contaminated by the broken period and must not be pooled with it.
POST_FIX_ISO = "2026-08-15T13:47:00Z"

# HL's hard page size for userFillsByTime lives in `src.hl_fills` and is
# re-exported here for the callers/tests that already import it from this
# module. One definition: two copies is how the pagers drift apart.
__all_page_limit__ = HL_FILL_PAGE_LIMIT

SURFACE_BASE = "base"
SURFACE_HIP3 = "hip3"
SURFACE_OUTCOME = "outcome"
SURFACE_SPOT = "spot"

# Order surfaces are printed in: the two that carry the strategy first.
SURFACE_ORDER = (SURFACE_BASE, SURFACE_HIP3, SURFACE_OUTCOME, SURFACE_SPOT)

# Below this many CLOSING fills, a mean has no meaning regardless of what the
# t-statistic says — a handful of fills can produce an arbitrarily clean number.
MIN_CLOSING_FILLS_FOR_A_VERDICT = 30


def classify_surface(coin: str) -> tuple[str, str]:
    """Map a fill's `coin` to (surface, detail).

    Deliberately NOT special-cased to `xyz` (INV 1's rule): any `<dex>:<COIN>`
    is a HIP-3 clearinghouse and is bucketed as one. We already trade `para:`
    as well as `xyz:`, and hard-coding `xyz` is how a module ends up blind to
    the next dex that appears.

    `detail` carries the dex name for HIP-3 so the per-dex split is available
    without re-parsing; it is empty for every other surface.
    """
    if not coin:
        return SURFACE_SPOT, ""
    # Outcome legs are `#<encoding>`; their fee token is `+<encoding>`.
    if coin.startswith("#") or coin.startswith("+"):
        return SURFACE_OUTCOME, ""
    if ":" in coin:
        return SURFACE_HIP3, coin.split(":", 1)[0]
    # Spot is `@<index>` or a `BASE/QUOTE` pair. Checked after the HIP-3 test
    # because a HIP-3 coin can contain neither.
    if coin.startswith("@") or "/" in coin:
        return SURFACE_SPOT, ""
    return SURFACE_BASE, ""


def parse_since(raw: str) -> int:
    """Parse `--since` into epoch ms. Accepts ISO-8601, epoch s, or epoch ms.

    Raises ValueError rather than falling back to a default: silently starting
    from the wrong point produces a confident report about the wrong window,
    which is worse than refusing to run.
    """
    raw = raw.strip()
    if not raw:
        raise ValueError("empty --since")
    if raw.isdigit():
        n = int(raw)
        # A plain epoch-seconds value for any date we care about is 10 digits;
        # ms is 13. Anything under the threshold is seconds.
        return n * 1000 if n < 100_000_000_000 else n
    iso = raw.replace("Z", "+00:00")
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:  # bare timestamps are UTC, never local — the box is UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def fetch_fills(info: Any, address: str, since_ms: int) -> list[dict[str, Any]] | None:
    """Every fill from `since_ms` to now, paginated. None on failure.

    None, never `[]` (INV 4): "the fetch broke" and "you traded nothing" are
    different facts, and this script's whole output is a judgement about how
    much we traded. A caller that cannot tell them apart will report a failed
    fetch as a flat surface.

    The paging itself lives in `src.hl_fills` so that this script, discovery
    (`leader_score`) and `src.backtest` cannot drift into three different ideas
    of what a wallet's history is.
    """

    def fetch_page(start_ms: int) -> list[dict[str, Any]] | None:
        try:
            return info.post(
                "/info",
                {"type": "userFillsByTime", "user": address.lower(), "startTime": start_ms},
            )
        except Exception as e:  # noqa: BLE001 — partial data would be a wrong answer
            print(f"  ! fills fetch failed at {iso(start_ms)}: {type(e).__name__}: {e}",
                  file=sys.stderr)
            return None

    return paginate_user_fills(
        fetch_page, since_ms, label=address[:10], page_limit=HL_FILL_PAGE_LIMIT
    )


@dataclass
class SurfaceStats:
    """Realized accounting for one surface over one window."""

    surface: str
    fills: int = 0
    opening_fills: int = 0
    closing_fills: int = 0  # fills with non-zero closedPnl — where PnL is booked
    notional_usd: float = 0.0
    realized_usd: float = 0.0  # sum(closedPnl), gross of fees
    fees_usd: float = 0.0  # USDC-denominated fees ONLY
    non_usdc_fee_fills: int = 0
    non_usdc_fee_tokens: dict[str, float] = field(default_factory=dict)
    detail_notional: dict[str, float] = field(default_factory=dict)
    first_ms: int = 0
    last_ms: int = 0
    _closed: list[float] = field(default_factory=list, repr=False)

    @property
    def net_usd(self) -> float:
        """Realized minus the fees we can actually price. See `fees_complete`."""
        return self.realized_usd - self.fees_usd

    @property
    def fees_complete(self) -> bool:
        """False when this surface paid a fee we have no USD price for."""
        return self.non_usdc_fee_fills == 0

    @property
    def effective_bps(self) -> float | None:
        """USDC fees as bps of notional. None when there is no notional."""
        if self.notional_usd <= 0:
            return None
        return self.fees_usd / self.notional_usd * 10_000.0


def aggregate(fills: list[dict[str, Any]], since_ms: int) -> dict[str, SurfaceStats]:
    """Bucket fills by surface. Only fills at/after `since_ms` are counted.

    The window is re-applied here even though `fetch_fills` already passed
    `startTime`: pagination re-reads the boundary page, and a caller may pass
    a pre-fetched list covering a wider span (the default run does exactly
    that — one fetch, two windows).
    """
    stats: dict[str, SurfaceStats] = {s: SurfaceStats(surface=s) for s in SURFACE_ORDER}
    for f in fills:
        t = int(f.get("time", 0))
        if t < since_ms:
            continue
        coin = str(f.get("coin", ""))
        surface, detail = classify_surface(coin)
        s = stats[surface]

        try:
            px = float(f.get("px", 0) or 0)
            sz = float(f.get("sz", 0) or 0)
            pnl = float(f.get("closedPnl", 0) or 0)
            fee = float(f.get("fee", 0) or 0)
        except (TypeError, ValueError):
            # A malformed fill is not a zero fill. Skip it loudly rather than
            # let it dilute a mean (INV 5: no silent drops).
            print(f"  ! unparseable fill on {coin} at {iso(t)}, skipped", file=sys.stderr)
            continue

        s.fills += 1
        s.notional_usd += abs(px * sz)
        s.realized_usd += pnl
        if pnl:
            s.closing_fills += 1
            s._closed.append(pnl)
        else:
            s.opening_fills += 1

        # Fees: only USDC is summed into dollars. Anything else is counted in
        # its own token — we have no price for it here and a guessed one would
        # make every downstream number quietly wrong.
        token = str(f.get("feeToken", "USDC") or "USDC")
        if token == "USDC":
            s.fees_usd += fee
        elif fee:
            s.non_usdc_fee_fills += 1
            s.non_usdc_fee_tokens[token] = s.non_usdc_fee_tokens.get(token, 0.0) + fee

        if detail:
            s.detail_notional[detail] = s.detail_notional.get(detail, 0.0) + abs(px * sz)
        s.first_ms = t if not s.first_ms else min(s.first_ms, t)
        s.last_ms = max(s.last_ms, t)
    return stats


def sample_verdict(s: SurfaceStats) -> tuple[bool, str]:
    """Can this surface's net figure support a conclusion? (sufficient, why).

    Two hurdles, both of which must clear:

      1. At least `MIN_CLOSING_FILLS_FOR_A_VERDICT` CLOSING fills. PnL is only
         booked on closes, so a window with 500 opens and 4 closes has a sample
         size of 4 no matter how busy it looks.
      2. The mean closed PnL must be at least two standard errors from zero.
         Below that we cannot distinguish the surface from noise, and copy-trade
         PnL is heavy-tailed enough that this bar is generous, not strict.

    Deliberately conservative: the cost of declaring a surface good on thin data
    is a weight change on a live account, which is how xyz got called "the
    surface that works" while realizing -$87.03 (INV 10).
    """
    n = s.closing_fills
    if n == 0:
        return False, "no closing fills — nothing realized in this window"
    if n < MIN_CLOSING_FILLS_FOR_A_VERDICT:
        return False, f"only {n} closing fills (want >= {MIN_CLOSING_FILLS_FOR_A_VERDICT})"
    if n < 2:
        return False, "need >= 2 closing fills for a dispersion estimate"
    mean = statistics.fmean(s._closed)
    sd = statistics.stdev(s._closed)
    if sd == 0:
        return True, f"n={n}, zero dispersion"
    se = sd / (n ** 0.5)
    t = abs(mean) / se if se else 0.0
    if t < 2.0:
        return False, (
            f"n={n}, mean ${mean:+.3f} +/- ${se:.3f} SE (t={t:.2f}) — "
            "indistinguishable from zero"
        )
    return True, f"n={n}, mean ${mean:+.3f} +/- ${se:.3f} SE (t={t:.2f})"


def format_window(title: str, since_ms: int, stats: dict[str, SurfaceStats]) -> str:
    """Render one window's table plus its per-surface sufficiency verdict."""
    lines: list[str] = []
    lines.append("=" * 100)
    lines.append(f"{title}   (since {iso(since_ms)} UTC)")
    lines.append("=" * 100)
    hdr = (
        f"{'surface':<9} {'fills':>6} {'open':>6} {'close':>6} {'notional':>13} "
        f"{'realized':>11} {'fees':>9} {'net':>11} {'eff bps':>8}"
    )
    lines.append(hdr)
    lines.append("-" * len(hdr))

    tot_fills = tot_notional = tot_realized = tot_fees = 0.0
    tot_open = tot_close = 0
    any_incomplete = False

    for key in SURFACE_ORDER:
        s = stats[key]
        if not s.fills:
            continue
        bps = s.effective_bps
        flag = "" if s.fees_complete else " *"
        if not s.fees_complete:
            any_incomplete = True
        lines.append(
            f"{s.surface:<9} {s.fills:>6} {s.opening_fills:>6} {s.closing_fills:>6} "
            f"{s.notional_usd:>13,.2f} {s.realized_usd:>+11.2f} {s.fees_usd:>9.4f} "
            f"{s.net_usd:>+11.2f} {(f'{bps:.2f}' if bps is not None else '-'):>8}{flag}"
        )
        tot_fills += s.fills
        tot_open += s.opening_fills
        tot_close += s.closing_fills
        tot_notional += s.notional_usd
        tot_realized += s.realized_usd
        tot_fees += s.fees_usd

    lines.append("-" * len(hdr))
    tot_bps = (tot_fees / tot_notional * 10_000.0) if tot_notional > 0 else None
    lines.append(
        f"{'TOTAL':<9} {int(tot_fills):>6} {tot_open:>6} {tot_close:>6} "
        f"{tot_notional:>13,.2f} {tot_realized:>+11.2f} {tot_fees:>9.4f} "
        f"{tot_realized - tot_fees:>+11.2f} "
        f"{(f'{tot_bps:.2f}' if tot_bps is not None else '-'):>8}"
    )

    # Per-dex split: "hip3" pools clearinghouses that settle separately (INV 2),
    # so the aggregate row can hide one dex funding another's losses.
    hip3 = stats[SURFACE_HIP3]
    if hip3.detail_notional:
        lines.append("")
        lines.append("  hip3 notional by dex: " + ", ".join(
            f"{d}=${v:,.2f}" for d, v in sorted(
                hip3.detail_notional.items(), key=lambda kv: -kv[1])
        ))

    if any_incomplete:
        lines.append("")
        lines.append("  * fees INCOMPLETE on this surface — some fills paid a non-USDC fee:")
        for key in SURFACE_ORDER:
            s = stats[key]
            if s.fees_complete:
                continue
            toks = ", ".join(f"{v:g} {k}" for k, v in sorted(s.non_usdc_fee_tokens.items()))
            lines.append(
                f"      {s.surface}: {s.non_usdc_fee_fills} fill(s) paying {toks}"
            )
        lines.append("    Not converted to USD — we have no price for these tokens here.")
        lines.append("    `net` on those rows is therefore an UPPER bound.")

    lines.append("")
    lines.append("  Is the sample big enough to conclude anything?")
    for key in SURFACE_ORDER:
        s = stats[key]
        if not s.fills:
            continue
        ok, why = sample_verdict(s)
        lines.append(f"    {s.surface:<9} {'YES' if ok else 'NO ':<4} {why}")
    return "\n".join(lines)


def format_caveats(post_fix_ms: int) -> str:
    lines = [
        "=" * 100,
        "HOW TO READ THIS",
        "=" * 100,
        "  - Every figure is REALIZED (INV 10): booked `closedPnl` and booked `fee`.",
        "    Open positions contribute notional and fees but no PnL. Nothing here is",
        "    marked-to-market, so nothing here is an opinion.",
        "  - `net` = realized - USDC fees. It is NOT account PnL: funding payments and",
        "    outcome settlement do not appear in the fills feed at all.",
        "  - A young window under-reports: entry fees book immediately, PnL books on the",
        "    close. Check the open/close columns before reading a negative net as a loss.",
        f"  - The post-fix window starts {iso(post_fix_ms)} UTC — the reconcile HIP-3 fix.",
        "    Before it, xyz sizing was broken and positions were zeroed each cycle, so",
        "    pooled xyz history measures the bugs and not the surface.",
        "  - `hip3` pools separate clearinghouses (INV 2). Use the per-dex notional line;",
        "    do not read one hip3 net as one book.",
        "  - Effective bps is FEES over notional — our cost of trading. It is not edge.",
    ]
    return "\n".join(lines)


def build_report(
    fills: list[dict[str, Any]], history_since_ms: int, post_fix_ms: int
) -> tuple[str, dict[str, Any]]:
    """Render both windows and return (text, json-able results)."""
    hist = aggregate(fills, history_since_ms)
    post = aggregate(fills, post_fix_ms)

    text = "\n".join([
        format_window("FULL HISTORY", history_since_ms, hist),
        "",
        format_window("POST-FIX WINDOW", post_fix_ms, post),
        "",
        format_caveats(post_fix_ms),
    ])

    def dump(stats: dict[str, SurfaceStats]) -> dict[str, Any]:
        out = {}
        for k, s in stats.items():
            if not s.fills:
                continue
            d = {kk: vv for kk, vv in asdict(s).items() if not kk.startswith("_")}
            ok, why = sample_verdict(s)
            d.update(
                net_usd=s.net_usd,
                effective_bps=s.effective_bps,
                fees_complete=s.fees_complete,
                sample_sufficient=ok,
                sample_note=why,
            )
            out[k] = d
        return out

    results = {
        "generated_at": iso(int(time.time() * 1000)),
        "history_since": iso(history_since_ms),
        "post_fix_since": iso(post_fix_ms),
        "total_fills_fetched": len(fills),
        "full_history": dump(hist),
        "post_fix": dump(post),
    }
    return text, results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Realized PnL by surface (read-only)")
    ap.add_argument(
        "--since", default="0",
        help="window start: ISO-8601 (2026-08-15T13:47:00Z), epoch s, or epoch ms. "
             "Default 0 = all history.",
    )
    ap.add_argument(
        "--post-fix-since", default=POST_FIX_ISO,
        help=f"start of the clean window (default {POST_FIX_ISO}, the reconcile fix)",
    )
    ap.add_argument("--address", default="", help="override HL_ACCOUNT_ADDRESS")
    ap.add_argument("--json", default="", help="also write the full result set here")
    args = ap.parse_args(argv)

    address = args.address or os.environ.get("HL_ACCOUNT_ADDRESS", "")
    if not address:
        print("no account address: pass --address or set HL_ACCOUNT_ADDRESS", file=sys.stderr)
        return 2

    try:
        history_since_ms = parse_since(args.since)
        post_fix_ms = parse_since(args.post_fix_since)
    except ValueError as e:
        print(f"bad timestamp: {e}", file=sys.stderr)
        return 2

    # Fetch ONCE from the earlier of the two starts and window in memory: two
    # fetches would double the /info calls for no new data, and INV 7 records
    # HL 429-ing us over back-to-back calls.
    fetch_from = min(history_since_ms, post_fix_ms)
    info = Info("https://api.hyperliquid.xyz", skip_ws=True)
    fills = fetch_fills(info, address, fetch_from)
    if fills is None:
        # INV 4: unreadable is UNKNOWN, not zero. Refuse to print a report
        # rather than render a partial book as a flat one.
        print("ABORT: could not read the full fill history — refusing to report on "
              "partial data.", file=sys.stderr)
        return 1

    text, results = build_report(fills, history_since_ms, post_fix_ms)
    print(text)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=1, default=str)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
