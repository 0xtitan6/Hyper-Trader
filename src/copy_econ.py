"""Copy-trade economics: does a leader's edge survive OUR fee tier?

`leader_score.py` answers "is this leader good?". This module answers the
different — and, for us, decisive — question: **is this leader good enough that
copying them at our fee tier still makes money?**

Those come apart badly. A leader at a volume fee tier (or one earning maker
rebates) can run a real edge of 2 bps per dollar traded and compound it over
$2M of monthly turnover. We pay 4.5 bps taker on the base dex and cross the
spread on every mirror, so the identical flow is a **loss** for us. The
2026-08 screen of 466 leaderboard wallets found every high-PnL name failing on
exactly this: their PnL was turnover x a thin edge that our fee tier eats.

That is also why `discovery.min_trades: 50` is the wrong knob (BACKLOG P2).
It selects for trade *frequency*, which is the property most correlated with a
thin per-trade edge — the thing our fee tier cannot afford. A genuine
low-frequency candidate at 43 trades/30d was auto-rejected for being under 50
while high-turnover scalpers sailed through.

Everything here is PURE (no I/O) and is **not** imported by the live trading
path — it exists for `scripts/min_trades_analysis.py` and for tests. Nothing in
this module may place an order.

Definitions, stated explicitly because a recommendation built on them is only
as good as they are:

  turnover_usd     Sum of |px * sz| over the leader's fills in the window. Both
                   the opening and the closing fill count, because we pay fees
                   on both. So a "per dollar of turnover" rate is charged ONCE
                   per fill, not twice per round trip.
  leader_fee_bps   Their ACTUAL paid fees / turnover. Measured, not assumed —
                   this is how we read a leader's fee tier off the tape, and it
                   goes negative when they are net-earning maker rebates.
  gross_edge_bps   (realized PnL + fees they paid) / turnover. Their edge
                   BEFORE any fee, i.e. the part of their performance that is
                   actually skill and might transfer to a copier.
  net_edge_bps     gross_edge_bps - our_taker_bps. What is left after WE pay to
                   trade the same flow. This is the number that decides whether
                   copying them is profitable, and it is what `min_trades`
                   should have been filtering on all along.

INV 10 applies with full force: every figure here comes from `closedPnl`, so
it is REALIZED. A leader sitting on a large unrealized loss looks identical to
one who is flat. Callers that fetch account state must surface unrealized PnL
and leverage alongside these numbers (INV 9 — realized-fill stats alone have
produced five false positives).
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any

# Base-dex taker fee for an account at the default (no-volume-discount) tier,
# which is where this account sits. Used as the default cost of copying.
DEFAULT_TAKER_BPS = 4.5

# Fee token for base-dex perps. Outcome (HIP-4) fills settle their fee in the
# outcome token itself (observed `feeToken: "+2120"`), so those fee amounts are
# NOT dollars and must never be summed into a USD fee total.
USD_FEE_TOKENS = frozenset({"USDC", "USD"})


def _is_perp_coin(coin: str) -> bool:
    """Perp = not a HIP-4 outcome and not spot. Mirrors `leader_score._is_perp_coin`."""
    if not coin:
        return False
    is_outcome = coin.startswith("#") or coin.startswith("+")
    is_spot = coin.startswith("@") or "/" in coin
    return not (is_outcome or is_spot)


@dataclass(frozen=True)
class CopyEcon:
    """Fee-tier economics for one leader over one lookback window.

    All bps figures are per dollar of turnover. `*_known` flags exist because
    UNKNOWN is not ZERO (INV 4): a leader with no readable perp turnover must
    not be reported as "0.0 bps edge", which reads as a marginal-but-real
    leader when it actually means we measured nothing.
    """

    address: str
    lookback_hours: float
    perp_fill_count: int
    turnover_usd: float
    # Turnover normalised to a 30-day month, so windows of different lengths
    # are comparable. This is the "turnover/mo" the backlog item asks for.
    turnover_usd_per_mo: float
    taker_fill_fraction: float
    realized_pnl_usd: float
    fees_paid_usd: float
    leader_fee_bps: float
    gross_edge_bps: float
    net_edge_bps: float
    net_pnl_at_our_tier_usd: float
    our_taker_bps: float
    # False when turnover was 0 (or unreadable): every bps field is then a
    # placeholder 0.0 that means "unmeasured", never "break-even".
    econ_known: bool
    # False when any perp fill paid its fee in a non-USD token, so
    # `fees_paid_usd` (and therefore gross/net edge) understates the true cost.
    fees_all_usd: bool


def compute_copy_econ(
    address: str,
    fills: list[dict[str, Any]],
    *,
    lookback_hours: float = 720.0,
    our_taker_bps: float = DEFAULT_TAKER_BPS,
) -> CopyEcon:
    """Fee-tier economics from a leader's raw `userFillsByTime` response.

    Restricted to PERP fills: those are the only ones this bot mirrors on the
    surfaces under discussion, and outcome fills would otherwise contaminate
    the fee total with non-USD fee tokens (see `USD_FEE_TOKENS`).

    Unparseable fills are skipped rather than defaulted to zero — a fill we
    cannot read is not a fill worth $0 (INV 4).
    """
    perp_fills = 0
    taker_fills = 0
    turnover = 0.0
    realized = 0.0
    fees = 0.0
    fees_all_usd = True

    for f in fills:
        if not isinstance(f, dict):
            continue
        coin = f.get("coin", "")
        if not _is_perp_coin(coin):
            continue
        try:
            px = float(f.get("px", 0))
            sz = abs(float(f.get("sz", 0)))
        except (TypeError, ValueError):
            continue
        if px <= 0 or sz <= 0:
            continue
        perp_fills += 1
        turnover += px * sz
        if f.get("crossed") is True:
            taker_fills += 1
        with contextlib.suppress(TypeError, ValueError):
            realized += float(f.get("closedPnl", 0) or 0)
        fee_token = str(f.get("feeToken") or "USDC").upper()
        try:
            fee = float(f.get("fee", 0) or 0)
        except (TypeError, ValueError):
            fee = 0.0
        if fee_token in USD_FEE_TOKENS:
            fees += fee
        elif fee != 0:
            # A perp fill charging a non-USD fee token. Don't guess a price for
            # it; record that the fee total is incomplete so the caller can
            # discount the edge figures instead of trusting them.
            fees_all_usd = False

    if turnover <= 0:
        return CopyEcon(
            address=address.lower(),
            lookback_hours=lookback_hours,
            perp_fill_count=perp_fills,
            turnover_usd=0.0,
            turnover_usd_per_mo=0.0,
            taker_fill_fraction=0.0,
            realized_pnl_usd=realized,
            fees_paid_usd=fees,
            leader_fee_bps=0.0,
            gross_edge_bps=0.0,
            net_edge_bps=0.0,
            net_pnl_at_our_tier_usd=0.0,
            our_taker_bps=our_taker_bps,
            econ_known=False,
            fees_all_usd=fees_all_usd,
        )

    # Their edge BEFORE fees: realized PnL on HL is already net of the fees
    # they paid, so add those back to recover the pre-fee number.
    gross_pnl = realized + fees
    gross_edge_bps = gross_pnl / turnover * 10_000.0
    our_cost_usd = turnover * our_taker_bps / 10_000.0
    scale = (720.0 / lookback_hours) if lookback_hours > 0 else 1.0

    return CopyEcon(
        address=address.lower(),
        lookback_hours=lookback_hours,
        perp_fill_count=perp_fills,
        turnover_usd=turnover,
        turnover_usd_per_mo=turnover * scale,
        taker_fill_fraction=taker_fills / perp_fills if perp_fills else 0.0,
        realized_pnl_usd=realized,
        fees_paid_usd=fees,
        leader_fee_bps=fees / turnover * 10_000.0,
        gross_edge_bps=gross_edge_bps,
        net_edge_bps=gross_edge_bps - our_taker_bps,
        net_pnl_at_our_tier_usd=gross_pnl - our_cost_usd,
        our_taker_bps=our_taker_bps,
        econ_known=True,
        fees_all_usd=fees_all_usd,
    )


def passes_fee_tier(econ: CopyEcon, *, min_net_edge_bps: float = 0.0) -> tuple[bool, str]:
    """Fee-tier screen: would copying this leader's flow make money at OUR tier?

    Returns `(ok, reason)`, with `reason` empty when ok — the same shape as
    `leader_score.meets_quality` so the two compose in a screening pipeline.

    INV 4: unmeasured economics is UNKNOWN, not a pass and not a fail. We
    return False with an explicit `econ_unknown` reason, so the caller gets a
    greppable rejection rather than a leader silently admitted on no evidence
    (INV 5 — every skip path gets its own reason).
    """
    if not econ.econ_known:
        return False, "econ_unknown (no readable perp turnover)"
    if econ.net_edge_bps < min_net_edge_bps:
        return False, (
            f"net_edge={econ.net_edge_bps:.2f}bps < {min_net_edge_bps:.2f}bps "
            f"(gross={econ.gross_edge_bps:.2f} - our_taker={econ.our_taker_bps:.2f})"
        )
    return True, ""
