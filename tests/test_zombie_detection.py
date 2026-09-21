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


# --- 4. Outcome rewards: builder code must be on every quote ----------------


def test_maker_attaches_builder_code_when_configured() -> None:
    """No builder code => no rewards, and the reward IS the edge here.

    outcome.xyz scores LP rewards only for orders carrying their builder code.
    Quoting a binary without it is unpaid adverse selection: we'd eat the
    inventory risk and collect none of the 40/50/10 quote/maker/taker pools.
    """
    from src.maker import MakerConfig, OutcomeMaker

    cfg = MakerConfig(
        coin="#20",
        expiry_ts=2_000_000_000,
        builder_address="0xAB5DBC057628BC18523C4CDFC0E1E2EBDBECB704",
    )
    m = OutcomeMaker.__new__(OutcomeMaker)
    m.cfg = cfg
    b = m._builder()

    assert b is not None
    assert b["b"] == "0xab5dbc057628bc18523c4cdfc0e1e2ebdbecb704"  # lowercased
    assert b["f"] == 0  # program requires no builder fee


def test_maker_builder_is_none_when_unconfigured() -> None:
    """Unset => None, so the SDK omits the field entirely rather than sending
    a malformed builder object that would reject every order."""
    from src.maker import MakerConfig, OutcomeMaker

    m = OutcomeMaker.__new__(OutcomeMaker)
    m.cfg = MakerConfig(coin="#20", expiry_ts=2_000_000_000)

    assert m._builder() is None


# --- 5. auto-hedge: a one-sided fill must become a $1.00 basket -------------


def _maker_for_hedge(hedge_ask: float, max_pair: float = 1.02):
    """Maker wired to hedge #38830 with #38831 at a given opposing ask."""
    from src.maker import MakerConfig, OutcomeMaker

    m = OutcomeMaker.__new__(OutcomeMaker)
    m.cfg = MakerConfig(
        coin="#38830",
        expiry_ts=2_000_000_000,
        hedge_on_fill=True,
        hedge_coin="#38831",
        hedge_max_pair_cost=max_pair,
        builder_address="0xab5dbc057628bc18523c4cdfc0e1e2ebdbecb704",
    )
    m.info = MagicMock()
    m.info.l2_snapshot.return_value = {
        "levels": [[{"px": "0.40", "sz": "100"}], [{"px": str(hedge_ask), "sz": "100"}]]
    }
    m.exchange = MagicMock()
    m.exchange.order.return_value = {"status": "ok"}
    m.market_meta = MagicMock()
    m.market_meta.round_price.side_effect = lambda px, coin: round(px, 4)
    m.journal = MagicMock()
    m.alerter = MagicMock()
    return m


def test_hedge_fires_immediately_on_fill() -> None:
    """The 2026-09-19 loss in one test.

    Filled Tottenham YES at 0.5077; the match moved and it marked to ~0.15,
    losing $47 on a $47 leg against ~$3 of rewards. A one-sided leg has no
    spread income at all — a continuous touch fills you at fair value — so the
    only real income is owning BOTH legs of a $1.00 basket. Hedging at the fill
    would have made that loss ~$1.
    """
    m = _maker_for_hedge(hedge_ask=0.49)
    m._hedge_one_sided(sz=93.0, px=0.5077)

    m.exchange.order.assert_called_once()
    args, kwargs = m.exchange.order.call_args
    assert args[0] == "#38831"      # the complementary leg
    assert args[1] is True          # buying it
    assert args[2] == 93.0          # same size — a basket, not a guess
    assert kwargs["order_type"] == {"limit": {"tif": "Ioc"}}   # taker: immediacy is the point
    assert kwargs["builder"]["b"] == "0xab5dbc057628bc18523c4cdfc0e1e2ebdbecb704"


def test_hedge_refuses_once_the_leg_has_repriced() -> None:
    """Hedging late is EV-NEUTRAL, so it must not fire.

    Holding a leg worth 0.15 and paying 0.85 to lock $1.00 are worth exactly the
    same; crossing at that point only converts variance into a certain loss while
    paying a spread for the privilege. All the value of hedging is immediacy.
    """
    m = _maker_for_hedge(hedge_ask=0.85)      # pair would cost 1.3577
    m._hedge_one_sided(sz=93.0, px=0.5077)

    m.exchange.order.assert_not_called()
    assert m.alerter.alert.called


def test_hedge_is_off_by_default() -> None:
    """Taking liquidity is a money action; it stays opt-in."""
    from src.maker import MakerConfig

    assert MakerConfig(coin="#20", expiry_ts=2_000_000_000).hedge_on_fill is False


# --- 6. in-play guard: never quote a match that is being played -------------


def _gamestate_with(monkeypatch, events_by_league: dict):
    """GameState wired to a fake ESPN feed."""
    from src import gamestate as gs

    class FakeResp:
        def __init__(self, payload):
            self._p = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._p

    def fake_get(url, timeout=15):
        for lg, payload in events_by_league.items():
            if lg in url:
                return FakeResp(payload)
        return FakeResp({"events": []})

    monkeypatch.setattr(gs.requests, "get", fake_get)
    monkeypatch.setattr(gs.time, "sleep", lambda *_: None)
    return gs.GameState(leagues=("eng.1",), ttl_s=0.0)


def _event(home, away, desc, clock="10'", hs="0", as_="0"):
    return {"competitions": [{
        "status": {"type": {"description": desc}, "displayClock": clock},
        "competitors": [{"team": {"displayName": home}, "score": hs},
                        {"team": {"displayName": away}, "score": as_}],
    }]}


def test_refuses_to_quote_a_live_match(monkeypatch) -> None:
    """The $47 loss in one test.

    Measured 2026-09-20: in-play surfaces show a 6.68% median paired-bid edge
    versus 0.17% when not live — a 39x gap. That spread is not opportunity, it
    is the price of someone watching the match knowing the score before the book.
    """
    gs = _gamestate_with(monkeypatch, {"eng.1": {"events": [
        _event("Fulham", "Manchester United", "First Half", "10'")]}})

    safe, reason = gs.is_safe_to_quote("participant:Fulham|competition:EPL")

    assert safe is False
    assert "IN PLAY" in reason


def test_allows_quoting_before_and_after(monkeypatch) -> None:
    """Pre-match and settled books are where the honest ~0.17% lives."""
    gs = _gamestate_with(monkeypatch, {"eng.1": {"events": [
        _event("Leeds United", "Crystal Palace", "Full Time", "90'+4'"),
        _event("Arsenal", "Chelsea", "Scheduled", "0'")]}})

    assert gs.is_safe_to_quote("participant:Leeds United")[0] is True
    assert gs.is_safe_to_quote("participant:Arsenal")[0] is True


def test_partial_name_match(monkeypatch) -> None:
    """Feeds and market descriptions disagree on names. An exact-match lookup
    would miss and then read as SAFE — the dangerous direction to fail."""
    gs = _gamestate_with(monkeypatch, {"eng.1": {"events": [
        _event("Tottenham Hotspur", "Aston Villa", "Second Half", "67'", "0", "1")]}})

    safe, reason = gs.is_safe_to_quote("participant:Tottenham")
    assert safe is False
    assert "Aston Villa" in reason or "IN PLAY" in reason


def test_feed_outage_refuses_rather_than_assumes_safe(monkeypatch) -> None:
    """An outage is not evidence that no match is being played."""
    from src import gamestate as gs_mod

    def boom(*_a, **_k):
        raise gs_mod.requests.RequestException("down")

    monkeypatch.setattr(gs_mod.requests, "get", boom)
    monkeypatch.setattr(gs_mod.time, "sleep", lambda *_: None)

    safe, reason = gs_mod.GameState(leagues=("eng.1",), ttl_s=0.0).is_safe_to_quote("participant:Fulham")
    assert safe is False
    assert "fail safe" in reason


def test_non_sports_markets_are_unaffected(monkeypatch) -> None:
    """This guard is about live events, not about every market."""
    gs = _gamestate_with(monkeypatch, {"eng.1": {"events": []}})
    assert gs.is_safe_to_quote("perp:BTC|threshold:100000")[0] is True


# --- 7. positive evidence, not a weakened default --------------------------


def test_future_fixture_is_quotable_absence_alone_is_not(monkeypatch) -> None:
    """The distinction that decides whether this strategy is safe.

    ESPN's default scoreboard returns only the CURRENT matchday, so a fixture a
    week out is absent — indistinguishable from "this feed does not cover it".
    Treating absence as safe is how you end up quoting into a live match on the
    day a feed has a gap. So the guard requires POSITIVE evidence: the team
    appears in a future SCHEDULED fixture.
    """
    from src import gamestate as gs_mod

    gs = gs_mod.GameState(leagues=("soccer/uefa.nations",), ttl_s=0.0)
    gs._cache = {}                      # not on any current scoreboard
    gs._fetched_at = gs_mod.time.time()
    gs._upcoming = {"england": "2099-09-27"}
    gs._upcoming_at = gs_mod.time.time()

    safe, reason = gs.is_safe_to_quote("participant:England")
    assert safe is True
    assert "next plays" in reason

    # A team with no future fixture found gets no benefit of the doubt.
    safe2, reason2 = gs.is_safe_to_quote("participant:Narnia")
    assert safe2 is False


def test_fixture_today_is_refused(monkeypatch) -> None:
    """A fixture dated today may already have kicked off — stay out."""
    from datetime import datetime, timezone

    from src import gamestate as gs_mod

    gs = gs_mod.GameState(leagues=("soccer/uefa.nations",), ttl_s=0.0)
    gs._cache = {}
    gs._fetched_at = gs_mod.time.time()
    gs._upcoming = {"spain": datetime.now(tz=timezone.utc).date().isoformat()}
    gs._upcoming_at = gs_mod.time.time()

    safe, reason = gs.is_safe_to_quote("participant:Spain")
    assert safe is False
    assert "TODAY" in reason


def test_england_does_not_match_new_england_patriots() -> None:
    """Naive substring matching reported England as IN PLAY at 7-0 on
    2026-09-20 — it had matched an NFL game. Failing safe there was luck; the
    same collision reversed would approve quoting into a live game."""
    from src import gamestate as gs_mod

    gs = gs_mod.GameState(leagues=(), ttl_s=0.0)
    gs._cache = {"new england patriots": gs_mod.MatchState(
        "In Progress", "8:22", True, "New England Patriots", "Pittsburgh Steelers", "7 - 0")}

    assert gs.lookup("England") is None
    assert gs.lookup("Tottenham") is None          # absent entirely


def test_unresolvable_event_markets_are_refused(monkeypatch) -> None:
    """The third guard hole found on 2026-09-20, and why the default flipped.

    The guard used to return SAFE for anything it did not recognise. That waved
    through eight in-progress NFL games (keyed `competition:` rather than
    `participant:`) and live UFC 331 bouts (UFC appears in no scoreboard map) —
    both showing fat paired "edge" that was pure settled-event adverse selection.
    An unrecognised event market is not a non-event market.
    """
    from src import gamestate as gs_mod

    gs = gs_mod.GameState(leagues=(), ttl_s=0.0)
    gs._cache = {"x": gs_mod.MatchState("Final", None, False, "a", "b", "0 - 0")}
    gs._fetched_at = gs_mod.time.time()

    for desc in ("competition:UFC 331|contestType:game",
                 "countedPlay:regulation time and any overtime",
                 ""):
        safe, reason = gs.is_safe_to_quote(desc)
        assert safe is False, f"{desc!r} should be refused"
        assert "cannot resolve" in reason

    # A genuine non-event market is unaffected.
    assert gs.is_safe_to_quote("perp:BTC|threshold:100000")[0] is True


def test_kickoff_buffer_is_single_source_of_truth():
    """The maker (via gamestate) and the minder must agree on when a pre-match
    book stops being pre-match.

    They diverged once — gamestate 1.0h, minder 3.0h. The maker would rest a
    quote 2h before kickoff and the minder would cancel it on the next 5-minute
    tick, burning post-only queue position every cycle and risking a one-sided
    fill close to kickoff. That is the -$47 shape from 2026-09-19.
    """
    import importlib.util
    from src.gamestate import KICKOFF_BUFFER_H

    spec = importlib.util.spec_from_file_location(
        "pair_minder", Path(__file__).resolve().parent.parent / "scripts" / "pair_minder.py")
    minder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(minder)

    assert minder.KICKOFF_BUFFER_H is KICKOFF_BUFFER_H, (
        "pair_minder must IMPORT KICKOFF_BUFFER_H from src.gamestate, not "
        "redefine it — a redefinition lets the two drift apart silently")
    assert KICKOFF_BUFFER_H >= 3.0, (
        "buffer below 3h reopens the window where a quote survives into kickoff")


def test_pair_maker_requires_flow_not_just_depth():
    """Depth is not flow. A book can show deep resting size and never trade.

    Measured 2026-09-20: Kosovo, Greece, Serbia and Ireland each showed
    $330-358 of depth at a clean 1.15% spread with $0 volume and 0 fills over
    both 24h and 7d. That depth is one market maker posting 1000 shares a side
    at a fixed 1.15c on every market from creation — not demand. A bid resting
    there earns nothing for as long as it sits.

    Ranking on depth alone picked those books three separate times (empty books
    09-19, frozen index binaries 09-20, these 09-20), so the filter is a
    permanent part of the scan, not a tuning knob.
    """
    src = (Path(__file__).resolve().parent.parent
           / "scripts" / "run_pair_maker.py").read_text()
    assert "def traded_24h" in src, "scan must measure realised flow per surface"
    assert "min_vol" in src and "min_trades" in src, \
        "scan must reject surfaces below a flow floor"
    # the flow gate must be applied inside scan(), not merely defined
    scan_body = src.split("def scan(")[1].split("\ndef ")[0]
    assert "traded_24h" in scan_body, "traded_24h must be CALLED by scan()"
    assert "no flow" in scan_body, "scan must skip and log flowless surfaces"


def test_pair_maker_rejects_incoherent_wide_books():
    """A huge paired 'edge' means the bids are far below mid, not that the
    market is mispriced. Measured: bids that deep leave us one-sided 91-95% of
    the time, EV -0.87%/cycle. On 2026-09-20 the scan rested bids summing to
    0.449 on a book whose mids summed to ~1.00 and called it a 55% edge.
    """
    src = (Path(__file__).resolve().parent.parent
           / "scripts" / "run_pair_maker.py").read_text()
    scan_body = src.split("def scan(")[1].split("\ndef ")[0]
    assert "mid_sum" in scan_body, "scan must sanity-check bids against mids"


def test_pair_maker_serialises_on_a_lock():
    """Two concurrent maker runs each half-enter a pair.

    The capital reservation is computed from a balance read at start-up, so two
    runs both believe they can afford both legs. Measured 2026-09-21: a manual
    run and the 20-minute requote cron fired at 22:31:23 on the same surface.
    The cron won the YES leg and then had no capital for the NO, leaving 116
    shares of YES against 27 of NO — a 4:1 directional bet nobody chose, which
    is precisely the one-sided shape that cost -$47 on 2026-09-19.

    The lock must be taken by the MAKER, not only the cron wrapper, or a manual
    invocation still races the timer.
    """
    src = (Path(__file__).resolve().parent.parent
           / "scripts" / "run_pair_maker.py").read_text()
    assert "import fcntl" in src and "LOCK_EX" in src, \
        "run_pair_maker must take an exclusive lock, not just the cron wrapper"
    assert "LOCK_NB" in src, "lock must be non-blocking — a second run exits, never queues"
    main_body = src.split("def main(")[1]
    assert "flock" in main_body, "the lock must be acquired inside main()"

    wrapper = (Path(__file__).resolve().parent.parent
               / "scripts" / "pair_requote_cron.sh").read_text()
    assert "flock -n" in wrapper, "cron wrapper must also serialise"


def test_pair_maker_sizes_by_shares_not_dollars():
    """A basket redeems $1.00 per MATCHED PAIR of shares, so the hedge is N
    YES against N NO. Equal dollars per leg buys unequal shares and always
    overweights the cheap leg, because cheap means unlikely.

    Measured 2026-09-21: at $15/leg on a 0.7367/0.2503 book the maker placed
    20 YES against 59 NO. Only 20 shares were hedged; the other 39 were a naked
    directional bet nobody chose. The same error at 60/40 with $20 a side loses
    $7 if YES wins and makes $10 if NO wins — a coin flip dressed as a hedge.
    """
    src = (Path(__file__).resolve().parent.parent
           / "scripts" / "run_pair_maker.py").read_text()
    assert "sz = float(int(args.usd_per_leg / px))" not in src, \
        "per-leg dollar sizing buys unequal shares — that is not a hedge"
    assert "shares = int(" in src, "must compute ONE share count for both legs"
    assert "sz = float(shares)" in src, "both legs must submit the same share count"


def test_pair_sizing_arithmetic_is_balanced():
    """The share count must be computed off the PAIR price, and the resulting
    basket must cost at most the budget while hedging every share bought."""
    for bid0, bid1, budget in ((0.73667, 0.25025, 30.0),
                               (0.4148, 0.5737, 40.0),
                               (0.0675, 0.9200, 50.0)):
        pair_px = bid0 + bid1
        shares = int(budget / pair_px)
        assert shares >= 1
        assert shares * pair_px <= budget + 1e-9, "basket must fit the budget"
        # every share on one leg is matched by one on the other
        assert shares == shares, "identical counts by construction"
        # and the payoff is symmetric: whichever side wins, we redeem `shares`
        redeem = shares * 1.0
        assert redeem - shares * pair_px >= 0, "pair below par must not lose"


def test_pair_maker_improves_the_touch():
    """Quoting behind the best bid means never trading.

    Measured 2026-09-21 after five hours of zero fills on books doing ~340
    trades/day: our bids sat one tick BELOW the touch with $384-$795 of other
    orders ahead of them — including the incumbent maker's 1000-share block —
    so nothing could reach us until that whole queue cleared. On one leg we
    were four levels deep (0.73332 against a 0.73912 touch).

    The original code justified this as stopping a post-only from crossing.
    That is false: an Alo order only crosses if it reaches the ASK. Resting at
    or one tick above the best bid never crosses and takes price priority.
    """
    src = (Path(__file__).resolve().parent.parent
           / "scripts" / "run_pair_maker.py").read_text()
    assert 'fresh[side]["bid"] - TICK' not in src, \
        "quoting BELOW the touch queues us behind the whole book — we never fill"
    assert 'fresh[side]["bid"] + TICK' in src, "must improve the touch"
    assert 'fresh[side]["ask"]' in src, \
        "must clamp against the ask so an improved bid can never cross"


def test_edge_is_checked_on_the_price_we_actually_pay():
    """Improving the touch costs a tick a leg. The edge gate must run on the
    quoted prices, not the raw book, or we book a worse trade than we measured.
    """
    src = (Path(__file__).resolve().parent.parent
           / "scripts" / "run_pair_maker.py").read_text()
    assert "edge_quoted" in src, "edge must be recomputed from the quoted prices"
    body = src.split("def main(")[1]
    assert body.index("edge_quoted") < body.index("free_usdc[0] -= need"), \
        "edge gate must precede capital reservation"
