"""Shadow harness for OutcomeMaker.

Runs the maker's real quoting logic against a live trades+book stream and
computes what would have happened, WITHOUT submitting orders. Purely
deterministic — trade and mid events are injected, so the simulator is
testable and reproducible.

Naive market-maker backtests self-flatter in three ways; this module refuses
each one explicitly:

  1. Fill assumption. A trade AT our quote price is not enough — we require
     a trade *crossing* our quote AND cumulative same-side aggressor volume
     to exhaust the queue ahead of us. Queue-ahead defaults to the full
     displayed depth at the quote level at post time (last in queue). That
     assumption is stated in the report; it is the single biggest source of
     self-flattery.
  2. Adverse selection. We record mid-price at t+1s, +10s, +60s from every
     shadowed fill, signed so positive = market moved our way. Persistently
     negative mark-outs mean we are being picked off; that is a NO-GO
     however good the gross-spread capture looks.
  3. Fees. Real round-trip fees, measured 2026-08-17 (see BACKLOG P0):
     HIP-3 0.86 bps, base 4.32 bps. No rebate — tier 0 has none.

The report is REALIZED only (INV 10): mean net edge per fill with standard
error and a plain YES/NO on whether the sample supports a conclusion
(n >= 30 AND |mean|/SE > 2, matching scripts/realized_pnl.py).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Measured 2026-08-17. Real fees for tier 0. No rebate.
HIP3_ROUND_TRIP_BPS = 0.86
BASE_ROUND_TRIP_BPS = 4.32

MARKOUT_HORIZONS_S: tuple[float, ...] = (1.0, 10.0, 60.0)
MARKOUT_REPORTING_HORIZON_S = 10.0

# Significance: n >= 30 AND |mean|/SE > 2  (~95% CI excludes zero).
MIN_SAMPLE_FOR_CONCLUSION = 30
SIGNIFICANCE_Z = 2.0


@dataclass
class ShadowQuote:
    ts: float
    side: str  # "B" (bid) or "A" (ask)
    px: float
    size: float
    queue_ahead: float  # size resting at our level ahead of us at post time
    filled_size: float = 0.0


@dataclass
class ShadowFill:
    quote_ts: float
    fill_ts: float
    side: str
    px: float
    size: float
    mid_at_fill: float
    markouts: dict[float, float] = field(default_factory=dict)


class ShadowSimulator:
    """Pure-logic maker shadow. Inject `on_trade` and `on_mid` events."""

    def __init__(self, coin: str, is_hip3: bool):
        self.coin = coin
        self.is_hip3 = is_hip3
        self._active: dict[str, ShadowQuote] = {}
        self._mid: float = 0.0
        self._mid_ts: float = 0.0
        self.fills: list[ShadowFill] = []
        self._pending_markouts: list[ShadowFill] = []

        self.inventory: float = 0.0
        self._max_inventory_abs: float = 0.0
        self._inv_time_accum: float = 0.0
        self._first_ts: float | None = None
        self._last_ts: float | None = None
        self._cap_size: float = 0.0
        self._cap_hits: int = 0

    def set_inventory_cap(self, cap_size: float) -> None:
        self._cap_size = cap_size

    def fee_bps(self) -> float:
        return HIP3_ROUND_TRIP_BPS if self.is_hip3 else BASE_ROUND_TRIP_BPS

    # ---------- inputs ----------

    def record_quote(
        self, ts: float, side: str, px: float, size: float, queue_ahead: float
    ) -> None:
        """Record a resting quote intent (overwrites any prior on that side).

        `queue_ahead` is the displayed depth at the price level at post time;
        we are last in that queue by convention (pessimistic).
        """
        if side not in ("B", "A"):
            raise ValueError(f"side must be 'B' or 'A', got {side!r}")
        if px <= 0 or size <= 0:
            raise ValueError("px and size must be positive")
        if queue_ahead < 0:
            raise ValueError("queue_ahead must be non-negative")
        self._touch_ts(ts)
        self._active[side] = ShadowQuote(ts, side, px, size, queue_ahead)

    def cancel_side(self, ts: float, side: str) -> None:
        self._touch_ts(ts)
        self._active.pop(side, None)

    def on_mid(self, ts: float, mid: float) -> None:
        self._touch_ts(ts)
        self._mid_ts = ts
        self._mid = mid
        self._settle_markouts(ts, mid)

    def on_trade(self, ts: float, aggressor_side: str, px: float, size: float) -> None:
        """Public trade event. `aggressor_side` is "B" (buy, lifts asks) or
        "A" (sell, hits bids)."""
        if aggressor_side not in ("B", "A"):
            raise ValueError(f"aggressor_side must be 'B' or 'A', got {aggressor_side!r}")
        if px <= 0 or size <= 0:
            return
        self._touch_ts(ts)
        # Aggressor B (buy) can only reach our ASK. Aggressor A (sell) can
        # only reach our BID. We fill the OPPOSITE side of the aggressor.
        our_side = "A" if aggressor_side == "B" else "B"
        q = self._active.get(our_side)
        if q is None:
            return
        # crossing requirement — the trade must reach our quote
        if our_side == "A" and px < q.px:
            return
        if our_side == "B" and px > q.px:
            return
        remaining = size
        if q.queue_ahead > 0:
            burn = min(q.queue_ahead, remaining)
            q.queue_ahead -= burn
            remaining -= burn
        if remaining <= 0:
            return
        fill_size = min(remaining, q.size - q.filled_size)
        if fill_size <= 1e-12:
            return
        q.filled_size += fill_size
        self._book_fill(q, ts, fill_size)
        if q.filled_size >= q.size - 1e-12:
            self._active.pop(our_side, None)

    # ---------- internals ----------

    def _book_fill(self, q: ShadowQuote, ts: float, size: float) -> None:
        mid = self._mid if self._mid > 0 else q.px
        fill = ShadowFill(
            quote_ts=q.ts,
            fill_ts=ts,
            side=q.side,
            px=q.px,
            size=size,
            mid_at_fill=mid,
        )
        self.fills.append(fill)
        self._pending_markouts.append(fill)
        # B = we bought (long); A = we sold (short)
        delta = size if q.side == "B" else -size
        self._update_inventory(ts, delta)

    def _update_inventory(self, ts: float, delta: float) -> None:
        # accumulate |inv| * dt BEFORE changing inventory
        if self._last_ts is not None and ts > self._last_ts:
            self._inv_time_accum += abs(self.inventory) * (ts - self._last_ts)
        self.inventory += delta
        self._last_ts = ts
        if abs(self.inventory) > self._max_inventory_abs:
            self._max_inventory_abs = abs(self.inventory)
        if self._cap_size > 0 and abs(self.inventory) >= self._cap_size:
            self._cap_hits += 1

    def _settle_markouts(self, ts: float, mid: float) -> None:
        still_pending: list[ShadowFill] = []
        for f in self._pending_markouts:
            elapsed = ts - f.fill_ts
            for h in MARKOUT_HORIZONS_S:
                if h in f.markouts:
                    continue
                if elapsed >= h:
                    move = mid - f.mid_at_fill
                    # positive = market moved OUR way
                    f.markouts[h] = move if f.side == "B" else -move
            if len(f.markouts) < len(MARKOUT_HORIZONS_S):
                still_pending.append(f)
        self._pending_markouts = still_pending

    def _touch_ts(self, ts: float) -> None:
        if self._first_ts is None:
            self._first_ts = ts
        # roll inventory time-weight forward for gap between events
        if self._last_ts is None:
            self._last_ts = ts
        elif ts > self._last_ts:
            self._inv_time_accum += abs(self.inventory) * (ts - self._last_ts)
            self._last_ts = ts

    # ---------- reporting ----------

    def net_edge_per_fill_bps(self, f: ShadowFill) -> float | None:
        """Realized net edge in bps. None if the reporting horizon hasn't
        settled — we only report REALIZED terms (INV 10)."""
        if MARKOUT_REPORTING_HORIZON_S not in f.markouts:
            return None
        if f.mid_at_fill <= 0:
            return None
        if f.side == "B":
            spread_captured = f.mid_at_fill - f.px
        else:
            spread_captured = f.px - f.mid_at_fill
        spread_bps = 1e4 * spread_captured / f.mid_at_fill
        markout_bps = 1e4 * f.markouts[MARKOUT_REPORTING_HORIZON_S] / f.mid_at_fill
        return spread_bps + markout_bps - self.fee_bps()

    def report(self) -> dict:
        edges: list[float] = []
        for f in self.fills:
            e = self.net_edge_per_fill_bps(f)
            if e is not None:
                edges.append(e)
        n = len(edges)
        mean = sum(edges) / n if n else 0.0
        if n > 1:
            var = sum((e - mean) ** 2 for e in edges) / (n - 1)
            se = math.sqrt(var / n)
        else:
            se = 0.0

        markout_summary: dict[str, dict[str, float]] = {}
        for h in MARKOUT_HORIZONS_S:
            samples = [f.markouts[h] for f in self.fills if h in f.markouts]
            if samples and any(f.mid_at_fill > 0 for f in self.fills):
                # convert to bps using mid_at_fill for each fill
                bps = [
                    1e4 * f.markouts[h] / f.mid_at_fill
                    for f in self.fills
                    if h in f.markouts and f.mid_at_fill > 0
                ]
                m = sum(bps) / len(bps)
            else:
                m = 0.0
            markout_summary[f"{h:g}s"] = {
                "n": float(len(samples)),
                "mean_bps": m,
            }

        if n < MIN_SAMPLE_FOR_CONCLUSION:
            conclusion = f"NO — n={n} below threshold {MIN_SAMPLE_FOR_CONCLUSION}"
        elif se == 0:
            conclusion = "YES" if mean > 0 else "NO"
        elif abs(mean) / se > SIGNIFICANCE_Z:
            conclusion = "YES" if mean > 0 else "NO"
        else:
            conclusion = f"NO — mean {mean:.2f}bps within {SIGNIFICANCE_Z} SE of zero"

        elapsed = 0.0
        if self._first_ts is not None and self._last_ts is not None:
            elapsed = self._last_ts - self._first_ts
        avg_abs_inv = self._inv_time_accum / elapsed if elapsed > 0 else 0.0

        return {
            "coin": self.coin,
            "surface": "hip3" if self.is_hip3 else "base",
            "n_shadow_fills": len(self.fills),
            "n_realized": n,
            "mean_net_edge_bps": mean,
            "stderr_bps": se,
            "significance_z": (abs(mean) / se) if se > 0 else (float("inf") if n else 0.0),
            "conclusion_yes_no": conclusion,
            "fee_round_trip_bps": self.fee_bps(),
            "reporting_horizon_s": MARKOUT_REPORTING_HORIZON_S,
            "queue_assumption": (
                "last-in-queue: queue_ahead = full displayed depth at quote-level "
                "at post time; a fill requires the trade to cross AND cumulative "
                "same-side aggressor volume to exhaust that queue"
            ),
            "markouts_bps": markout_summary,
            "max_abs_inventory": self._max_inventory_abs,
            "time_weighted_avg_abs_inventory": avg_abs_inv,
            "inventory_cap": self._cap_size,
            "inventory_cap_hits": self._cap_hits,
        }
