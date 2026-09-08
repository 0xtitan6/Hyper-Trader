"""Detect leader-position drift and close stale mirrors.

The bot mirrors leader fills via WS. If a leader closes their position and the
WS feed silently drops the close fill (observed 2026-05-21: rank 13 closed
their ZEC short and our follower never received the buy-back fills, leaving us
short for days while the market reversed against us), we eat the retrace.

This module is the defense-in-depth: every `interval_s` seconds, fetch each
followed leader's on-chain `assetPositions` and cross-reference with the
`originator_address` we stored when the position opened (PR #25). If the
originator has flat'd or flipped while we still hold the mirror, we either
alert (default) or auto-close via reduce_only IOC (opt-in).

This does NOT replace FillFollower. It's a slower safety net. WS still does
the heavy lifting on entries and intra-position adjustments.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.error import URLError

from .alerts import Alerter, NullAlerter
from .journal import Journal
from .market_meta import MarketMeta
from .protocols import ExchangeProto, InfoProto
from .state import State

log = logging.getLogger(__name__)

# Detection statuses returned by reconcile().
STATUS_OK = "ok"               # leader still holds same-direction position
STATUS_CLOSED = "closed"       # originator flat — they exited
STATUS_FLIPPED = "flipped"     # originator reversed direction
STATUS_ORPHAN = "orphan"       # no recorded originator AND no follower holds same direction
STATUS_UNKNOWN = "unknown"     # fetch failed; preserve last state, don't act
# Originator is no longer in the followed set — the leader was dropped from
# config/discovery while we still hold what they opened. Detect-only: this
# status is produced by `check_dropped_leaders`, never by `reconcile`, and it
# is deliberately unreachable from the auto-close path (see the docstring).
STATUS_DROPPED = "dropped_leader_orphan"


class LeaderReconciler:
    """Periodic cross-check between our open positions and the originating
    leader's on-chain state.

    Requires `interval_s` between reconciles (default 5 min). Uses a debounce
    of `debounce_cycles` consecutive stale detections before acting — defends
    against transient one-cycle false positives (leader briefly reduced size,
    leader's fill not yet visible to user_state, etc).

    `auto_close=False` ships alert-only. Auto-close requires explicit opt-in
    via config plus an Exchange + MarketMeta to submit reduce_only orders.
    """

    def __init__(
        self,
        info: InfoProto,
        state: State,
        journal: Journal,
        alerter: Alerter | None = None,
        exchange: ExchangeProto | None = None,
        market_meta: MarketMeta | None = None,
        auto_close: bool = False,
        debounce_cycles: int = 2,
        slippage_bps: float = 50.0,
        manual_holdings: list[str] | None = None,
        dropped_confirm_passes: int = 2,
    ):
        self.info = info
        self.state = state
        self.journal = journal
        self.alerter: Alerter = alerter or NullAlerter()
        self.exchange = exchange
        self.market_meta = market_meta
        self.auto_close = auto_close
        self.debounce_cycles = debounce_cycles
        self.slippage_bps = slippage_bps
        # Operator-managed positions to skip entirely. Stored lowercase for
        # case-insensitive match.
        self.manual_holdings: set[str] = {c.lower() for c in (manual_holdings or [])}
        # coin -> consecutive stale cycles
        self._stale_counts: dict[str, int] = {}
        # Coins already alerted as dropped-leader orphans. A dropped leader is a
        # STANDING condition, not an event: without this the check would re-fire
        # on every leader refresh (every 10 min) forever.
        self._dropped_alerted: set[str] = set()
        # Confirm a drop across N consecutive checks before alerting. Only
        # `discovery.top_n` (4) of our ~9 slots are auto-discovered, and those
        # rotate on rank: a leader can fall out of the top-4 on one refresh and
        # return on the next. Alerting on a single observation would page the
        # operator on ordinary leaderboard churn. Counter resets the moment the
        # originator is followed again, so a flapping leader never accumulates.
        self.dropped_confirm_passes = max(1, dropped_confirm_passes)
        self._dropped_pending: dict[str, int] = {}

    def reconcile(self, follower_addresses: list[str]) -> dict[str, str]:
        """One reconcile pass. Returns {coin: status} for every open position.

        Caller is responsible for cadence — invoke from the main loop every
        `interval_s` seconds.
        """
        leader_positions = self._fetch_all_leader_positions(follower_addresses)
        if leader_positions is None:
            log.warning("leader_reconcile: all leader fetches failed; skipping cycle")
            return {}

        status: dict[str, str] = {}
        for coin, (our_sz, _our_avg) in self.state.get_positions().items():
            if our_sz == 0:
                continue
            if coin.lower() in self.manual_holdings:
                continue
            originator = self.state.get_position_originator(coin)
            status[coin] = self._classify(coin, our_sz, originator, leader_positions)

        for coin, st in status.items():
            if st == STATUS_OK or st == STATUS_UNKNOWN:
                self._stale_counts.pop(coin, None)
            else:
                self._on_stale(coin, st)

        return status

    def check_dropped_leaders(
        self, followed_addresses: list[str] | None
    ) -> dict[str, str]:
        """Flag open positions whose originator is no longer followed.

        `reconcile()` above only ever notices a leader *exiting their own
        position*. It is structurally blind to a leader being REMOVED from
        `config.yaml` / dropped by discovery, for two reasons:

          1. it is fed `FillFollower.addresses`, which only ever GROWS —
             `follow()` has no unsubscribe, so a dropped leader stays in that
             list for the lifetime of the process; and
          2. a dropped leader who still holds their position classifies as
             `ok`, forever.

        So the mirror is simply abandoned. Four of them (JUP, JTO, AR, XMR,
        from two leaders dropped around July) accumulated unnoticed until
        2026-08-15, when they held $67.64 initial margin / $344 gross — 100% of
        base margin — and every signal from our CURRENT leaders was being
        rejected for want of collateral. They were closed by hand.

        This is DETECT-ONLY and deliberately separate from `reconcile()`:

        - It never calls `_submit_close`. Closing is a money action and stays
          with the operator; `auto_close` does not reach this path at all.
        - It never touches `_stale_counts`. Wiring drop-detection into the
          reconcile cycle would have let a leader refresh and the 5-minute
          timer fire two "cycles" seconds apart, defeating the debounce that
          protects the auto-close path from transient false positives.
        - It needs no network read (state only), so it is safe to call on
          startup and on every leader refresh.

        Pass the CURRENT followed set (discovery + `always_follow`), NOT
        `follower.addresses` — see (1) above.

        Returns {coin: status} for every open, non-manual position.
        """
        # INV 4: UNKNOWN is never EMPTY. An empty followed set means discovery
        # failed or returned nothing — it does NOT mean every leader was
        # dropped. Acting on that reading would flag the entire book at once,
        # which is precisely the "incomplete leader book → ORPHAN" mistake that
        # tried to auto-close six live positions on 2026-08-15.
        followed = {a.lower() for a in (followed_addresses or []) if a}

        status: dict[str, str] = {}
        # coin -> (originator, sz, avg_px), captured for the alert text so the
        # report describes the same snapshot the classification was made on.
        seen: dict[str, tuple[str | None, float, float]] = {}
        for coin, (our_sz, avg_px) in self.state.get_positions().items():
            if our_sz == 0:
                continue
            # AC-3: operator-managed positions are exempt, same as reconcile().
            if coin.lower() in self.manual_holdings:
                continue
            if not followed:
                status[coin] = STATUS_UNKNOWN
                continue
            originator = self.state.get_position_originator(coin)
            seen[coin] = (originator, our_sz, avg_px)
            if originator is None:
                # Unreadable/unrecorded originator (pre-PR-#25 rows, or a row
                # whose originator was cleared). We cannot tell whose position
                # this is, so we cannot call it dropped. UNKNOWN, not DROPPED.
                status[coin] = STATUS_UNKNOWN
                continue
            if originator.lower() in followed:
                status[coin] = STATUS_OK
                continue
            status[coin] = STATUS_DROPPED

        if not followed:
            log.warning(
                "leader_reconcile: empty followed set (%d open positions) — "
                "UNKNOWN this pass, nothing flagged as dropped",
                len(status),
            )
            return status

        # Throttle bookkeeping. Forget coins that are no longer open (or became
        # manual holdings) so a genuinely new orphan on the same coin re-alerts.
        live = set(status)
        self._dropped_alerted &= live
        self._dropped_pending = {c: n for c, n in self._dropped_pending.items() if c in live}
        for coin, st in status.items():
            if st == STATUS_OK:
                # Leader is followed again (re-added to config, or back in the
                # top-N) — re-arm and forget any part-accumulated confirmation.
                self._dropped_alerted.discard(coin)
                self._dropped_pending.pop(coin, None)
            elif st == STATUS_DROPPED:
                # Clamped: once confirmed it stays confirmed, and the counter
                # must not grow without bound across a long-lived process.
                n = min(self._dropped_pending.get(coin, 0) + 1, self.dropped_confirm_passes)
                self._dropped_pending[coin] = n
                if n < self.dropped_confirm_passes:
                    log.info(
                        "leader_reconcile: %s looks orphaned by a dropped leader "
                        "[pass %d/%d]", coin, n, self.dropped_confirm_passes,
                    )
                    continue
                originator, sz, avg_px = seen[coin]
                self._report_dropped(coin, originator, sz, avg_px)
        return status

    def _report_dropped(
        self, coin: str, originator: str | None, sz: float, avg_px: float
    ) -> None:
        """Journal + alert ONCE per coin. Never closes."""
        if coin in self._dropped_alerted:
            log.info(
                "leader_reconcile: %s still orphaned by dropped leader %s "
                "(already alerted)",
                coin,
                (originator or "?")[:10],
            )
            return
        self._dropped_alerted.add(coin)
        log.warning(
            "leader_reconcile: %s orphaned — originator %s is no longer followed "
            "(our_sz=%+.4f avg=$%.4f); NOT auto-closing",
            coin,
            (originator or "?")[:10],
            sz,
            avg_px,
        )
        self.journal.write(
            STATUS_DROPPED,
            coin=coin,
            originator=originator,
            our_sz=sz,
            our_avg_px=avg_px,
        )
        self.alerter.alert(
            "error",
            f"Dropped-leader orphan: {coin} our_sz={sz:+.4f} avg=${avg_px:.4f} — "
            f"originator {(originator or '?')[:10]} is no longer in the followed "
            f"set. NOT auto-closed; operator must decide.",
        )

    def _classify(
        self,
        coin: str,
        our_sz: float,
        originator: str | None,
        leader_positions: dict[str, dict[str, float]],
    ) -> str:
        """Determine status of one position relative to its originator."""
        if originator is None:
            # Pre-PR-#25 position. Fallback: any followed leader still holds
            # a same-direction position? If not, treat as orphan.
            same_dir_anyone = any(
                self._same_direction(our_sz, lp.get(coin, 0.0))
                for lp in leader_positions.values()
            )
            return STATUS_OK if same_dir_anyone else STATUS_ORPHAN

        leader_book = leader_positions.get(originator)
        if leader_book is None:
            # We failed to fetch this specific leader. Don't act on partial
            # data — wait for the next cycle.
            return STATUS_UNKNOWN

        leader_sz = leader_book.get(coin, 0.0)
        if leader_sz == 0:
            return STATUS_CLOSED
        if self._same_direction(our_sz, leader_sz):
            return STATUS_OK
        return STATUS_FLIPPED

    @staticmethod
    def _same_direction(a: float, b: float) -> bool:
        if a == 0 or b == 0:
            return False
        return (a > 0) == (b > 0)

    def _fetch_all_leader_positions(
        self, addresses: list[str]
    ) -> dict[str, dict[str, float]] | None:
        """Fetch each leader's perp positions. Returns address → {coin: sz}.

        Missing entries mean fetch failed for that address — caller treats as
        UNKNOWN. If ALL fetches fail, returns None (signaling the caller to
        skip the cycle entirely rather than misclassify everything as orphan).
        """
        out: dict[str, dict[str, float]] = {}
        any_success = False
        for raw in addresses:
            addr = raw.lower()
            try:
                us = self.info.user_state(addr) or {}
            except (URLError, OSError, ValueError, KeyError):
                log.warning("leader_reconcile: user_state fetch failed for %s", addr[:10])
                continue
            except Exception:
                log.exception("leader_reconcile: unexpected fetch error for %s", addr[:10])
                continue
            book: dict[str, float] = {}
            self._ingest_positions(us, book)
            # HIP-3 builder dexes are separate clearinghouses — `user_state`
            # never returns them. Without this the leader's entire xyz book is
            # invisible, EVERY xyz mirror we hold classifies as `orphan`, and
            # auto-close fires on all of them. Observed 2026-08-15: six
            # simultaneous "Leader exit detected ... orphan" on live positions
            # the leader still held. The only reason our xyz book survived is
            # that `_fetch_mid` has no xyz mid and the close failed — an
            # accident, not a safeguard. Fixing the mid without this would have
            # force-closed the whole surface.
            dex_ok = self._ingest_hip3_positions(addr, book)
            out[addr] = book
            # A dex we could not read means this leader's book is INCOMPLETE.
            # Recording it as complete would mark live mirrors as orphans, so
            # drop the leader to UNKNOWN for this cycle instead.
            if not dex_ok:
                log.warning(
                    "leader_reconcile: incomplete HIP-3 book for %s; "
                    "treating as UNKNOWN this cycle", addr[:10],
                )
                out.pop(addr, None)
                continue
            any_success = True
        return out if any_success else None

    @staticmethod
    def _ingest_positions(state: dict, book: dict[str, float]) -> None:
        for ap in (state or {}).get("assetPositions", []) or []:
            pos = ap.get("position") if isinstance(ap, dict) else None
            if not isinstance(pos, dict):
                continue
            coin = pos.get("coin")
            if not coin:
                continue
            try:
                sz = float(pos.get("szi", 0))
            except (TypeError, ValueError):
                continue
            if sz != 0:
                book[coin] = sz

    def _ingest_hip3_positions(self, addr: str, book: dict[str, float]) -> bool:
        """Add the leader's builder-dex positions. False if any dex was unreadable."""
        try:
            dexes = self.info.post("/info", {"type": "perpDexs"})
        except Exception:
            log.warning("leader_reconcile: perpDexs fetch failed for %s", addr[:10])
            return False
        if dexes is None:
            return False
        ok = True
        for d in dexes:
            if not isinstance(d, dict) or not d.get("name"):
                continue
            name = d["name"]
            try:
                st = self.info.post(
                    "/info",
                    {"type": "clearinghouseState", "user": addr, "dex": name},
                )
            except Exception:
                log.warning("leader_reconcile: dex=%s state failed for %s", name, addr[:10])
                ok = False
                continue
            self._ingest_positions(st or {}, book)
        return ok

    def _on_stale(self, coin: str, reason: str) -> None:
        count = self._stale_counts.get(coin, 0) + 1
        self._stale_counts[coin] = count
        log.info(
            "leader_reconcile: %s is %s [cycle %d/%d]",
            coin,
            reason,
            count,
            self.debounce_cycles,
        )
        if count < self.debounce_cycles:
            return
        # Debounce satisfied — act
        self._stale_counts[coin] = 0  # reset so we don't loop on the same coin
        self._act_on_stale(coin, reason)

    def _act_on_stale(self, coin: str, reason: str) -> None:
        sz, avg_px = self.state.get_position(coin)
        if sz == 0:
            return  # already gone (closed by another path between cycles)

        self.journal.write(
            "leader_exit_detected",
            coin=coin,
            reason=reason,
            our_sz=sz,
            our_avg_px=avg_px,
        )
        self.alerter.alert(
            "error",
            f"Leader exit detected on {coin}: {reason}. our_sz={sz:+.4f} avg=${avg_px:.4f}",
        )

        if not self.auto_close:
            return
        if self.exchange is None or self.market_meta is None:
            log.error(
                "leader_reconcile: auto_close=True but exchange/market_meta not configured"
            )
            return

        self._submit_close(coin, sz, avg_px, reason)

    def _submit_close(self, coin: str, sz: float, avg_px: float, reason: str) -> None:
        """Submit reduce_only IOC to flatten `coin`. is_buy is the opposite of
        our current direction. Limit price = mid ± slippage_bps, rounded."""
        mid = self._fetch_mid(coin)
        if mid is None or mid <= 0:
            self.alerter.alert(
                "error",
                f"leader_reconcile: cannot auto-close {coin} — mid fetch failed/invalid",
            )
            return

        assert self.exchange is not None  # narrowed by caller's auto_close check
        assert self.market_meta is not None
        is_buy = sz < 0  # close a short by buying
        bps = self.slippage_bps / 10_000
        slipped = mid * (1.0 + bps) if is_buy else mid * (1.0 - bps)
        limit_px = self.market_meta.round_price(slipped, coin)

        log.warning(
            "leader_reconcile: auto-closing %s reason=%s our_sz=%+.4f mid=$%.4f limit=$%.4f",
            coin,
            reason,
            sz,
            mid,
            limit_px,
        )
        try:
            result = self.exchange.order(
                coin,
                is_buy,
                abs(sz),
                limit_px,
                order_type={"limit": {"tif": "Ioc"}},
                reduce_only=True,
            )
        except Exception as e:
            self.alerter.alert(
                "error",
                f"leader_reconcile: auto-close order failed for {coin}: {type(e).__name__}: {e}",
            )
            self.journal.write(
                "leader_exit_close_failed",
                coin=coin,
                reason=reason,
                error=str(e),
            )
            return

        self.journal.write(
            "leader_exit_close",
            coin=coin,
            reason=reason,
            our_sz=sz,
            our_avg_px=avg_px,
            limit_px=limit_px,
            result=result,
        )
        self.alerter.alert(
            "error",
            f"leader_reconcile: auto-closed {coin} via reduce_only IOC "
            f"({'BUY' if is_buy else 'SELL'} {abs(sz)} @ {limit_px})",
        )

    def _fetch_mid(self, coin: str) -> float | None:
        """Fetch mid price for one coin via allMids endpoint."""
        try:
            mids = self.info.all_mids()
        except Exception:
            log.exception("leader_reconcile: allMids fetch failed")
            return None
        try:
            return float(mids[coin])
        except (KeyError, TypeError, ValueError):
            log.warning("leader_reconcile: no mid for %s", coin)
            return None

    def reset_debounce(self, coin: str | None = None) -> None:
        """Forget pending stale counts. Pass coin=None to reset all.

        Useful in tests and after an externally-triggered close.
        """
        if coin is None:
            self._stale_counts.clear()
        else:
            self._stale_counts.pop(coin, None)
