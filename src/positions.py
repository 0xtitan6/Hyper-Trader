import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from typing import Any

from .alerts import Alerter, NullAlerter
from .connection import ConnectionHealth
from .journal import Journal
from .market_meta import dex_of
from .protocols import InfoProto
from .state import State

log = logging.getLogger(__name__)


def today_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _free_usdc(spot_state: dict) -> float | None:
    """Unencumbered spot USDC = total - hold, or None if unreadable.

    Under unified margin this IS our collateral for new positions on every
    clearinghouse: HL places a `hold` on spot USDC per open position (verified
    2026-08-15 — xyz marginUsed 64.424287 == spot hold 64.424287 exactly).

    Returns None rather than 0.0 when the balance is missing or malformed, so
    the caller can fall back to the perp figure instead of reading "unknown"
    as "broke" and halting trading.
    """
    for b in (spot_state or {}).get("balances", []) or []:
        if isinstance(b, dict) and b.get("coin") == "USDC":
            try:
                return max(0.0, float(b.get("total", 0) or 0) - float(b.get("hold", 0) or 0))
            except (TypeError, ValueError):
                log.warning("reconcile: malformed USDC balance %s", b)
                return None
    return None


@dataclass(frozen=True)
class MarginSnapshot:
    """Point-in-time view of HL's own margin accounting for our account.

    Captured on every `reconcile_with_user_state` (startup + the 5-min loop in
    main) so the order hot path can check free-margin headroom WITHOUT a
    blocking HTTP call per leader fill. A single leader burst is 5+ child fills
    in a second and HL rate-limits /info and /exchange per account — adding a
    synchronous fetch there would trade margin rejects for 429s.

    `exposure_at_snapshot_usd` is our own cost-basis exposure at capture time.
    The mirror uses it to charge itself for positions opened SINCE the snapshot
    (up to 5 min of drift) instead of re-spending the same free collateral on
    every fill in a burst.
    """

    account_value_usd: float
    total_margin_used_usd: float
    free_collateral_usd: float
    exposure_at_snapshot_usd: float
    ts: float

    @property
    def age_s(self) -> float:
        return max(0.0, time.time() - self.ts)


class PositionTracker:
    """Subscribes to our own userFills, persists fills, maintains positions and
    realized PnL. Source of truth for the daily-loss kill switch and exposure cap.

    Exposure is computed at cost basis (|sz| * avg_px). For HIP-4 outcomes that's
    the actual max loss; for perps it's an approximation that ignores leverage.
    """

    def __init__(
        self,
        info: InfoProto,
        account_address: str,
        state: State,
        journal: Journal,
        health: ConnectionHealth | None = None,
        alerter: Alerter | None = None,
    ):
        self.info = info
        self.account_address = account_address.lower()
        self.state = state
        self.journal = journal
        self.health = health
        self.alerter: Alerter = alerter or NullAlerter()
        self._lock = RLock()
        self._subscribed = False
        # Last margin reading from HL, refreshed by reconcile_with_user_state.
        # None until the first successful reconcile — consumers must fail OPEN
        # on None (see mirror._margin_headroom_check).
        self._margin: MarginSnapshot | None = None

    def start(self) -> None:
        with self._lock:
            if self._subscribed:
                return
            log.info("Subscribing to own userFills for %s", self.account_address[:10])
            self.info.subscribe(
                {"type": "userFills", "user": self.account_address},
                self._handle,
            )
            self._subscribed = True

    def realized_pnl_today(self) -> float:
        """Net of fees: closedPnl - fee. This is what the daily-loss kill switch checks."""
        gross, fee = self.state.daily_pnl(today_utc())
        return gross - fee

    def realized_pnl_today_gross(self) -> float:
        """Gross PnL only, no fees deducted. Useful for journaling / debugging."""
        return self.state.daily_pnl(today_utc())[0]

    def total_exposure_usd(self) -> float:
        total = 0.0
        for _coin, (sz, avg_px) in self.state.get_positions().items():
            total += abs(sz) * avg_px
        return total

    def exposure_usd_for_dex(self, dex: str) -> float:
        """Gross notional held on ONE clearinghouse.

        Hyperliquid settles each HIP-3 builder dex against its own collateral,
        so summing them into a single number and gating on that charges an
        `xyz:` order for risk carried on the base account. Measured 2026-08-15
        while doing exactly that: base ran 2.4x maintenance coverage and xyz
        ran 14.6x, yet a single shared cap blocked 40 of 40 opens — 39 of them
        on xyz:SP500, which is 64% of our best leader's flow.

        `dex` is the prefix before ':' (`xyz`, `flx`, ...), or "" for the base
        perp dex, which is also where outcomes and spot live: they draw on the
        base account's collateral, so they belong in the base bucket.
        """
        total = 0.0
        for coin, (sz, avg_px) in self.state.get_positions().items():
            if dex_of(coin) == dex:
                total += abs(sz) * avg_px
        return total

    def margin_snapshot(self) -> MarginSnapshot | None:
        """Latest cached margin reading, or None if we've never reconciled."""
        with self._lock:
            return self._margin

    def _capture_margin_snapshot(self, us: dict, spot_free_usdc: float | None = None) -> None:
        """Record how much collateral is actually available to open new risk.

        UNIFIED MARGIN (corrected 2026-08-15). This account settles every
        clearinghouse — base perps AND each HIP-3 builder dex — against the one
        spot USDC balance, placing a `hold` on it per open position. Proof, to
        six decimals, at the moment of the fix:

            xyz dex marginUsed  64.424287
            spot USDC hold      64.424287
            spot USDC free      $151.78

        The base perp `withdrawable` is therefore NOT our free collateral. With
        no base positions open it reads $0.00 — not "no money", just "nothing
        held yet" — and gating on it blocked every base-perp open while $151.78
        sat available. That is a silent trade-suppression bug of exactly the
        kind this guard exists to prevent, so prefer the spot figure and keep
        `withdrawable` only as the fallback when spot is unreadable.
        """
        try:
            ms = us.get("marginSummary") or {}
            account_value = float(ms.get("accountValue", 0) or 0)
            margin_used = float(ms.get("totalMarginUsed", 0) or 0)
            raw_withdrawable = us.get("withdrawable")
            fallback = (
                float(raw_withdrawable)
                if raw_withdrawable is not None
                else account_value - margin_used
            )
            free = spot_free_usdc if spot_free_usdc is not None else fallback
        except (TypeError, ValueError):
            log.warning("reconcile: malformed marginSummary %s", us.get("marginSummary"))
            return
        with self._lock:
            self._margin = MarginSnapshot(
                account_value_usd=account_value,
                total_margin_used_usd=margin_used,
                free_collateral_usd=free,
                exposure_at_snapshot_usd=self.total_exposure_usd(),
                ts=time.time(),
            )

    def _hip3_dex_names(self) -> list[str] | None:
        """Active HIP-3 builder-dex names, or None if we couldn't enumerate.

        None is distinct from []: an empty list means "there are genuinely no
        builder dexes", while None means "we don't know", and the caller must
        not treat unknown as empty (that's what zeroed live positions).
        """
        try:
            dexes = self.info.post("/info", {"type": "perpDexs"})
        except Exception:
            log.exception("reconcile: perpDexs fetch failed; holding HIP-3 state")
            return None
        if dexes is None:
            log.warning("reconcile: perpDexs returned empty; holding HIP-3 state")
            return None
        return [d["name"] for d in dexes if isinstance(d, dict) and d.get("name")]

    def _merge_hip3_positions(self, upstream: dict[str, tuple[float, float]]) -> set[str]:
        """Merge each builder dex's positions into `upstream`.

        Returns the set of dex names we could NOT read, so the caller can hold
        (rather than zero) local positions belonging to them.
        """
        names = self._hip3_dex_names()
        if names is None:
            # Unknown which dexes exist → treat every dex we hold as unreachable.
            return {dex_of(c) for c in self.state.get_positions() if dex_of(c)}
        unreachable: set[str] = set()
        for dex in names:
            try:
                st = (
                    self.info.post(
                        "/info",
                        {
                            "type": "clearinghouseState",
                            "user": self.account_address,
                            "dex": dex,
                        },
                    )
                    or {}
                )
            except Exception:
                log.exception("reconcile: clearinghouseState failed for dex=%s; holding", dex)
                unreachable.add(dex)
                continue
            for ap in st.get("assetPositions", []) or []:
                pos = ap.get("position") if isinstance(ap, dict) else None
                if not isinstance(pos, dict):
                    continue
                coin = pos.get("coin")
                if not coin:
                    continue
                try:
                    szi = float(pos.get("szi", 0))
                    entry_px = float(pos.get("entryPx", 0) or 0)
                except (TypeError, ValueError):
                    log.warning("reconcile: malformed HIP-3 position %s", pos)
                    continue
                # HL already returns these dex-prefixed ("xyz:SP500"), which is
                # the same key leader fills carry. Prefix defensively if not.
                upstream[coin if ":" in coin else f"{dex}:{coin}"] = (szi, entry_px)
        return unreachable

    def reconcile_with_user_state(self) -> dict[str, tuple[float, float]]:
        """Overwrite local position state with HL's authoritative state.

        Queries BOTH:
          - `user_state` for perp/futures `assetPositions`
          - `spotClearinghouseState` for HIP-4 outcome positions (`+NN` coins
            with positive balance — these are NOT in `assetPositions`)

        Run at startup (before the WS snapshot, which can be truncated) and
        periodically (so HIP-4 settlement, manual trades, and any drift get
        picked up). Returns the post-reconcile map of {coin: (sz, avg_px)}.

        Coins that exist locally but not upstream are zeroed — that's how
        settled outcome positions get cleared.
        """
        upstream: dict[str, tuple[float, float]] = {}

        try:
            us = self.info.user_state(self.account_address) or {}
        except Exception:
            log.exception("reconcile: user_state fetch failed; keeping local state")
            return self.state.get_positions()

        for ap in us.get("assetPositions", []) or []:
            pos = ap.get("position") if isinstance(ap, dict) else None
            if not isinstance(pos, dict):
                continue
            coin = pos.get("coin")
            if not coin:
                continue
            try:
                szi = float(pos.get("szi", 0))
                entry_px = float(pos.get("entryPx", 0) or 0)
            except (TypeError, ValueError):
                log.warning("reconcile: malformed position %s", pos)
                continue
            upstream[coin] = (szi, entry_px)

        # HIP-4 outcomes live in spotClearinghouseState.balances as `+NN`,
        # NOT in assetPositions. Without this, our local outcome positions
        # would get zeroed every reconcile cycle (treated as "missing
        # upstream") even though we still own them.
        try:
            sc = (
                self.info.post(
                    "/info",
                    {"type": "spotClearinghouseState", "user": self.account_address},
                )
                or {}
            )
        except Exception:
            log.exception("reconcile: spotClearinghouseState fetch failed; perp-only")
            sc = {}
        for b in sc.get("balances", []) or []:
            if not isinstance(b, dict):
                continue
            coin = b.get("coin")
            if not coin or not coin.startswith("+"):
                continue  # only outcome legs (USDC/USDH/etc are not positions)
            try:
                total = float(b.get("total", 0) or 0)
                entry_ntl = float(b.get("entryNtl", 0) or 0)
            except (TypeError, ValueError):
                log.warning("reconcile: malformed spot balance %s", b)
                continue
            if total <= 0:
                continue
            avg_px = entry_ntl / total if total > 0 else 0.0
            # Translate `+NN` (spot ticker) to `#NN` (trade ticker) — they're
            # the same outcome leg but HL uses different prefixes per surface.
            trade_coin = "#" + coin[1:]
            upstream[trade_coin] = (total, avg_px)

        # HIP-3 builder dexes are SEPARATE clearinghouses. `user_state` above
        # only ever returns base-dex positions, so without this every `xyz:*`
        # position looked "missing upstream" and was zeroed on every cycle.
        # Found 2026-08-15: 27 `zeroing xyz:SP500` in one day, with three
        # compounding consequences —
        #   1. sizing: the bot believed it was flat and re-opened on the next
        #      leader signal, stacking SP500 to 7x the intended size;
        #   2. reduce_only: exits looked like opens against a flat book;
        #   3. the per-dex exposure cap read the same zeroed state, so it saw
        #      ~$0 of xyz risk against ~$339 real — the cap bounded nothing.
        # Same bug class as the outcome-leg special case above.
        unreachable_dexes = self._merge_hip3_positions(upstream)

        local = self.state.get_positions()
        # Filter out already-closed positions (sz=0) from comparison/journal
        # entries — they are historical artifacts, not phantom positions
        # needing reconciliation. Without this filter, every reconcile cycle
        # logs the same closed-coin set in `zeroed` even though no mutation
        # happens (caught by supervisor 2026-05-09: 9 phantoms re-listed every
        # 5 min for 24+ hours straight).
        active_local = {coin: pos for coin, pos in local.items() if pos[0] != 0}
        # A dex we could not read is UNKNOWN, not empty. Zeroing on a failed
        # fetch is precisely the bug being fixed, so hold local state for those
        # coins until the dex answers again.
        if unreachable_dexes:
            held = {c for c in active_local if dex_of(c) in unreachable_dexes}
            if held:
                log.warning(
                    "reconcile: holding %d position(s) on unreachable dex(es) %s: %s",
                    len(held), sorted(unreachable_dexes), sorted(held),
                )
            active_local = {c: p for c, p in active_local.items() if c not in held}
        with self._lock:
            for coin, (sz, avg_px) in upstream.items():
                cur = active_local.get(coin)
                if cur != (sz, avg_px):
                    log.info(
                        "reconcile: %s local=%s upstream=(%s,%s)",
                        coin,
                        cur,
                        sz,
                        avg_px,
                    )
                self.state.update_position(coin, sz, avg_px)
            for coin in active_local.keys() - upstream.keys():
                cur_sz, _cur_avg = active_local[coin]
                log.info("reconcile: zeroing %s (was sz=%s)", coin, cur_sz)
                self.state.update_position(coin, 0.0, 0.0)
        # After the position writes, so exposure_at_snapshot_usd lines up with
        # the state the mirror will read.
        self._capture_margin_snapshot(us, _free_usdc(sc))
        snap = self.margin_snapshot()
        self.journal.write(
            "reconcile",
            upstream_count=len(upstream),
            local_count=len(active_local),
            zeroed=sorted(active_local.keys() - upstream.keys()),
            account_value_usd=snap.account_value_usd if snap else None,
            free_collateral_usd=snap.free_collateral_usd if snap else None,
        )
        return self.state.get_positions()

    def _handle(self, msg: Any) -> None:
        if self.health is not None:
            self.health.touch()
        try:
            data = msg.get("data", msg) if isinstance(msg, dict) else {}
            fills = data.get("fills", []) or []
            is_snapshot = bool(data.get("isSnapshot", False))
            for f in fills:
                self._on_fill(f, is_snapshot=is_snapshot)
        except Exception:
            log.exception("PositionTracker error handling msg")

    def _on_fill(self, fill: dict, is_snapshot: bool) -> None:
        tid = fill.get("tid")
        if tid is None:
            return
        coin = fill.get("coin")
        side = fill.get("side")
        direction = fill.get("dir", "")
        try:
            sz = float(fill.get("sz", 0))
            px = float(fill.get("px", 0))
            closed_pnl = float(fill.get("closedPnl", 0))
            fee = float(fill.get("fee", 0))
        except (TypeError, ValueError):
            log.warning("Malformed own fill (numeric): %s", fill)
            return
        ts = int(fill.get("time", time.time() * 1000)) // 1000
        date_utc = datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")

        # Settlement is a special HL fill type for HIP-4 outcomes: px=0 (settled
        # to zero) or px=1 (settled to one), dir="Settlement". Pre-fix this code
        # rejected px=0 fills as malformed, leaving the position dangling and
        # missing the closed_pnl. Now we handle settlement explicitly.
        is_settlement = direction == "Settlement"
        if is_settlement:
            if not coin or sz <= 0:
                log.warning("Malformed settlement fill (fields): %s", fill)
                return
            self._handle_settlement(
                tid=int(tid),
                coin=coin,
                sz=sz,
                px=px,
                closed_pnl=closed_pnl,
                fee=fee,
                ts=ts,
                date_utc=date_utc,
                is_snapshot=is_snapshot,
                fill=fill,
            )
            return

        if not coin or side not in ("B", "A") or sz <= 0 or px <= 0:
            log.warning("Malformed own fill (fields): %s", fill)
            return

        # Skip HL spot-pair fills (`@NNN` or contain `/`). These are stablecoin
        # swaps and other spot trades — they're EXCHANGES, not positions. If we
        # tracked them as positions, the inventory would falsely count toward
        # exposure caps and block legitimate trades. (Real-world bug: a one-time
        # USDC→USDH swap registered as "@230 short of 54.73" and blocked all
        # perp mirroring until reconcile.)
        is_spot_pair = coin.startswith("@") or "/" in coin
        if is_spot_pair:
            self.journal.write(
                "own_fill_skipped",
                tid=int(tid),
                coin=coin,
                reason="spot_pair_not_a_position",
                sz=sz,
                px=px,
            )
            return

        with self._lock:
            inserted = self.state.record_own_fill(
                tid=int(tid),
                coin=coin,
                side=side,
                sz=sz,
                px=px,
                closed_pnl=closed_pnl,
                fee=fee,
                ts=ts,
                date_utc=date_utc,
            )
            if not inserted:
                return  # dup
            self._update_position(coin=coin, side=side, sz=sz, px=px)

        self.journal.write(
            "own_fill",
            tid=int(tid),
            coin=coin,
            side=side,
            sz=sz,
            px=px,
            closed_pnl=closed_pnl,
            fee=fee,
            is_snapshot=is_snapshot,
        )

    def _handle_settlement(
        self,
        *,
        tid: int,
        coin: str,
        sz: float,
        px: float,
        closed_pnl: float,
        fee: float,
        ts: int,
        date_utc: str,
        is_snapshot: bool,
        fill: dict,
    ) -> None:
        """HIP-4 outcome settlement event.

        - Records the fill (so daily P&L includes the realized closed_pnl).
        - Zeros our local position for this coin (it's literally gone).
        - Emits a critical alert with the verdict + P&L (so operator gets
          notified via webhook even if the agent supervising the trade is
          offline — solves the "session went silent at expiry" failure mode).
        - Journals 'settlement' explicitly for forensics.
        """
        with self._lock:
            inserted = self.state.record_own_fill(
                tid=tid,
                coin=coin,
                side=fill.get("side") or "A",
                sz=sz,
                px=px,
                closed_pnl=closed_pnl,
                fee=fee,
                ts=ts,
                date_utc=date_utc,
            )
            if inserted:
                self.state.update_position(coin, 0.0, 0.0)
        verdict = "won" if closed_pnl > 0 else ("lost" if closed_pnl < 0 else "flat")
        sign = "+" if closed_pnl >= 0 else ""
        msg = (
            f"SETTLEMENT {coin} {sz:g} shares -> px=${px:.4f} "
            f"({verdict}, pnl={sign}${closed_pnl:.2f})"
        )
        log.warning(msg)
        self.alerter.alert("critical", msg)
        self.journal.write(
            "settlement",
            tid=tid,
            coin=coin,
            sz=sz,
            settle_px=px,
            closed_pnl=closed_pnl,
            fee=fee,
            verdict=verdict,
            is_snapshot=is_snapshot,
        )

    def _update_position(self, coin: str, side: str, sz: float, px: float) -> None:
        delta = sz if side == "B" else -sz
        existing_sz, existing_avg = self.state.get_position(coin)
        new_sz = existing_sz + delta
        new_avg: float
        if existing_sz == 0:
            new_avg = px
        elif (existing_sz > 0) == (delta > 0):
            new_avg = ((existing_sz * existing_avg) + (delta * px)) / new_sz if new_sz != 0 else 0.0
        elif abs(delta) >= abs(existing_sz):
            new_avg = px if new_sz != 0 else 0.0
        else:
            new_avg = existing_avg
        self.state.update_position(coin, new_sz, new_avg)
