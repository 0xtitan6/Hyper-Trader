import logging
import os
import time
from dataclasses import asdict, dataclass, replace
from threading import Lock

from hyperliquid.utils.error import ClientError

from .alerts import Alerter
from .config import Config
from .errors import OrderError, UnknownPrecisionError
from .funding import FundingTracker
from .journal import Journal
from .market_meta import MarketMeta
from .positions import MarginSnapshot, PositionTracker
from .protocols import ExchangeProto

log = logging.getLogger(__name__)


@dataclass
class TradeIntent:
    coin: str
    is_buy: bool
    sz: float
    limit_px: float
    notional_usd: float
    reduce_only: bool = False


# In-flight TTL — how long after submit do we count an order toward exposure
# before assuming the own-fill WS feedback has updated PositionTracker. Set
# longer than typical HL WS round-trip (~100-500ms) but short enough that a
# stuck or rejected order doesn't permanently inflate our exposure estimate.
IN_FLIGHT_TTL_SECONDS = 30.0

# Order submit retry config. HL rate-limits the /exchange endpoint per-account
# at sub-second granularity; a leader firing 5+ child orders in 1s can trip
# the limiter (live cost 2026-05-30: 6 missed fills today from one ZEC burst).
# Only retry on 429 — other exceptions are ambiguous (timeout-mid-request
# might have placed the order). 2 retries with exp backoff caps total latency
# at ~3s in the worst case.
ORDER_RETRY_MAX_ATTEMPTS = 3   # 1 initial + 2 retries
ORDER_RETRY_BASE_BACKOFF_S = 1.0

# HL rejects some orders IN-BAND: HTTP 200 with the error nested in the body
# ({'status':'ok','response':{'data':{'statuses':[{'error':'Order has invalid
# size.'}]}}}). These never rest or fill. Two failures follow if we ignore it:
#   1. in_flight leak — we reserve notional that only clears on TTL, leaking
#      phantom exposure that eats the cap (observed 2026-06-29: $440 phantom).
#   2. API storm — the HIP-3 `xyz:` equity perps reject EVERY open on szDecimals
#      ("invalid size"), and the mirror re-fires per leader child-fill, so one
#      leader burst becomes hundreds of doomed submits (668 rejects in 4h).
# Structural per-coin errors below get the coin cooled down; others just skip.
POISON_COOLDOWN_SECONDS = 300.0
_POISON_ORDER_ERRORS = ("invalid size", "invalid price")

# How long before we re-attempt a failed update_leverage on a coin. Same
# reasoning as the poison cooldown: a leverage call that fails once (asset not
# registered, HL rejecting the change) will keep failing, and the mirror sees
# one fill per leader child order, so an uncooled retry turns a single leader
# burst into a /exchange storm.
LEVERAGE_RETRY_COOLDOWN_SECONDS = 300.0
# Sub-minimum rescue margin (incident 2026-07-21 → 2026-08-14).
# Two failures compound at the venue minimum:
#   1. Our own floor-rounding: a clip worth exactly `min_per_trade_usd` becomes
#      $9.9x once the size is floored to szDecimals, and the old code silently
#      dropped it. Leader 0x6cd520c1 went to weight 1.0 on 2026-07-21 against
#      fixed_usd=$10 and was muted for 24 days — 10,706 fills filtered vs 79
#      orders accepted, the survivors only funding-amplified stragglers.
#   2. HL values the order with ITS OWN reference price, not our limit price,
#      so an order we compute at exactly $10.00 still rejects when the mark has
#      drifted a few bps against us (30d evidence: 199 rejects, every single one
#      at exactly $10.00 intent notional).
# So the rescue path does not aim at the bare minimum, it aims 1% above it.
# 1% is comfortably wider than observed mark-vs-fill drift on a mirrored fill
# and costs ~$0.10 of extra exposure on a $10 clip.
MIN_NOTIONAL_SAFETY_MARGIN = 0.01

# Hard ceiling on how far the rescue may bump a clip (review addition,
# 2026-08-14). Rounding up only ever INCREASES exposure, and on coarse-
# szDecimals assets one step is not small: a $12 clip on an $18/share
# integer-share outcome becomes $18 (1.5x). With max_per_trade_usd as the
# only backstop the theoretical worst case is max_per_trade_usd /
# min_per_trade_usd — at the live $120/$10 that is a 12x unintended
# position, which is a position-sizing decision, not a rounding fix.
# We would rather skip the fill than take a materially larger bet than the
# configured weight asked for. A skipped mirror costs one leader signal; an
# oversized one costs real money on a $200 book.
MAX_BUMP_RATIO = 1.5
# How often we're willing to re-alert about the same coin being skipped for
# unknown szDecimals. The skip itself is per-fill and a busy leader can fire
# dozens a minute, so the alert (not the journal line) needs a throttle.
PRECISION_ALERT_THROTTLE_SECONDS = 900.0


class MirrorTrader:
    def __init__(
        self,
        cfg: Config,
        exchange: ExchangeProto,
        positions: PositionTracker,
        journal: Journal,
        alerter: Alerter,
        market_meta: MarketMeta,
        funding: FundingTracker | None = None,
    ):
        self.cfg = cfg
        self.exchange = exchange
        self.positions = positions
        self.journal = journal
        self.alerter = alerter
        self.market_meta = market_meta
        self.funding = funding  # None = funding-aware sizing disabled
        # Held across risk-check + submit so two concurrent leader fills can't
        # both pass the exposure cap based on stale state.
        self._submit_lock = Lock()
        # In-flight orders — pending notional that's been submitted but whose
        # own-fill confirmation hasn't yet propagated through PositionTracker.
        # Without this, rapid leader fills bypass `max_total_exposure_usd`
        # because each new submit's risk check sees stale local position state.
        # (Real-world bug: 19 fills bypassed a $60 cap and produced a 5x XMR
        # leverage runaway on 2026-05-05.) Each entry: (expires_at, notional).
        self._in_flight: list[tuple[float, float]] = []
        # Coins under a structural-rejection cooldown (bad szDecimals → repeated
        # "invalid size"). coin -> unix ts until which new opens are skipped.
        self._poison_until: dict[str, float] = {}
        # Coins whose cross leverage we've already pinned this process (see
        # _ensure_leverage). `_leverage_attempted` holds the last attempt time
        # per coin so failures back off instead of retrying every fill.
        self._leverage_set: set[str] = set()
        self._leverage_attempted: dict[str, float] = {}
        # coin -> unix ts before which we won't re-alert about unknown
        # szDecimals. Journal still records every skip; only the alert throttles.
        self._precision_alert_after: dict[str, float] = {}
        # Per-leader sizing weight, refreshed every discover_leaders cycle.
        # Default 1.0 = original proportional sizing. Updated via
        # update_leader_weights() from main's refresh loop.
        self._leader_weights: dict[str, float] = {}

    def update_leader_weights(self, weights: dict[str, float]) -> None:
        """Replace the per-leader weight map (called after each leader refresh).

        Keys are lowercase address strings; values are size multipliers in [0.1, 5.0].
        Missing leaders default to 1.0 in `_build_intent`.
        """
        self._leader_weights = {a.lower(): float(w) for a, w in weights.items()}

    def on_leader_fill(self, leader: str, fill: dict) -> None:
        tid = fill.get("tid")
        # Once _submit is entered, a live order may have been placed. Any
        # failure AFTER this point must NOT unmark the tid, else backfill
        # re-dispatches the same leader fill and double-trades.
        submit_attempted = False
        try:
            self.journal.write(
                "leader_fill",
                leader=leader,
                tid=tid,
                coin=fill.get("coin"),
                px=fill.get("px"),
                sz=fill.get("sz"),
                side=fill.get("side"),
            )
            intent, skip_reason = self._build_intent(fill, leader)
            if intent is None:
                # `skip_reason` is deliberately specific — see _build_intent's
                # docstring. Never collapse these back into one token.
                self.journal.write("intent_skipped", leader=leader, tid=tid, reason=skip_reason)
                return
            with self._submit_lock:
                # Re-evaluate reduce_only inside the lock — position state may
                # have changed (own-fill arrived) between _build_intent and here.
                intent = replace(
                    intent,
                    reduce_only=self._is_reduce_only(intent.coin, intent.is_buy, intent.sz),
                )
                # Per-coin weight-priority conflict lock (PR #25). Caught
                # 2026-05-10: two leaders took opposite sides on TON within
                # 30 min and we whipsawed -$1.85 across both legs. Rule:
                # if our existing position on this coin was opened by a
                # different leader AND new fill is opposite-direction AND
                # current leader has lower weight than originator → skip.
                conflict_reason = self._check_leader_conflict(intent, leader)
                if conflict_reason is not None:
                    log.info(
                        "[conflict] skip leader=%s coin=%s reason=%s",
                        leader[:10], intent.coin, conflict_reason,
                    )
                    self.journal.write(
                        "intent_skipped", leader=leader, tid=tid,
                        reason=f"leader_conflict:{conflict_reason}",
                    )
                    return
                ok, reason = self._risk_check(intent)
                self.journal.write(
                    "risk_check",
                    leader=leader,
                    tid=tid,
                    ok=ok,
                    reason=reason,
                    intent=asdict(intent),
                )
                if not ok:
                    log.info(
                        "[risk] reject (%s) leader=%s coin=%s", reason, leader[:10], intent.coin
                    )
                    return
                # Mark BEFORE the call: _submit places the live order internally,
                # so if it raises (or anything after it does) the order may
                # already exist and the tid must stay marked.
                submit_attempted = True
                submitted = self._submit(intent, leader, tid)
                # Record this leader as the position's originator only if the
                # order was actually accepted — a rejected order must not claim
                # the coin (else conflict-lock blocks the real originator).
                if submitted:
                    self.positions.state.set_position_originator(intent.coin, leader)
        except UnknownPrecisionError as e:
            # A HIP-3 builder-dex coin (`xyz:*`) whose szDecimals never
            # arrived — `register_hip3_dexes: perpDexs fetch failed` fired 215
            # times in Aug 2026 and left the rounder blind. We used to guess
            # 4dp: `xyz:MU sz=0.0143` on 2026-08-10 (xyz:MU is really 3dp) →
            # `Order has invalid size` → _POISON_ORDER_ERRORS muted the coin
            # for 300s → every later leader fill on it died `poison_cooldown`
            # (5,366 Jul-Aug, 2,510 on 07-27 alone), on exactly the surface
            # several of our leaders specialise in.
            #
            # Skip instead, with its own greppable reason. Cost of a skip is
            # one signal; cost of a poisoned coin is EVERY signal on it for
            # the next 5 minutes, on repeat. This path is pre-_submit, so no
            # order exists and the coin stays clean — the trade resumes on
            # its own the moment the next HIP-3 refresh registers the symbol.
            skip_coin = fill.get("coin") or "?"
            log.warning("[precision] skip leader=%s tid=%s: %s", leader[:10], tid, e)
            self.journal.write(
                "intent_skipped",
                leader=leader,
                tid=tid,
                coin=skip_coin,
                reason="unknown_sz_decimals",
                detail=str(e),
            )
            # Alert too, throttled per-coin. Silence here would be dangerous:
            # our best-evidenced leader (0x819d06c0, sharpe 0.59) is 64%
            # xyz:SP500, so a stuck registration means we quietly stop
            # mirroring the leader we most want to mirror. One alert per coin
            # per 15 min is enough to notice without becoming its own storm.
            now = time.time()
            if now >= self._precision_alert_after.get(skip_coin, 0.0):
                self._precision_alert_after[skip_coin] = now + PRECISION_ALERT_THROTTLE_SECONDS
                self.alerter.alert(
                    "warn",
                    f"Skipping {skip_coin}: szDecimals unknown (HIP-3 registration "
                    "incomplete). Not trading this coin until it registers.",
                )
        except OrderError:
            raise
        except Exception:
            log.exception("Mirror pipeline error leader=%s tid=%s", leader, tid)
            self.alerter.alert(
                "error",
                f"Mirror pipeline exception leader={leader[:10]} tid={tid}",
            )
            self.journal.write("pipeline_error", leader=leader, tid=tid)
            # Unmark so backfill can re-dispatch this fill — but ONLY if the
            # failure happened before we entered _submit. Once _submit runs a
            # live order may have been placed (regardless of OrderError vs a
            # plain exception from set_position_originator / journal.write on
            # the post-submit success path), so the tid must stay marked to
            # avoid a duplicate order on the next backfill/re-dispatch.
            if isinstance(tid, int) and not submit_attempted:
                self.positions.state.unmark_tid_seen(tid)

    def _build_intent(self, fill: dict, leader: str = "") -> tuple[TradeIntent | None, str]:
        """Size a leader fill into our own order.

        Returns `(intent, reason)`. On success `reason` is "ok"; on a skip
        `intent` is None and `reason` names the SPECIFIC gate that fired.

        The reason string is not cosmetic. Until 2026-08-14 every skip here
        journalled the single opaque token "filter" — 2,449,814 of them in 30
        days — so a leader that had been muted by a sizing bug for 24 days was
        indistinguishable from a leader trading markets we simply don't allow.
        Any new skip added below MUST get its own reason.
        """
        coin = fill.get("coin")
        try:
            px = float(fill.get("px", 0))
            sz = float(fill.get("sz", 0))
        except (TypeError, ValueError):
            return None, "bad_fill_numbers"
        side = fill.get("side")
        if not coin or px <= 0 or sz <= 0 or side not in ("B", "A"):
            return None, "bad_fill_fields"
        if not self._is_allowed_market(coin):
            return None, "market_type"

        is_buy = side == "B"
        leader_notional = px * sz
        s = self.cfg.sizing
        weight = self._leader_weights.get(leader.lower(), 1.0) if leader else 1.0
        if s.mode == "proportional":
            mirror_notional = leader_notional * s.proportional_fraction * weight
        elif s.mode == "fixed":
            mirror_notional = float(s.fixed_usd) * weight
        else:
            return None, "bad_sizing_mode"

        # Outcomes have a separate (typically higher) min — HL enforces $10
        # USDH min on HIP-4 orders. Perps allow much smaller mirror sizes.
        is_outcome = coin.startswith("#") or coin.startswith("+")
        effective_min = (
            s.outcome_min_per_trade_usd
            if is_outcome and s.outcome_min_per_trade_usd is not None
            else s.min_per_trade_usd
        )

        # Funding-aware sizing (perps only — outcomes settle at expiry, no funding).
        # Apply BEFORE the max_per_trade cap so amplification still respects it.
        if (
            s.use_funding_aware_sizing
            and self.funding is not None
            and not is_outcome
        ):
            apr_pct = self.funding.get_apr_pct(coin)
            if apr_pct is not None:
                # Convention: APR > 0 means longs PAY shorts (i.e. shorts get paid).
                # we_get_paid_apr = +apr if short, -apr if long.
                we_get_paid_apr = -apr_pct if is_buy else apr_pct
                if we_get_paid_apr <= -s.funding_skip_threshold_apr_pct:
                    # Adverse funding too costly — skip the mirror entirely.
                    return None, "funding_skip"
                if we_get_paid_apr >= s.funding_amplify_threshold_apr_pct:
                    # Linear ramp: at threshold → 1.0x, scaled up to amplify_cap
                    # at +200% APR. Capped at amplify_cap.
                    raw_mult = 1.0 + (we_get_paid_apr / 200.0)
                    mirror_notional *= min(raw_mult, s.funding_amplify_cap)

        mirror_notional = min(mirror_notional, s.max_per_trade_usd)
        if mirror_notional < effective_min:
            # Genuinely too small to trade. This is the ONLY place a
            # below-minimum clip is discarded; the rescue below deliberately
            # never fires here, so we can never size UP a trade the configured
            # weight/fraction did not already ask for.
            return None, "sub_min"

        rounded_px = self.market_meta.round_price(px, coin)
        raw_sz = mirror_notional / px
        # Deliberately NOT caught here: UnknownPrecisionError means this is a
        # HIP-3 builder-dex coin whose szDecimals we never received, and it is
        # handled with its own journal reason in on_leader_fill. Guessing the
        # precision is what started the Jul-Aug 2026 poison cascade.
        rounded_sz = self.market_meta.round_size(coin, raw_sz)
        rounded_notional = rounded_sz * rounded_px

        # Sub-minimum rescue (2026-08-14). We WANTED at least `effective_min`
        # of notional, but flooring the size to szDecimals took us under it —
        # or under HL's own mark-price valuation of it, see the constant above.
        # Rather than discard the leader's signal, round the size up to the
        # smallest szDecimals step that clears the margin-adjusted minimum.
        # For the incident case that is exactly one step; coarse-szDecimals
        # assets (integer-share outcomes) may need the size expressed at their
        # granularity, which is the same operation.
        if rounded_sz <= 0 or rounded_notional < effective_min * (1 + MIN_NOTIONAL_SAFETY_MARGIN):
            target_notional = effective_min * (1 + MIN_NOTIONAL_SAFETY_MARGIN)
            bumped_sz = self.market_meta.round_size_up(coin, target_notional / rounded_px)
            bumped_notional = bumped_sz * rounded_px
            # Rounding up ONLY ever increases exposure, so max_per_trade_usd is
            # the hard stop: if the smallest viable order is bigger than the
            # operator's per-trade cap, we skip rather than breach the cap.
            if bumped_sz <= 0 or bumped_notional > s.max_per_trade_usd:
                return None, "rounding:exceeds_max"
            # ...but max_per_trade_usd alone is far too loose a leash on a
            # coarse-granularity asset (see MAX_BUMP_RATIO). Also refuse to
            # bump more than MAX_BUMP_RATIO x what the configured weight
            # actually asked for.
            if bumped_notional > mirror_notional * MAX_BUMP_RATIO:
                return None, "rounding:exceeds_bump_ratio"
            log.info(
                "[sizing] rounded up to clear min: coin=%s %.8f->%.8f sz "
                "($%.2f->$%.2f, min=$%.2f)",
                coin, rounded_sz, bumped_sz, rounded_notional, bumped_notional, effective_min,
            )
            self.journal.write(
                "size_rounded_up",
                leader=leader,
                coin=coin,
                from_sz=rounded_sz,
                to_sz=bumped_sz,
                from_notional=rounded_notional,
                to_notional=bumped_notional,
                effective_min=effective_min,
            )
            rounded_sz, rounded_notional = bumped_sz, bumped_notional

        # reduce_only deferred — evaluated inside _submit_lock against fresh state.
        return TradeIntent(
            coin=coin,
            is_buy=is_buy,
            sz=rounded_sz,
            limit_px=rounded_px,
            notional_usd=rounded_notional,
            reduce_only=False,
        ), "ok"

    def _check_leader_conflict(self, intent: TradeIntent, leader: str) -> str | None:
        """Per-coin weight-priority conflict check.

        Returns None if the trade is allowed, or a string reason if it should
        be skipped because a different (higher-weight) leader already holds
        a position on this coin in the opposite direction.

        Rules:
          1. No existing position → allow (this leader becomes originator)
          2. Existing position from same leader → allow (they're managing it)
          3. Existing position from different leader, same direction → allow
             (we're adding to position they opened; benign)
          4. Existing position from different leader, OPPOSITE direction
             AND new leader weight ≤ originator weight → SKIP (conflict)
          5. Same as (4) but new leader has STRICTLY higher weight → allow
             (override based on conviction)
        """
        existing_sz, _ = self.positions.state.get_position(intent.coin)
        if existing_sz == 0:
            return None  # rule 1
        originator = self.positions.state.get_position_originator(intent.coin)
        # Treat anything that isn't a real address string as "unset" — covers
        # pre-PR-#25 positions migrated without an originator AND defends
        # against mock-test environments returning unexpected types.
        if not isinstance(originator, str) or not originator:
            return None
        if originator == leader.lower():
            return None  # rule 2: same leader managing their own position
        # Different leader. Is the new fill opposite-direction?
        opposing = (existing_sz > 0 and not intent.is_buy) or (
            existing_sz < 0 and intent.is_buy
        )
        if not opposing:
            return None  # rule 3 (same-side add is fine)
        # Conflict candidate. Compare weights.
        new_weight = self._leader_weights.get(leader.lower(), 1.0)
        orig_weight = self._leader_weights.get(originator, 1.0)
        if new_weight > orig_weight:
            return None  # rule 5 (override allowed)
        # rule 4: skip
        return (
            f"originator={originator[:10]} (w={orig_weight:.2f}) "
            f"vs new_leader={leader[:10]} (w={new_weight:.2f})"
        )

    def _is_reduce_only(self, coin: str, is_buy: bool, sz: float) -> bool:
        """True iff this order strictly shrinks an existing opposing position
        without flipping through zero. HL rejects reduce-only orders that flip.
        """
        existing_sz, _ = self.positions.state.get_position(coin)
        if existing_sz == 0:
            return False
        # Long position + sell, or short position + buy → reducing
        opposing = (existing_sz > 0 and not is_buy) or (existing_sz < 0 and is_buy)
        if not opposing:
            return False
        return sz <= abs(existing_sz)

    def _is_allowed_market(self, coin: str) -> bool:
        allowed = self.cfg.risk.allowed_market_types
        is_outcome = coin.startswith("#") or coin.startswith("+")
        is_spot = coin.startswith("@") or "/" in coin
        is_perp = not is_outcome and not is_spot
        return (
            (is_outcome and "outcome" in allowed)
            or (is_spot and "spot" in allowed)
            or (is_perp and "perp" in allowed)
        )

    def _in_flight_notional(self) -> float:
        """Sum of in-flight order notionals whose TTL hasn't expired.

        Side-effect: prunes expired entries while iterating. Caller must hold
        `_submit_lock` (we do — _risk_check is called inside the lock).
        """
        now = time.time()
        active: list[tuple[float, float]] = []
        total = 0.0
        for expires_at, notional in self._in_flight:
            if expires_at > now:
                active.append((expires_at, notional))
                total += notional
        self._in_flight = active
        return total

    def _risk_check(self, intent: TradeIntent) -> tuple[bool, str]:
        r = self.cfg.risk
        if os.path.exists(r.kill_switch_file):
            self.alerter.alert("warn", f"Kill switch active: {r.kill_switch_file}")
            return False, "kill_switch"

        net_realized = self.positions.realized_pnl_today()
        if -net_realized >= r.max_daily_loss_usd:
            self.alerter.alert("critical", f"Daily loss cap hit: net=${net_realized:.2f}")
            return False, f"daily_loss_cap (net={net_realized:.2f})"

        # Reduce-only orders shrink, never grow exposure — bypass the cap.
        # (Also bypasses the poison cooldown below: exits must always be allowed
        # so a poisoned coin can still be closed if we somehow hold it.)
        if intent.reduce_only:
            return True, ""

        # Coin in structural-rejection cooldown (see _POISON_ORDER_ERRORS). Skip
        # opens so we don't storm the API with orders that can't succeed.
        if self._poison_until.get(intent.coin, 0.0) > time.time():
            return False, f"poison_cooldown ({intent.coin})"

        exposure = self.positions.total_exposure_usd()
        in_flight = self._in_flight_notional()
        # Total committed exposure = confirmed positions + pending submissions
        # whose own-fill hasn't propagated through PositionTracker yet. Without
        # `in_flight`, rapid-fire leader mirrors race the WS feedback loop and
        # bypass the cap entirely (real bug observed 2026-05-05).
        committed = exposure + in_flight
        if committed + intent.notional_usd > r.max_total_exposure_usd:
            return False, (
                f"exposure_cap (have=${exposure:.0f} + in_flight=${in_flight:.0f} "
                f"+ new=${intent.notional_usd:.0f} > ${r.max_total_exposure_usd:.0f})"
            )

        # The exposure cap above is NOTIONAL only — it never asked whether the
        # account can actually post the initial margin. Audit 2026-08-14: 1,599
        # "Insufficient margin to place order" in-band rejects in 30 days
        # ($18,952 of dropped notional) against 457 accepted orders, i.e. 3.5
        # doomed /exchange round trips per real one, each one eating rate-limit
        # budget the next genuine fill needs. Raising max_total_exposure_usd
        # 350 -> 800 on a ~$200 account makes margin bind first, always.
        return self._margin_headroom_check(intent, committed)

    def _effective_leverage(self, coin: str) -> float:
        """Leverage we actually expect HL to apply to this coin.

        min(configured target, asset max) — this is what _ensure_leverage pins
        the coin to, so the margin math and the leverage we actually set can't
        drift apart. Truncated to a whole number because that's all HL accepts,
        and floored at 1x so it's always a safe divisor.
        """
        lev = min(self.cfg.risk.target_leverage, self.market_meta.max_leverage(coin))
        return float(max(1, int(lev)))

    def _margin_headroom_check(self, intent: TradeIntent, committed: float) -> tuple[bool, str]:
        """Reject an open whose initial margin exceeds our free collateral.

        Reads the margin snapshot PositionTracker caches on every reconcile
        (startup + every 5 min) — deliberately no HTTP here: this runs under
        `_submit_lock` on the hot path, and a leader burst is 5+ fills/second.

        Deliberately NOT applied to:
          - HIP-4 outcomes / spot: bought outright out of the spot balance, not
            perp margin. Consistent with the audit — zero of the 1,599 margin
            rejects were outcome legs.
          - HIP-3 builder dexes (`xyz:NVDA` etc): each dex is a SEPARATE
            clearinghouse with its own collateral (measured 2026-08-14: base
            perp withdrawable $0.0096, xyz dex $0.0015). Gating them on the base
            account's free margin would be checking the wrong wallet, so HL
            stays the authority there until we snapshot per-dex state.

        Fails OPEN (no snapshot / stale snapshot): this guard saves wasted round
        trips, it is not the last line of defence — HL still rejects what it
        won't accept. A broken reconcile loop must not silently halt trading.
        """
        coin = intent.coin
        is_outcome_or_spot = (
            coin.startswith("#") or coin.startswith("+") or coin.startswith("@") or "/" in coin
        )
        if is_outcome_or_spot or ":" in coin:
            return True, ""

        snap = self.positions.margin_snapshot()
        # isinstance (not `is None`) on purpose: PositionTracker is a MagicMock
        # in much of the suite and in the shadow/backtest harnesses, where any
        # attribute returns a truthy mock. Same defence as _check_leader_conflict.
        if not isinstance(snap, MarginSnapshot):
            return True, ""
        max_age = self.cfg.risk.margin_snapshot_max_age_s
        if snap.age_s > max_age:
            log.warning(
                "[margin] snapshot stale (%.0fs > %.0fs) — skipping headroom check for %s",
                snap.age_s, max_age, coin,
            )
            return True, ""

        lev = self._effective_leverage(coin)
        required = intent.notional_usd / lev
        # Positions opened SINCE the snapshot have already eaten margin that
        # `free_collateral_usd` still shows as available. Without this term a
        # single leader burst re-spends the same free collateral on every fill
        # for up to 5 minutes — the same stale-state race `_in_flight` was
        # added for on 2026-05-05, one layer up. Charged at this intent's
        # leverage, which is an approximation when the burst spans coins.
        growth = max(0.0, committed - snap.exposure_at_snapshot_usd)
        free = snap.free_collateral_usd - (growth / lev)
        budget = free * (1.0 - self.cfg.risk.margin_headroom_buffer_frac)
        if required > budget:
            return False, (
                f"margin_headroom (need=${required:.2f} at {lev:g}x > budget=${budget:.2f} "
                f"| free=${snap.free_collateral_usd:.2f} since_snapshot=${growth:.0f} "
                f"age={snap.age_s:.0f}s)"
            )
        return True, ""

    def _ensure_leverage(self, coin: str) -> None:
        """Pin this coin's cross leverage to risk.target_leverage (capped at the
        asset max) before our first live open on it.

        The bot has never called update_leverage in its life, so every asset ran
        at whatever HL defaulted it to — live account 2026-08-14 held JUP at 10x
        next to JTO/AR/AVNT/XMR at 5x, none of it chosen by us. That also means
        the margin a given notional consumes was HL's decision, so the headroom
        check above would be doing arithmetic against a number we don't control.

        Best-effort by design: a failure here NEVER blocks the order. Worst case
        we're back to the old implicit-default behaviour for that coin, and HL
        enforces margin either way. Failures back off for
        LEVERAGE_RETRY_COOLDOWN_SECONDS so a leader burst can't storm /exchange.
        """
        if not self.cfg.risk.set_leverage or coin in self._leverage_set:
            return
        # Outcomes and spot aren't leveraged instruments — update_leverage on
        # them is meaningless and errors on the asset lookup.
        if coin.startswith("#") or coin.startswith("+") or coin.startswith("@") or "/" in coin:
            return
        now = time.time()
        if now - self._leverage_attempted.get(coin, 0.0) < LEVERAGE_RETRY_COOLDOWN_SECONDS:
            return
        # Never re-margin a position we already hold. LOWERING leverage on an
        # open position raises that position's initial-margin requirement on the
        # spot, and this account runs fully committed (2026-08-14: accountValue
        # $75.22 vs totalMarginUsed $75.21) — HL would either reject the change
        # or we'd hand ourselves a worse liquidation price for no new edge.
        # Flat coins only; leverage then applies to the position we're opening.
        try:
            existing_sz, _ = self.positions.state.get_position(coin)
            if existing_sz:
                return
        except Exception:
            log.exception("[leverage] position lookup failed for %s; skipping", coin)
            return

        self._leverage_attempted[coin] = now
        lev = int(self._effective_leverage(coin))
        try:
            result = self.exchange.update_leverage(lev, coin, True)  # is_cross=True
        except Exception as e:
            log.warning("[leverage] update_leverage(%s, %dx) failed: %s", coin, lev, e)
            self.journal.write("leverage_set_failed", coin=coin, leverage=lev, error=str(e))
            return
        # update_leverage rejects in-band exactly like order() does (HTTP 200
        # with the reason nested in the body), so reuse the same parser.
        err = self._order_status_error(result)
        if err is not None:
            log.warning("[leverage] %s rejected at %dx: %s", coin, lev, err)
            self.journal.write("leverage_set_failed", coin=coin, leverage=lev, error=err)
            return
        self._leverage_set.add(coin)
        log.info("[leverage] %s pinned to %dx cross", coin, lev)
        self.journal.write("leverage_set", coin=coin, leverage=lev)

    def _submit_with_retry(
        self, intent: TradeIntent, px: float, leader: str, tid: object
    ) -> dict:
        """Wrap exchange.order() with retry on 429. Caller is `_submit` —
        runs inside `_submit_lock` so no concurrent retry storms.

        Why only 429: HL responds 429 BEFORE the order is placed (rejected at
        the rate-limit gate), so retry is safe — no risk of double-submit.
        Network timeouts mid-request, by contrast, are ambiguous (order may
        or may not have reached the matching engine), so we fail loud and
        let the operator decide.

        On final failure, raises OrderError exactly like the original
        no-retry path — caller-side journal+alert behavior is unchanged.
        """
        last_exc: Exception | None = None
        for attempt in range(ORDER_RETRY_MAX_ATTEMPTS):
            try:
                result = self.exchange.order(
                    intent.coin,
                    intent.is_buy,
                    intent.sz,
                    px,
                    order_type={"limit": {"tif": "Ioc"}},
                    reduce_only=intent.reduce_only,
                )
            except ClientError as e:
                last_exc = e
                status = getattr(e, "status_code", None)
                # Some wrappers stash the code as args[0]
                if status is None and e.args:
                    candidate = e.args[0]
                    if isinstance(candidate, int):
                        status = candidate
                if status == 429 and attempt + 1 < ORDER_RETRY_MAX_ATTEMPTS:
                    backoff = ORDER_RETRY_BASE_BACKOFF_S * (2**attempt)
                    log.warning(
                        "Order 429 on %s (attempt %d/%d); sleeping %.1fs",
                        intent.coin, attempt + 1, ORDER_RETRY_MAX_ATTEMPTS, backoff,
                    )
                    time.sleep(backoff)
                    continue
                # Non-retryable status (or budget exhausted) — fall through to raise
                break
            except Exception as e:
                # Non-ClientError: ambiguous (timeout, connection) → fail fast.
                # Don't retry — could double-submit a placed order.
                last_exc = e
                break
            else:
                # Success — caller (_submit) handles in-flight tracking +
                # journaling.
                return result

        # All attempts exhausted or non-retryable failure
        assert last_exc is not None
        self.alerter.alert(
            "error", f"Order submit failed: {type(last_exc).__name__}: {last_exc}"
        )
        self.journal.write(
            "order_failed",
            leader=leader,
            tid=tid,
            intent=asdict(intent),
            error=str(last_exc),
        )
        raise OrderError(f"order failed: {last_exc}") from last_exc

    @staticmethod
    def _order_status_error(result: object) -> str | None:
        """Return HL's in-band rejection message, or None if the order was
        accepted (rested or filled).

        HL returns HTTP 200 even when it rejects an order — the reason is nested
        in the body. Two shapes:
          - {'status': 'err', 'response': '<message>'}
          - {'status': 'ok', 'response': {'data': {'statuses': [{'error': ...}]}}}
        A status dict with 'resting' or 'filled' (and no 'error') is a success.
        """
        if not isinstance(result, dict):
            return None
        if result.get("status") == "err":
            resp = result.get("response")
            return str(resp) if resp else "unknown error"
        response = result.get("response")
        if not isinstance(response, dict):
            return None
        data = response.get("data")
        if not isinstance(data, dict):
            return None
        for st in data.get("statuses") or []:
            if isinstance(st, dict) and st.get("error"):
                return str(st["error"])
        return None

    def _submit(self, intent: TradeIntent, leader: str, tid: object) -> bool:
        if self.cfg.risk.dry_run:
            log.info(
                "[DRY] %s %s %.6f @ %.4f notional=$%.2f reduce_only=%s leader=%s tid=%s",
                "BUY" if intent.is_buy else "SELL",
                intent.coin,
                intent.sz,
                intent.limit_px,
                intent.notional_usd,
                intent.reduce_only,
                leader[:10],
                tid,
            )
            self.journal.write("order_dry_run", leader=leader, tid=tid, intent=asdict(intent))
            return True

        self._ensure_leverage(intent.coin)

        slip = self.cfg.sizing.ioc_slippage_bps / 10_000.0
        slipped_px = intent.limit_px * (1 + slip if intent.is_buy else 1 - slip)
        px = self.market_meta.round_price(slipped_px, intent.coin)
        log.info(
            "Submitting %s %s %.6f @ %.4f notional=$%.2f reduce_only=%s",
            "BUY" if intent.is_buy else "SELL",
            intent.coin,
            intent.sz,
            px,
            intent.notional_usd,
            intent.reduce_only,
        )
        result = self._submit_with_retry(intent, px, leader, tid)
        log.info("Order result: %s", result)

        # HL may reject in-band (HTTP 200 + error in body). A rejected order
        # never rests or fills, so it must NOT reserve in-flight notional —
        # doing so leaks phantom exposure that only clears on TTL (2026-06-29:
        # $440 phantom ate the cap). Return False so the caller doesn't claim
        # the coin's originator slot.
        err = self._order_status_error(result)
        if err is not None:
            log.warning("Order rejected in-band on %s: %s", intent.coin, err)
            self.alerter.alert("warn", f"Order rejected {intent.coin}: {err}")
            self.journal.write(
                "order_rejected",
                leader=leader,
                tid=tid,
                intent=asdict(intent),
                error=err,
                result=result,
            )
            if any(p in err.lower() for p in _POISON_ORDER_ERRORS):
                self._poison_until[intent.coin] = time.time() + POISON_COOLDOWN_SECONDS
                log.warning(
                    "Coin %s poisoned for %.0fs (%s)",
                    intent.coin, POISON_COOLDOWN_SECONDS, err,
                )
            return False

        # Accepted (rested/filled): the order is now LIVE on the exchange. Any
        # error past this point (in-flight bookkeeping, journal write) must NOT
        # propagate — an exception here escapes _submit -> on_leader_fill's
        # `except Exception`, which unmarks the tid and lets backfill re-dispatch
        # the SAME leader fill, placing a duplicate live order (double-trade).
        # journal.write does open()+write() on every call, so a transient FS
        # fault (ENOSPC/EDQUOT/EROFS/EMFILE/permission) can raise here. Swallow
        # and alert instead: the order is already placed, so returning True (tid
        # stays marked) is the only safe outcome.
        try:
            # reserve notional as in-flight until the own-fill confirmation
            # propagates through PositionTracker. _submit runs inside
            # _submit_lock so mutating _in_flight here needs no extra lock.
            self._in_flight.append((time.time() + IN_FLIGHT_TTL_SECONDS, intent.notional_usd))
            self.journal.write(
                "order_result",
                leader=leader,
                tid=tid,
                intent=asdict(intent),
                result=result,
            )
        except Exception:
            log.exception(
                "Post-submit bookkeeping failed (order is LIVE) leader=%s tid=%s coin=%s",
                leader, tid, intent.coin,
            )
            self.alerter.alert(
                "critical",
                f"Post-submit bookkeeping failed but order is LIVE "
                f"leader={leader[:10]} tid={tid} coin={intent.coin} — tid stays "
                f"marked to prevent double-trade",
            )
        return True
