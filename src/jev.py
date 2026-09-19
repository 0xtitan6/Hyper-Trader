"""TypeSafe (Jev) System One judgments for the Outcome LP farm.

The farm allocates capital by exact arithmetic (`pool / depth`). That arithmetic
is blind to the one thing that actually loses money: informed flow. Quote rewards
are safe — an order that never fills carries no risk — but a ONE-SIDED fill leaves
us directional, and adverse selection means the side that fills is
disproportionately the side about to be wrong.

That judgment is fast, repeated, and made over structured state, which is System
One shape. Jev returns numbers we branch on in code rather than prose we parse.

Questions are ATOMIC on purpose (TypeSafe's own guidance): "is this market worth
quoting?" would bundle reward economics we compute exactly with flow toxicity we
cannot compute at all. We ask only the part arithmetic cannot answer.

SHADOW MODE FIRST. Nothing here changes allocation until `informed_flow` has been
shown to predict which fills actually went one-sided. A plausible-sounding gate
that quietly suppresses profitable quoting is worse than no gate.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import requests

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
ENV = Path("/home/ec2-user/.config/hyper-trader/copytrader.env")

log = logging.getLogger(__name__)


def api_key() -> str | None:
    try:
        for line in ENV.read_text().splitlines():
            if line.startswith("TYPESAFE_API_KEY="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return None


QUESTIONS: dict[str, Any] = {
    "informed_flow": {
        "type": "noul",
        "instructions": (
            "Does recent order flow in this book indicate informed trading — "
            "participants acting on information not yet reflected in the price?"
        ),
        "criteria": {
            "true": "One-directional flow, accelerating, price moving with it — consistent with someone knowing something",
            "false": "Two-sided or balanced flow, price stable, consistent with ordinary liquidity taking",
        },
    },
    "imminent_repricing": {
        "type": "noul",
        "instructions": "Is this market likely to reprice sharply within the next hour?",
        "criteria": {
            "true": "Event is imminent or news is likely to land within the hour",
            "false": "Stable period, no scheduled catalyst inside the hour",
        },
    },
    "fill_asymmetry": {
        "type": "score",
        "instructions": (
            "If we rest bids on BOTH legs of this surface, how likely is it that only "
            "one side fills, leaving us directional rather than hedged?"
        ),
        "criteria": [
            "Both sides likely to fill (stays hedged)",
            "Mixed",
            "Only one side likely to fill (ends up directional)",
        ],
    },
}


def build_state(
    market_name: str,
    outcome_name: str,
    legs: dict[str, dict[str, float]],
    trades: list[dict] | None,
    ends_in_h: float | None,
) -> str:
    """One paragraph of plain text. Flow data matters most.

    A book snapshot alone gives `fill_asymmetry` confidence 0.00 — measured
    2026-09-19. The model cannot judge fill dynamics without knowing who is
    hitting what, so recent trades are included whenever available.
    """
    parts = [f"Prediction market: {market_name}. Scored outcome: {outcome_name}."]
    if ends_in_h is not None:
        parts.append(f"Incentive window ends in {ends_in_h:.1f}h.")
    for name, d in legs.items():
        parts.append(
            f"{name} leg: mid {d['mid']:.4f}, top-5 bid depth ${d['depth']:.0f}, "
            f"spread {d['spread_bp']:.0f}bp."
        )
    if trades:
        buys = sum(1 for t in trades if t.get("side") == "B")
        ntl = sum(float(t.get("px", 0)) * float(t.get("sz", 0)) for t in trades)
        first, last = float(trades[-1].get("px", 0)), float(trades[0].get("px", 0))
        parts.append(
            f"Last {len(trades)} trades: {buys} buys / {len(trades) - buys} sells, "
            f"${ntl:.0f} notional, price {first:.4f} -> {last:.4f}."
        )
    else:
        parts.append("No recent trade data available for this leg.")
    parts.append("We rest post-only bids on both legs to earn liquidity rewards.")
    return " ".join(parts)


def evaluate(state: str, key: str, timeout: float = 45.0) -> dict[str, Any] | None:
    """Return the `answers` dict, or None on any failure.

    Fails OPEN by design: the arithmetic allocation is the default and Jev is an
    override. An API hiccup must never stop us earning the safe 40% quote reward.
    """
    try:
        r = requests.post(
            ENDPOINT,
            headers={"Authorization": f"Bearer {key}"},
            json={"model": MODEL, "state": state, "questions": QUESTIONS},
            timeout=timeout,
        )
        if r.status_code != 200:
            log.warning("jev: http %s %s", r.status_code, r.text[:200])
            return None
        return r.json().get("answers")
    except (requests.RequestException, ValueError):
        log.warning("jev: call failed", exc_info=True)
        return None


def log_shadow(path: Path, market: str, outcome_id: int, state: str,
               answers: dict[str, Any], alloc_usd: float) -> None:
    """Append one observation. `alloc_usd` is what arithmetic decided, unchanged —
    the whole point of shadow mode is to compare later, not to act now."""
    rec = {
        "ts": time.time(),
        "market": market,
        "outcome_id": outcome_id,
        "alloc_usd": alloc_usd,
        "informed_flow": (answers.get("informed_flow") or {}).get("noul"),
        "imminent_repricing": (answers.get("imminent_repricing") or {}).get("noul"),
        "fill_asymmetry": (answers.get("fill_asymmetry") or {}).get("score"),
        "fill_asymmetry_conf": (answers.get("fill_asymmetry") or {}).get("confidence"),
        "state": state,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(rec) + "\n")
