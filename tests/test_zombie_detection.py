"""Tests for the three defects found after the 2026-09-16 zombie incident.

Background: the engine's working directory was deleted out from under the
running process. It stayed alive for 2.5 days — `systemctl` reported
`active (running)`, the watchdog stayed silent — while every API call failed
and it placed no orders. Nothing caught it; a human asked three days later.

Each test below pins one of the three reasons that was possible. They are
cheap, and each one failed before its fix.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.leader_reconcile import LeaderReconciler

# --- 1. the kill switch must cover EVERY order path ------------------------


def _reconciler_with_exchange(tmp_path: Path, exchange, kill_file: str):
    """A reconciler wired for auto-close, with a configurable KILL path."""
    info = MagicMock()
    info.all_mids.return_value = {"ZEC": "1580.0"}
    market_meta = MagicMock()
    market_meta.round_price.side_effect = lambda px, coin: round(px, 1)
    return LeaderReconciler(
        info=info,
        state=MagicMock(),
        journal=MagicMock(),
        alerter=MagicMock(),
        exchange=exchange,
        market_meta=market_meta,
        auto_close=True,
        slippage_bps=50.0,
        kill_switch_file=kill_file,
    )


def test_auto_close_is_blocked_by_kill_switch(tmp_path: Path) -> None:
    """KILL present => no order, on the reconciler's path too.

    This is the one that mattered. `KILL` is checked in `mirror._risk_check`,
    which gates mirroring. `_submit_close` calls `exchange.order()` directly,
    so before the fix an operator could touch ./KILL, believe all trading was
    stopped, and still have a path live that flattens positions.
    """
    kill = tmp_path / "KILL"
    kill.touch()
    exchange = MagicMock()

    r = _reconciler_with_exchange(tmp_path, exchange, str(kill))
    r._submit_close("ZEC", 0.21, 1121.0, reason="leader_flat")

    exchange.order.assert_not_called()


def test_auto_close_proceeds_when_kill_absent(tmp_path: Path) -> None:
    """The gate must not be a mute button — absent KILL still closes."""
    exchange = MagicMock()
    exchange.order.return_value = {"status": "ok"}

    r = _reconciler_with_exchange(tmp_path, exchange, str(tmp_path / "KILL"))
    r._submit_close("ZEC", 0.21, 1121.0, reason="leader_flat")

    exchange.order.assert_called_once()
    kwargs = exchange.order.call_args.kwargs
    assert kwargs["reduce_only"] is True


def test_kill_gate_precedes_the_mid_fetch(tmp_path: Path) -> None:
    """With KILL set we must not even price the close.

    Ordering matters: `_fetch_mid` is what accidentally blocked HIP-3
    auto-closes, and someone will eventually fix that. The kill check has to
    sit in front of it so the guard survives that fix.
    """
    kill = tmp_path / "KILL"
    kill.touch()
    r = _reconciler_with_exchange(tmp_path, MagicMock(), str(kill))

    r._submit_close("xyz:TSLA", 0.179, 367.0, reason="leader_flat")

    r.info.all_mids.assert_not_called()


# --- 2. tier-1 must bound its liveness proof by recency --------------------


@pytest.fixture()
def tier1(monkeypatch, tmp_path: Path):
    """tier1_check with a scratch ROOT and every probe but the log forced healthy."""
    from scripts import status

    (tmp_path / "state").mkdir()
    monkeypatch.setattr(status, "ROOT", tmp_path)

    def fake_sh(cmd: str, timeout: int = 30) -> str:
        if "is-active" in cmd:
            return "active"
        if "wc -l" in cmd:          # ps | grep '[s]rc.main' | wc -l
            return "1"
        if "Following" in cmd:
            return "2026-09-16 12:01:00 INFO Following 2 leaders."
        if "df" in cmd:
            return "99999999"
        return "tier=OK"

    monkeypatch.setattr(status, "sh", fake_sh)
    return status


def test_stale_log_escalates_even_though_following_line_exists(tier1, tmp_path):
    """The zombie's exact signature: startup line present, nothing written since.

    `grep 'Following N leaders'` matches a STARTUP line that persists in the log
    forever. It proves the engine once began following — not that it is still
    working. Before the recency bound, this state reported HEALTHY indefinitely.
    """
    log = tmp_path / "state" / "main.log"
    log.write_text("2026-09-16 12:01:00 INFO Following 2 leaders.\n")
    stale = time.time() - (tier1.LOG_STALE_S + 600)
    import os

    os.utime(log, (stale, stale))

    code, reasons = tier1.tier1_check()

    assert code == 1
    assert any("stale" in r for r in reasons), reasons


def test_fresh_log_stays_healthy(tier1, tmp_path):
    """Guard against the opposite failure: a tier-1 that cries wolf every 15min
    is worse than no tier-1, because it trains the operator to ignore it."""
    log = tmp_path / "state" / "main.log"
    log.write_text("2026-09-19 01:26:00 INFO Following 2 leaders.\n")

    code, reasons = tier1.tier1_check()

    assert code == 0, reasons


def test_missing_log_escalates(tier1, tmp_path):
    """An unlinked log is the literal 2026-09-16 case — the file was deleted
    while the process held the inode open."""
    code, reasons = tier1.tier1_check()

    assert code == 1
    assert any("main.log" in r for r in reasons), reasons


def test_rotation_does_not_false_escalate(tier1, tmp_path):
    """logrotate briefly leaves the freshest writes in main.log.1. This has
    broken the sibling `Following` lookup twice already (2026-09-11)."""
    (tmp_path / "state" / "main.log").write_text("")
    old = time.time() - (tier1.LOG_STALE_S + 600)
    import os

    os.utime(tmp_path / "state" / "main.log", (old, old))
    (tmp_path / "state" / "main.log.1").write_text("fresh writes landed here\n")

    code, reasons = tier1.tier1_check()

    assert code == 0, reasons


# --- 3. the watchdog must watch a file that exists -------------------------


def test_watchdog_watches_the_real_log() -> None:
    """`run.log` never existed on this box, so the freshness check — the only
    one that detects "alive but not working" — took its else-branch on cycle
    one, fired a single alert, latched log_fresh=False, and went quiet for a
    month. Pin the filename against the engine's actual systemd output path.
    """
    import inspect

    from scripts import watchdog

    # Strip comments — the fix's own rationale comment names the old path.
    src = inspect.getsource(watchdog.check_once)
    code_only = "\n".join(
        ln for ln in src.splitlines() if not ln.strip().startswith("#")
    )
    assert '"state" / "main.log"' in code_only
    assert "run.log" not in code_only
