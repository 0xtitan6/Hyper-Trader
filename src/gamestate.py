"""Live match state for HIP-4 sports outcomes — the in-play quoting guard.

WHY THIS EXISTS (measured 2026-09-20)
-------------------------------------
The paired-bid "edge" on HIP-4 sports surfaces is almost entirely an artefact of
matches being played right now:

    IN-PLAY    median paired edge  6.68%   (n=3)
    NOT LIVE   median paired edge  0.17%   (n=6)

A 39x difference. That spread is not an opportunity, it is the market pricing the
information asymmetry of a live event: someone watching the match knows the score
before the order book does.

We paid to learn this. On 2026-09-19 a resting bid on Tottenham YES filled at
0.5077 during a live match; Villa scored, the leg settled at 0.00, -$47. The same
mechanism filled a Draw leg at 0.2457 on a match that finished 0-0, +$165 so far.
Same process, opposite luck — which is exactly what no-edge-high-variance looks
like, and why the fix is to stop taking the bet rather than to hope for the good side.

So: quote pre-match and post-settlement, never in-play. The honest edge on
not-live books is ~0.17%, which is small and real, rather than ~6.7%, which is
compensation for being the person who does not know.

Deliberately deterministic — a public score feed answers this exactly and for
free. No model needed, and no model should be trusted over a scoreboard.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

ESPN = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
# ESPN's default scoreboard returns only the CURRENT matchday. A fixture a week
# out is simply absent, which reads identically to "feed does not cover it".
# Querying an explicit date range turns that silence into positive evidence:
# "England plays 2026-09-27, today is 2026-09-20, therefore not in play".
# A RANGE (dates=A-B) returns HTTP 400 on this API; single days work. So we
# walk day by day, cached, rather than asking for a window.
ESPN_DATED = ESPN + "?dates={date}"

# (sport_path, token that appears in a HIP-4 description). Soccer markets name a
# team ("participant:Fulham"); US leagues name the competition
# ("competition:NFL|contestType:game"). Missing the second form is not cosmetic:
# on 2026-09-20 a scan passed eight IN-PROGRESS NFL games as safe because the
# guard only knew "participant:", and their 1-8% paired "edge" was pure in-play
# adverse selection.
SPORT_PATHS = (
    "soccer/eng.1", "soccer/esp.1", "soccer/ita.1", "soccer/ger.1",
    "soccer/fra.1", "soccer/usa.1", "soccer/uefa.champions",
    # International windows list team names that appear in no domestic feed
    # (England, Spain, Slovenia...). Without these the guard cannot resolve them
    # and refuses every international fixture — safe, but it excludes the one
    # window with a genuine pre-match spread.
    "soccer/uefa.nations", "soccer/fifa.friendly", "soccer/fifa.worldq.uefa",
    "football/nfl", "football/college-football",
    "basketball/nba", "baseball/mlb", "hockey/nhl",
)
LEAGUES = SPORT_PATHS

# ESPN status descriptions that mean "the ball is in play right now".
IN_PLAY = {"First Half", "Second Half", "Halftime", "Extra Time", "Penalties",
           "In Progress", "End of Period", "Overtime", "Delayed", "Rain Delay"}
SAFE = {"Scheduled", "Full Time", "Final", "Final/OT", "Postponed", "Canceled"}

# Competition tokens -> the sport path whose scoreboard decides them. A market
# keyed on the competition rather than a team is live if ANY game in that league
# is live, because we cannot tell which fixture it refers to.
COMPETITION_LEAGUES = {
    "NFL": "football/nfl", "NBA": "basketball/nba", "MLB": "baseball/mlb",
    "NHL": "hockey/nhl", "NCAAF": "football/college-football",
}

# Tokens that mark a description as EVENT-SHAPED. If one of these is present and
# we cannot resolve the event to a scoreboard, we refuse — we do not shrug.
#
# This default was inverted on 2026-09-20 after the third hole in one day. The
# guard used to return "not a sports market" -> SAFE for anything it did not
# recognise, which waved through: eight in-progress NFL games (keyed
# `competition:` not `participant:`), and live UFC 331 bouts (UFC is in no
# scoreboard map). Both had juicy paired "edge" that was pure settled-event
# adverse selection. An unrecognised event market is not a non-event market.
EVENT_TOKENS = ("competition:", "contesttype:", "countedplay:", "participant:",
                "tournament", "contest", "ufc", "boxing", "fight", "match")

CACHE_TTL_S = 60.0
# Stop quoting this long before kickoff: a resting order becomes an in-play
# order the moment the contest starts, silently.
#
# SINGLE SOURCE OF TRUTH. scripts/pair_minder.py imports this value rather than
# defining its own. They diverged once (maker 1.0h, minder 3.0h) and the gap is
# not cosmetic: the maker would rest a quote 2h before kickoff and the minder
# would cancel it minutes later, burning post-only queue position on every
# cycle and — worse — risking a one-sided fill close to kickoff, which is
# exactly the shape that cost -$47 on 2026-09-19. Any change here moves both.
KICKOFF_BUFFER_H = 3.0


@dataclass
class MatchState:
    description: str          # ESPN status, e.g. "First Half"
    clock: str | None
    in_play: bool
    home: str
    away: str
    score: str


class GameState:
    """Team name -> live match state, cached briefly.

    Fails SAFE, and that word is load-bearing: if the feed is unreachable we
    report `unknown`, and the caller must treat unknown as DO-NOT-QUOTE. An
    outage is not evidence a match is not being played.
    """

    def __init__(self, leagues: tuple[str, ...] = LEAGUES, ttl_s: float = CACHE_TTL_S):
        self.leagues = leagues
        self.ttl_s = ttl_s
        self._cache: dict[str, MatchState] = {}
        self._live_by_league: dict[str, int] = {}
        self._fetched_at = 0.0
        self._upcoming: dict[str, str] = {}
        self._upcoming_at = 0.0

    def upcoming(self, days: int = 8) -> dict[str, str]:
        """team -> ISO date of its next SCHEDULED fixture within `days`.

        This is the positive-evidence half of the guard. Absence from today's
        scoreboard is not proof a team is idle; presence in a FUTURE fixture is.
        """
        if self._upcoming and (time.time() - self._upcoming_at) < 600:
            return self._upcoming
        today = datetime.now(tz=timezone.utc).date()
        found: dict[str, str] = {}
        for off in range(1, days + 1):          # tomorrow onward; today is handled by refresh()
            d = today + timedelta(days=off)
            ds = d.strftime("%Y%m%d")
            iso = d.isoformat()
            for lg in self.leagues:
                try:
                    r = requests.get(ESPN_DATED.format(path=lg, date=ds), timeout=15)
                    if r.status_code != 200:
                        continue
                    events = r.json().get("events", [])
                except (requests.RequestException, ValueError):
                    continue
                for e in events:
                    try:
                        comp = e["competitions"][0]
                        if comp["status"]["type"]["description"] != "Scheduled":
                            continue
                        for c in comp["competitors"]:
                            n = c["team"]["displayName"].lower()
                            if n not in found or iso < found[n]:
                                found[n] = iso
                    except (KeyError, IndexError, TypeError):
                        continue
                time.sleep(0.05)
        if found:
            self._upcoming = found
            self._upcoming_at = time.time()
        return found

    def next_fixture(self, team: str) -> str | None:
        up = self.upcoming()
        t = team.strip().lower()
        if t in up:
            return up[t]
        want = self._tokens(t)
        best = None
        for k, d in up.items():
            have = self._tokens(k)
            shared = want & have
            if shared and len(shared) / max(len(want), len(have)) >= 0.5:
                if best is None or d < best:
                    best = d
        return best

    def refresh(self, force: bool = False) -> bool:
        """Returns True if we hold usable state. False means the feed failed."""
        if not force and self._cache and (time.time() - self._fetched_at) < self.ttl_s:
            return True
        fresh: dict[str, MatchState] = {}
        live_by_league: dict[str, int] = {}
        ok_any = False
        for lg in self.leagues:
            try:
                r = requests.get(ESPN.format(path=lg), timeout=15)
                r.raise_for_status()
                events = r.json().get("events", [])
            except (requests.RequestException, ValueError):
                log.warning("gamestate: %s fetch failed", lg)
                continue
            ok_any = True
            for e in events:
                try:
                    comp = e["competitions"][0]
                    st = comp["status"]
                    desc = st["type"]["description"]
                    names = [c["team"]["displayName"] for c in comp["competitors"]]
                    score = " - ".join(str(c.get("score", "?")) for c in comp["competitors"])
                    ms = MatchState(
                        description=desc,
                        clock=st.get("displayClock"),
                        in_play=desc in IN_PLAY,
                        home=names[0] if names else "?",
                        away=names[1] if len(names) > 1 else "?",
                        score=score,
                    )
                    for n in names:
                        fresh[n.lower()] = ms
                    if ms.in_play:
                        live_by_league[lg] = live_by_league.get(lg, 0) + 1
                except (KeyError, IndexError, TypeError):
                    continue
            time.sleep(0.2)
        if ok_any:
            self._cache = fresh
            self._live_by_league = live_by_league
            self._fetched_at = time.time()
        return ok_any

    @staticmethod
    def _tokens(name: str) -> set[str]:
        """Word tokens, minus filler that creates false matches."""
        drop = {"fc", "cf", "afc", "sc", "ac", "the", "united", "city", "club"}
        return {w for w in re.split(r"[^a-z0-9]+", name.lower()) if w and w not in drop}

    def lookup(self, team: str) -> MatchState | None:
        """Match on WORD TOKENS, not raw substrings.

        Naive substring matching is actively dangerous here: on 2026-09-20 the
        market 'participant:England' matched 'New England Patriots' — an NFL game
        in progress — and reported England as IN PLAY at 7-0. That failed safe by
        luck. The same collision in the other direction (a live team whose name is
        a substring of a settled one) would wrongly APPROVE quoting into a live
        game, which is exactly the $47 loss.

        Requires a full-token match: {'england'} vs {'new','england','patriots'}
        is a subset and would still collide, so we additionally demand that the
        shorter name's tokens cover at least half the longer one's.
        """
        t = team.strip().lower()
        if not t:
            return None
        if t in self._cache:
            return self._cache[t]
        want = self._tokens(t)
        if not want:
            return None
        for k, v in self._cache.items():
            have = self._tokens(k)
            if not have:
                continue
            shared = want & have
            if not shared:
                continue
            # 'england' vs 'new england patriots' -> 1 shared of 3 = 0.33, rejected.
            # 'tottenham' vs 'tottenham hotspur'  -> 1 shared of 2 = 0.50, accepted.
            if len(shared) / max(len(want), len(have)) >= 0.5:
                return v
        return None

    @staticmethod
    def scheduled_start(description: str) -> datetime | None:
        """Kickoff time parsed from the market's OWN description.

        HIP-4 sports markets carry `scheduledStart:YYYYMMDD-HHMM` in UTC, e.g.
        `...|participantA:Miami Dolphins|scheduledStart:20260920-2025|...`.

        This is strictly better than matching team names against a scoreboard:
        it is deterministic, league-agnostic, needs no feed, and is immune to the
        name-collision class of bug that had 'England' resolving to 'New England
        Patriots' earlier today. Prefer it; fall back to the feed only when the
        field is absent.
        """
        if "scheduledStart:" not in description:
            return None
        raw = description.split("scheduledStart:")[1].split("|")[0].strip()
        try:
            return datetime.strptime(raw, "%Y%m%d-%H%M").replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    def is_safe_to_quote(self, description: str) -> tuple[bool, str]:
        """Decide from a HIP-4 outcome description, e.g. 'participant:Fulham'.

        Returns (safe, reason). Non-sports markets are safe by default — this
        guard is about live events, not about every market.
        """
        # PREFERRED PATH: the market states its own kickoff. No feed, no name
        # matching, no ambiguity about which fixture is meant.
        start = self.scheduled_start(description)
        if start is not None:
            now = datetime.now(tz=timezone.utc)
            hrs = (start - now).total_seconds() / 3600
            if hrs <= KICKOFF_BUFFER_H:
                return False, (f"contest started/starts {start:%Y-%m-%d %H:%M}Z "
                               f"({hrs:+.1f}h) — refusing to quote")
            return True, f"contest starts {start:%Y-%m-%d %H:%M}Z (in {hrs:.1f}h)"

        is_participant = "participant:" in description
        comp = None
        if "competition:" in description:
            comp = description.split("competition:")[1].split("|")[0].strip().upper()
        if not is_participant and comp not in COMPETITION_LEAGUES:
            low = description.lower()
            if any(t in low for t in EVENT_TOKENS) or not description.strip():
                return False, ("event-shaped market we cannot resolve to a scoreboard "
                               f"({description[:40]!r}) — refusing to quote")
            return True, "not an event market"

        if not self.refresh():
            return False, "score feed unreachable — refusing to quote (fail safe)"

        # Competition-keyed market: we cannot tell WHICH fixture, so any live
        # game in that league makes it unsafe.
        if not is_participant:
            lg = COMPETITION_LEAGUES[comp]
            n_live = self._live_by_league.get(lg, 0)
            if n_live:
                return False, f"{comp}: {n_live} game(s) IN PLAY — refusing to quote"
            return True, f"{comp}: no games in play"

        team = description.split("participant:")[1].split("|")[0].strip()

        ms = self.lookup(team)
        if ms is None:
            # Not on any current scoreboard. Look for positive evidence that the
            # fixture is in the FUTURE before allowing a quote.
            nxt = self.next_fixture(team)
            if nxt:
                today = datetime.now(tz=timezone.utc).date().isoformat()
                if nxt > today:
                    return True, f"{team} next plays {nxt} (not today)"
                return False, f"{team} plays TODAY ({nxt}) — refusing to quote"
            # A tournament-winner market has no single fixture today. Genuinely
            # different from "a match is on and we cannot see it", but we cannot
            # distinguish the two from here, so stay out.
            return False, f"no match state found for {team!r} — refusing to quote"
        if ms.in_play:
            return False, f"{team} IN PLAY ({ms.description} {ms.clock}, {ms.score})"
        return True, f"{team} {ms.description}"
