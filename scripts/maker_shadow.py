"""Live maker-shadow harness.

Runs the OutcomeMaker's *real* quoting logic (dry_run=True) against a live
HL trades + l2Book feed, forwards every intended quote into the pure-logic
ShadowSimulator (src/maker_shadow.py), and prints a REALIZED-only report
with a plain YES/NO on whether the sample supports going live.

This is the harness that gates any capital going to the maker (BACKLOG P0).
It submits nothing.

Run:
    .venv/bin/python scripts/maker_shadow.py \\
        --coin '#20' --expiry 2026-05-06T06:00:00+00:00 \\
        --minutes 30 --out state/maker_shadow.jsonl

Live-wire is intentionally thin — the fill math, mark-out timing, fee
tables, and significance test are all in src/maker_shadow.py and covered
by tests/test_maker_shadow.py. The script's own job is only to plumb
events; don't put business logic here.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from hyperliquid.info import Info

from src.hl_outcome import register_outcome_assets
from src.log import setup_logging
from src.maker import MakerConfig, OutcomeMaker
from src.maker_shadow import ShadowSimulator
from src.market_meta import MarketMeta

log = logging.getLogger("maker_shadow")

HL_API = "https://api.hyperliquid.xyz"


def _is_hip3(coin: str) -> bool:
    return ":" in coin  # e.g. "xyz:SMCI", "para:IREN"


def main() -> int:
    p = argparse.ArgumentParser(prog="maker-shadow")
    p.add_argument("--coin", required=True)
    p.add_argument("--expiry", required=True, help="ISO8601 or 'never'")
    p.add_argument("--minutes", type=int, default=30, help="run duration")
    p.add_argument("--quote-size", type=float, default=1.0)
    p.add_argument("--min-spread-bps", type=float, default=30.0)
    p.add_argument("--max-position", type=float, default=20.0)
    p.add_argument("--out", required=True, help="JSONL output path")
    args = p.parse_args()

    setup_logging(level="INFO", json_mode=False)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    info = Info(HL_API, skip_ws=False)
    register_outcome_assets(info)
    market_meta = MarketMeta(info)
    market_meta.load()

    # Journal writes are directed at a shadow-only file — never touching the
    # live trader's journal.
    from src.journal import Journal

    shadow_journal = Journal(str(out_path))

    if args.expiry.lower() == "never":
        expiry_ts = int(time.time()) + args.minutes * 60 + 3600
    else:
        expiry_ts = int(datetime.fromisoformat(args.expiry).timestamp())

    mk_cfg = MakerConfig(
        coin=args.coin,
        expiry_ts=expiry_ts,
        quote_size_shares=args.quote_size,
        min_spread_bps=args.min_spread_bps,
        max_position_shares=args.max_position,
    )
    # dry_run=True is the ONLY safe mode for a shadow harness.
    maker = OutcomeMaker(
        info=info,
        exchange=_DevNullExchange(),
        market_meta=market_meta,
        journal=shadow_journal,
        config=mk_cfg,
        dry_run=True,
    )

    sim = ShadowSimulator(coin=args.coin, is_hip3=_is_hip3(args.coin))
    sim.set_inventory_cap(mk_cfg.max_position_shares)

    def on_trades_msg(msg: dict) -> None:
        for t in msg.get("data", []):
            try:
                ts = float(t.get("time", 0)) / 1000.0
                # HL trades msg: side "B" = buy aggressor
                sim.on_trade(
                    ts=ts,
                    aggressor_side=t.get("side", ""),
                    px=float(t.get("px", 0)),
                    size=float(t.get("sz", 0)),
                )
            except (KeyError, TypeError, ValueError):
                continue

    def on_l2_msg(msg: dict) -> None:
        d = msg.get("data") or {}
        levels = d.get("levels") or []
        if len(levels) < 2 or not levels[0] or not levels[1]:
            return
        try:
            best_bid = float(levels[0][0]["px"])
            best_ask = float(levels[1][0]["px"])
        except (KeyError, TypeError, ValueError, IndexError):
            return
        mid = (best_bid + best_ask) / 2
        ts = float(d.get("time", time.time() * 1000)) / 1000.0
        sim.on_mid(ts, mid)

    info.subscribe({"type": "trades", "coin": args.coin}, on_trades_msg)
    info.subscribe({"type": "l2Book", "coin": args.coin}, on_l2_msg)

    stop_at = time.time() + args.minutes * 60
    last_reported_quotes: tuple[float | None, float | None] = (None, None)
    log.info(
        "shadow: coin=%s duration=%dmin surface=%s fee=%.2fbps",
        args.coin,
        args.minutes,
        "hip3" if sim.is_hip3 else "base",
        sim.fee_bps(),
    )

    while time.time() < stop_at:
        try:
            maker.tick()
        except Exception:
            log.exception("shadow tick error")
        # After tick(), maker._open holds the intended quotes; forward them
        # into the simulator. We ignore private state discipline here on
        # purpose — the shadow needs to see exactly what live would submit.
        bid_px = maker._open.bid_px if maker._open.bid_oid is not None else 0.0
        ask_px = maker._open.ask_px if maker._open.ask_oid is not None else 0.0
        now = time.time()
        # Queue-ahead: pessimistic = full displayed size at that price level.
        # We look it up from the last-seen l2 snapshot via a fresh info.post.
        if bid_px > 0 and bid_px != last_reported_quotes[0]:
            qa = _depth_at(info, args.coin, "B", bid_px)
            sim.record_quote(now, "B", bid_px, mk_cfg.quote_size_shares, qa)
        elif bid_px == 0 and last_reported_quotes[0]:
            sim.cancel_side(now, "B")
        if ask_px > 0 and ask_px != last_reported_quotes[1]:
            qa = _depth_at(info, args.coin, "A", ask_px)
            sim.record_quote(now, "A", ask_px, mk_cfg.quote_size_shares, qa)
        elif ask_px == 0 and last_reported_quotes[1]:
            sim.cancel_side(now, "A")
        last_reported_quotes = (bid_px or None, ask_px or None)

        time.sleep(mk_cfg.refresh_interval_s)

    rep = sim.report()
    log.info("shadow report: %s", json.dumps(rep, indent=2, default=float))
    with out_path.open("a") as fh:
        fh.write(json.dumps({"type": "shadow_report", **rep}) + "\n")
    return 0


def _depth_at(info: Info, coin: str, side: str, px: float) -> float:
    """Displayed size at `px` on `side` right now. Best-effort — if the
    l2Book fetch fails, assume full 1.0 unit ahead (still pessimistic)."""
    try:
        book = info.post("/info", {"type": "l2Book", "coin": coin})
    except Exception:
        return 1.0
    levels = (book or {}).get("levels") or []
    if len(levels) < 2:
        return 1.0
    side_levels = levels[0] if side == "B" else levels[1]
    for lv in side_levels:
        try:
            if abs(float(lv["px"]) - px) < 1e-9:
                return float(lv["sz"])
        except (KeyError, TypeError, ValueError):
            continue
    return 1.0


class _DevNullExchange:
    """Stub exchange that refuses to submit anything. Belt-and-suspenders on
    top of dry_run=True — if any code path forgets the flag, this raises."""

    def order(self, *a, **kw):  # pragma: no cover - safety net
        raise RuntimeError("shadow harness must not place orders")

    def cancel(self, *a, **kw):  # pragma: no cover - safety net
        raise RuntimeError("shadow harness must not place orders")


if __name__ == "__main__":
    raise SystemExit(main())
