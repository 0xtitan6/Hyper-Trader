import logging
from typing import Any

from .config import DiscoveryConfig
from .leader_score import load_metrics, meets_quality
from .liquidiction import LiquidictionClient, Trader
from .protocols import InfoProto

log = logging.getLogger(__name__)


def _account_value(state: Any) -> float | None:
    """`marginSummary.accountValue` out of a clearinghouse state, or None."""
    if not isinstance(state, dict):
        return None
    summary = state.get("marginSummary")
    if not isinstance(summary, dict):
        return None
    try:
        return float(summary.get("accountValue", 0) or 0)
    except (TypeError, ValueError):
        return None


def _base_equity_usd(info: Any, address: str) -> float | None:
    """The leader's BASE-dex perp equity, or None if the probe failed."""
    try:
        return _account_value(info.user_state(address) or {})
    except Exception:  # a probe failure must not break discovery
        log.warning("discover_leaders: base equity probe failed for %s", address[:12], exc_info=True)
        return None


def hip3_dex_names(info: Any) -> list[str] | None:
    """Active HIP-3 builder-dex names, or None if we couldn't enumerate them.

    None is distinct from `[]`: empty means "there are genuinely no builder
    dexes", None means "we don't know", and INV 4 forbids actioning unknown as
    empty. Same shape as `positions.PositionReconciler._hip3_dex_names`.

    The answer is a property of the EXCHANGE, not of any wallet, so callers
    fetch it once per discovery cycle and pass it to every `_perp_equity_usd`
    call. Fetching it per candidate would put ~60 identical calls into each
    cycle, and INV 7 records HL 429-ing us over back-to-back /info calls.
    """
    try:
        dexes = info.post("/info", {"type": "perpDexs"})
    except Exception:  # unknown, never "no dexes" — see the caller
        log.warning("discover_leaders: perpDexs fetch failed", exc_info=True)
        return None
    if not isinstance(dexes, list):
        return None
    return [d["name"] for d in dexes if isinstance(d, dict) and d.get("name")]


def _dex_equity_usd(info: Any, address: str, dex: str) -> float | None:
    """The leader's equity on one HIP-3 clearinghouse, or None if unreadable."""
    try:
        state = info.post(
            "/info", {"type": "clearinghouseState", "user": address, "dex": dex}
        )
    except Exception:  # one bad dex must not blind the whole probe
        log.warning(
            "discover_leaders: dex=%s equity probe failed for %s", dex, address[:12],
            exc_info=True,
        )
        return None
    return _account_value(state)


def _perp_equity_usd(
    info: Any, address: str, *, min_usd: float, dex_names: list[str] | None
) -> float | None:
    """The equity figure that decides the solvency gate, or None if unknown.

    Contract: if ANY clearinghouse clears `min_usd`, returns that one (so the
    result is >= min_usd). Otherwise returns the largest equity we could read
    (< min_usd), or None if we could not read enough to be sure.

    Never a sum across dexes — INV 2, each dex settles against its own
    collateral, so $300 on base plus $300 on xyz is not a $600 wallet on
    either. "Any clearinghouse clears the bar" is the only sound test.

    Why per-dex at all (P0c, 2026-08-15): this read used `user_state` alone,
    which covers the BASE dex only — INV 1, the same misread that shipped in
    three separate modules that day. A leader whose collateral sits on a HIP-3
    dex read $0 and was rejected as insolvent:

        0x819d06c0   base $0.00  ->    $514 on xyz   <- our PINNED incumbent
        0x9551e7d4   base $0.00  ->  $8,104 on xyz
        0x810b41bd   base $0.00  -> $62,955 on xyz
        0x2649bb08   base $0.00  -> $15,109 on xyz

    18-21 of 60 candidates were being rejected this way. Our own pinned leader
    would have been rejected the moment it was unpinned.

    `dex_names` comes from `hip3_dex_names` (fetched once per cycle, see
    there), and carries its None-vs-[] distinction: None = we could not
    enumerate, [] = there are genuinely none.

    `min_usd` and `dex_names` are keyword-only and have no defaults on
    purpose: the base-dex shortcut below is only sound against a real
    threshold, and a caller that forgot either argument would silently get
    back the base-only behaviour this function exists to fix.

    None means "we did not measure it", not "they have nothing" (INV 4), and
    callers must not reject on it. But fail-open must not decay into never-act
    (INV 4, second half): `perpDexs` failed 215 times in August, and answering
    None on every blip would disable the gate outright. So we only answer None
    when the gap could actually change the verdict — a readable clearinghouse
    that already clears `min_usd` settles the question whatever the unreadable
    ones hold, and a wallet that is genuinely empty everywhere readable is
    still rejected as long as the enumeration itself was complete.
    """
    best: float | None = None
    complete = True

    base = _base_equity_usd(info, address)
    if base is None:
        complete = False
    else:
        best = base
        if base >= min_usd:
            # Funded on base — the HIP-3 enumeration cannot change the verdict,
            # so skip it. Keeps the common case at one /info call per candidate.
            return base

    if dex_names is None:
        complete = False
        dex_names = []
    for dex in dex_names:
        equity = _dex_equity_usd(info, address, dex)
        if equity is None:
            complete = False
            continue
        if best is None or equity > best:
            best = equity
        if equity >= min_usd:
            return equity

    if best is None:
        return None  # nothing readable on any clearinghouse
    if not complete:
        # Below the bar everywhere we could read, but we could not read it all.
        return None
    return best


def discover_leaders(
    client: LiquidictionClient,
    cfg: DiscoveryConfig,
    info: InfoProto | None = None,
) -> list[Trader]:
    """Pull top traders from Liquidiction, then optionally filter through
    a per-leader quality scorer (`leader_score.meets_quality`) using their
    own fill history from HL.

    The Liquidiction filters (`min_trades`, `min_volume_usd`, `min_pnl_usd`)
    are coarse — they pass leaders with high raw PnL even if that PnL came
    from a single lucky position. The score filter catches scalpers
    (low time_between_fills) and flip-floppers (low direction_consistency).

    Pass `info=None` to skip the quality scorer (legacy behavior — useful
    for tests that don't want HL fill round-trips).
    """
    candidates = client.top_traders(period=cfg.period, n=max(cfg.top_n * 4, 50))
    coarse_filtered = [
        t
        for t in candidates
        if t.trades >= cfg.min_trades
        and t.volume >= cfg.min_volume_usd
        and t.pnl >= cfg.min_pnl_usd
    ]

    # Quality filter: only enabled when info is provided AND config requests it
    score_enabled = info is not None and cfg.use_quality_filter
    selected: list[Trader] = []
    rejected_for_score: list[tuple[Trader, str]] = []

    if score_enabled:
        assert info is not None  # narrowed by score_enabled
        # Enumerated ONCE for the whole cycle: it describes the exchange, not
        # any wallet. None here means "we could not enumerate", which leaves
        # every HIP-3-funded candidate UNKNOWN rather than insolvent (INV 4).
        dex_names = hip3_dex_names(info)
        for t in coarse_filtered:
            metrics = load_metrics(
                info,
                t.address,
                lookback_hours=cfg.score_lookback_hours,
                perp_only=cfg.score_perp_only,
            )
            if metrics is None:
                rejected_for_score.append((t, "metrics_unavailable"))
                continue
            # Solvency gate (2026-08-15). A leaderboard PnL says nothing about
            # whether the wallet still HAS money — 30d rank is history, and a
            # trader who withdrew or blew up keeps their rank while trading
            # nothing. `0x166866a2` is genuinely empty on every clearinghouse
            # despite 1,375 recent fills, which is the case this catches.
            #
            # The earlier claims that `0x9551e7d4` was a "$0 equity dead slot"
            # and that "44 of the top 60 have zero perp equity" were BOTH
            # artifacts of reading base-dex equity only (INV 1) — 0x9551e7d4
            # holds $8,104 on xyz. Do not cite either; see P0c in BACKLOG.md.
            # `_perp_equity_usd` now reads every clearinghouse.
            #
            # Checked before meets_quality because it is the cheaper, more
            # decisive test: no equity means no future fills to mirror, whatever
            # the historical metrics say.
            equity = _perp_equity_usd(
                info, t.address, min_usd=cfg.min_leader_equity_usd, dex_names=dex_names
            )
            if equity is not None and equity < cfg.min_leader_equity_usd:
                rejected_for_score.append(
                    (t, f"equity=${equity:.0f} < ${cfg.min_leader_equity_usd:.0f}")
                )
                continue
            ok, reason = meets_quality(
                metrics,
                min_holding_s=cfg.min_holding_time_s,
                min_sharpe=cfg.min_sharpe,
                min_realized_pnl_usd=cfg.min_pnl_usd,
                min_direction_consistency=cfg.min_direction_consistency,
                min_trades=cfg.min_trades,
                min_perp_fraction=cfg.min_perp_fraction,
            )
            if ok:
                if cfg.use_sharpe_weighting:
                    # clip(sharpe + 1.0, 0.5, 2.0): sharpe 0 → 1.0x (current),
                    # sharpe 1.0 → 2.0x (cap), sharpe -0.5 → 0.5x (floor).
                    t.weight = max(0.5, min(2.0, metrics.realized_pnl_sharpe + 1.0))
                selected.append(t)
                if len(selected) >= cfg.top_n:
                    break
            else:
                rejected_for_score.append((t, reason))
    else:
        selected = coarse_filtered[: cfg.top_n]

    # Operator override: append `always_follow` addresses regardless of any
    # filter outcome above. If the address is in the candidates pool we use
    # the real Trader record; otherwise we synthesize a minimal one (the
    # downstream FillFollower only needs the address).
    if cfg.always_follow:
        already = {t.address.lower() for t in selected}
        by_addr = {t.address.lower(): t for t in candidates}
        for raw in cfg.always_follow:
            addr = raw.lower()
            if addr in already:
                continue
            forced = by_addr.get(addr) or Trader(
                address=addr, rank=-1, pnl=0.0, trades=0, volume=0.0
            )
            selected.append(forced)
            already.add(addr)

    # Operator-explicit weight overrides take precedence over auto-Sharpe weights.
    if cfg.leader_weights:
        weights_by_addr = {a.lower(): w for a, w in cfg.leader_weights.items()}
        for t in selected:
            override = weights_by_addr.get(t.address.lower())
            if override is not None:
                t.weight = float(override)

    if selected:
        log.info(
            "Selected %d/%d leaders (period=%s, quality_filter=%s): %s",
            len(selected),
            len(candidates),
            cfg.period,
            score_enabled,
            ", ".join(
                f"{t.address[:10]}…(rank={t.rank}, pnl=${t.pnl:.0f}, "
                f"trades={t.trades}, weight={t.weight:.2f})"
                for t in selected
            ),
        )
        if rejected_for_score:
            log.info(
                "Quality filter rejected %d candidates. First few: %s",
                len(rejected_for_score),
                ", ".join(f"{t.address[:10]}…({reason})" for t, reason in rejected_for_score[:5]),
            )
    else:
        log.warning(
            "No leaders matched filters (candidates=%d, coarse=%d, "
            "rejected_by_score=%d, min_trades=%d, min_volume=%.0f, min_pnl=%.0f)",
            len(candidates),
            len(coarse_filtered),
            len(rejected_for_score),
            cfg.min_trades,
            cfg.min_volume_usd,
            cfg.min_pnl_usd,
        )
    return selected
