"""Tests for src/hl_hip3.py — HIP-3 perp dex asset registration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src import hl_hip3
from src.hl_hip3 import register_hip3_dexes
from src.market_meta import MarketMeta


def _info_with_dexes(*, dexes_response, meta_by_dex: dict | None = None) -> MagicMock:
    """Build a mock Info where info.post() routes by request type."""
    info = MagicMock()
    info.coin_to_asset = {}
    info.name_to_coin = {}
    info.asset_to_sz_decimals = {}
    meta_by_dex = meta_by_dex or {}

    # Simulate SDK's set_perp_meta — write into coin_to_asset etc.
    def set_perp_meta(meta, offset):
        for asset_idx, asset_info in enumerate(meta.get("universe", [])):
            asset_id = offset + asset_idx
            name = asset_info["name"]
            info.coin_to_asset[name] = asset_id
            info.name_to_coin[name] = name
            info.asset_to_sz_decimals[asset_id] = asset_info.get("szDecimals", 0)

    info.set_perp_meta.side_effect = set_perp_meta

    def post(path, payload):
        t = payload.get("type")
        if t == "perpDexs":
            return dexes_response
        if t == "meta":
            return meta_by_dex.get(payload.get("dex"))
        return None

    info.post.side_effect = post
    return info


# --- happy path ------------------------------------------------------------


def test_registers_assets_from_single_hip3_dex():
    info = _info_with_dexes(
        dexes_response=[None, {"name": "xyz"}],
        meta_by_dex={
            "xyz": {"universe": [
                {"name": "xyz:NVDA", "szDecimals": 4},
                {"name": "xyz:AAPL", "szDecimals": 4},
            ]},
        },
    )
    n = register_hip3_dexes(info)
    assert n == 2
    assert info.coin_to_asset["xyz:NVDA"] == 110_000
    assert info.coin_to_asset["xyz:AAPL"] == 110_001
    assert info.name_to_coin["xyz:NVDA"] == "xyz:NVDA"


def test_registers_assets_from_multiple_hip3_dexes():
    info = _info_with_dexes(
        dexes_response=[None, {"name": "xyz"}, {"name": "flx"}],
        meta_by_dex={
            "xyz": {"universe": [{"name": "xyz:NVDA", "szDecimals": 4}]},
            "flx": {"universe": [{"name": "flx:BTC", "szDecimals": 5}]},
        },
    )
    n = register_hip3_dexes(info)
    assert n == 2
    # xyz at offset 110000, flx at offset 120000
    assert info.coin_to_asset["xyz:NVDA"] == 110_000
    assert info.coin_to_asset["flx:BTC"] == 120_000


def test_idempotent_overwrites_same_mapping():
    info = _info_with_dexes(
        dexes_response=[None, {"name": "xyz"}],
        meta_by_dex={"xyz": {"universe": [{"name": "xyz:NVDA", "szDecimals": 4}]}},
    )
    register_hip3_dexes(info)
    register_hip3_dexes(info)  # second call must not double-count, no errors
    assert info.coin_to_asset["xyz:NVDA"] == 110_000


def test_periodic_refresh_picks_up_newly_added_symbols():
    """Real-world scenario: HL adds a new symbol to xyz dex after our startup
    registration. Re-running register_hip3_dexes against the now-bigger
    universe must add the new symbol without disturbing existing entries."""
    # First registration: 1 symbol
    info = _info_with_dexes(
        dexes_response=[None, {"name": "xyz"}],
        meta_by_dex={"xyz": {"universe": [{"name": "xyz:NVDA", "szDecimals": 4}]}},
    )
    register_hip3_dexes(info)
    assert "xyz:NVDA" in info.coin_to_asset
    assert "xyz:QNT" not in info.coin_to_asset

    # Simulate HL adding a new symbol — rebuild the mock with bigger universe
    info2 = _info_with_dexes(
        dexes_response=[None, {"name": "xyz"}],
        meta_by_dex={"xyz": {"universe": [
            {"name": "xyz:NVDA", "szDecimals": 4},
            {"name": "xyz:QNT", "szDecimals": 4},
        ]}},
    )
    # Copy the existing coin map so we're testing on the same instance state
    info2.coin_to_asset = dict(info.coin_to_asset)
    register_hip3_dexes(info2)
    assert "xyz:NVDA" in info2.coin_to_asset
    assert "xyz:QNT" in info2.coin_to_asset
    # Original symbol's asset_id unchanged
    assert info2.coin_to_asset["xyz:NVDA"] == 110_000
    # New symbol gets the next index
    assert info2.coin_to_asset["xyz:QNT"] == 110_001


# --- error handling --------------------------------------------------------


def test_returns_zero_when_perp_dexs_fetch_fails():
    info = MagicMock()
    info.coin_to_asset = {}
    info.post.side_effect = RuntimeError("network down")
    n = register_hip3_dexes(info)
    assert n == 0


def test_returns_zero_when_perp_dexs_returns_non_list():
    info = _info_with_dexes(dexes_response={"oops": "shape"})
    n = register_hip3_dexes(info)
    assert n == 0


def test_continues_when_one_dex_meta_fails():
    """If one HIP-3 dex's meta fetch fails, others should still register."""
    def post(path, payload):
        t = payload.get("type")
        if t == "perpDexs":
            return [None, {"name": "xyz"}, {"name": "flx"}]
        if t == "meta" and payload.get("dex") == "xyz":
            raise OSError("transient")
        if t == "meta" and payload.get("dex") == "flx":
            return {"universe": [{"name": "flx:BTC", "szDecimals": 5}]}
        return None

    info = MagicMock()
    info.coin_to_asset = {}
    info.name_to_coin = {}
    info.asset_to_sz_decimals = {}

    def set_perp_meta(meta, offset):
        for i, a in enumerate(meta["universe"]):
            info.coin_to_asset[a["name"]] = offset + i

    info.set_perp_meta.side_effect = set_perp_meta
    info.post.side_effect = post

    n = register_hip3_dexes(info)
    assert n == 1  # only flx registered
    assert "flx:BTC" in info.coin_to_asset
    assert "xyz:NVDA" not in info.coin_to_asset


def test_skips_malformed_dex_entries():
    """Defensive: dex entries that aren't dicts or have no name are skipped."""
    info = _info_with_dexes(
        dexes_response=[None, "not_a_dict", {"no_name_field": True}, {"name": "xyz"}],
        meta_by_dex={"xyz": {"universe": [{"name": "xyz:NVDA", "szDecimals": 4}]}},
    )
    n = register_hip3_dexes(info)
    # xyz still registers; bad entries skipped without crash. xyz is at index 3 in dexes[1:],
    # so its offset is 110000 + 2*10000 = 130000 (i=2 in the loop).
    assert n == 1
    assert info.coin_to_asset["xyz:NVDA"] == 130_000


def test_skips_when_meta_shape_invalid():
    info = _info_with_dexes(
        dexes_response=[None, {"name": "xyz"}],
        meta_by_dex={"xyz": {"no_universe_field": True}},
    )
    n = register_hip3_dexes(info)
    assert n == 0


def test_empty_dexes_returns_zero():
    """No HIP-3 dexes deployed yet — just the original dex (None) in the list."""
    info = _info_with_dexes(dexes_response=[None])
    n = register_hip3_dexes(info)
    assert n == 0


def test_falls_back_to_manual_mutation_when_set_perp_meta_missing():
    """If a future SDK version drops set_perp_meta, we shouldn't crash."""
    info = MagicMock(spec=[])  # no methods/attrs at all
    info.coin_to_asset = {}
    info.name_to_coin = {}
    info.asset_to_sz_decimals = {}

    def post(path, payload):
        t = payload.get("type")
        if t == "perpDexs":
            return [None, {"name": "xyz"}]
        if t == "meta":
            return {"universe": [{"name": "xyz:NVDA", "szDecimals": 4}]}
        return None

    info.post = MagicMock(side_effect=post)
    # No set_perp_meta on this mock — AttributeError will fire, fallback should kick in
    n = register_hip3_dexes(info)
    assert n == 1
    assert info.coin_to_asset["xyz:NVDA"] == 110_000
    assert info.name_to_coin["xyz:NVDA"] == "xyz:NVDA"
    assert info.asset_to_sz_decimals[110_000] == 4


# --- retry / backoff -------------------------------------------------------
#
# `register_hip3_dexes: perpDexs fetch failed` fired 215 times in Aug 2026.
# A single failure used to zero out the whole cycle, leaving us blind to the
# xyz:* surface until main.py's next 30-min tick — and blind means the size
# rounder has no szDecimals, which is the head of the poison cascade.


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    """Never actually sleep in tests; record the backoff schedule instead."""
    slept: list[float] = []
    monkeypatch.setattr(hl_hip3.time, "sleep", slept.append)
    return slept


def test_perp_dexs_transient_failure_is_retried(no_real_sleep):
    """One blip must not cost us the whole registration cycle."""
    calls = {"n": 0}
    info = _info_with_dexes(
        dexes_response=[None, {"name": "xyz"}],
        meta_by_dex={"xyz": {"universe": [{"name": "xyz:MU", "szDecimals": 3}]}},
    )
    inner = info.post.side_effect

    def flaky(path, payload):
        if payload.get("type") == "perpDexs":
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("connection reset")
        return inner(path, payload)

    info.post.side_effect = flaky
    n = register_hip3_dexes(info)
    assert n == 1
    assert calls["n"] == 2
    assert info.coin_to_asset["xyz:MU"] == 110_000
    assert no_real_sleep == [2.0]  # one backoff before the retry


def test_perp_dexs_retries_exhaust_then_returns_zero(no_real_sleep):
    info = MagicMock()
    info.coin_to_asset = {}
    info.post.side_effect = RuntimeError("network down")
    n = register_hip3_dexes(info)
    assert n == 0
    assert info.post.call_count == 3  # 1 initial + 2 retries
    assert no_real_sleep == [2.0, 4.0]  # exponential backoff


def test_perp_dexs_empty_body_is_retried(no_real_sleep):
    """HL sometimes answers 200 with a null body — just as blind as raising."""
    calls = {"n": 0}

    def post(path, payload):
        if payload.get("type") == "perpDexs":
            calls["n"] += 1
            if calls["n"] < 3:
                return None
            return [None, {"name": "xyz"}]
        if payload.get("type") == "meta":
            return {"universe": [{"name": "xyz:MU", "szDecimals": 3}]}
        return None

    info = MagicMock()
    info.coin_to_asset = {}
    info.name_to_coin = {}
    info.asset_to_sz_decimals = {}
    info.post.side_effect = post
    n = register_hip3_dexes(info)
    assert n == 1
    assert calls["n"] == 3
    assert no_real_sleep == [2.0, 4.0]


def test_per_dex_meta_failure_is_retried_before_giving_up(no_real_sleep):
    """A flaky per-dex meta must not silently drop that dex's whole universe."""
    calls = {"n": 0}

    def post(path, payload):
        t = payload.get("type")
        if t == "perpDexs":
            return [None, {"name": "xyz"}]
        if t == "meta":
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("timeout")
            return {"universe": [{"name": "xyz:SKHY", "szDecimals": 2}]}
        return None

    info = MagicMock()
    info.coin_to_asset = {}
    info.name_to_coin = {}
    info.asset_to_sz_decimals = {}
    info.post.side_effect = post
    assert register_hip3_dexes(info) == 1
    assert calls["n"] == 2


def test_non_list_perp_dexs_is_not_retried(no_real_sleep):
    """A well-formed-but-wrong shape is a contract change, not a blip —
    retrying it just burns 6s on every refresh tick."""
    info = _info_with_dexes(dexes_response={"oops": "shape"})
    assert register_hip3_dexes(info) == 0
    assert no_real_sleep == []


# --- MarketMeta hand-off ---------------------------------------------------


def test_registers_szdecimals_into_market_meta():
    """The ONLY path by which the rounder learns xyz:MU is 3dp — MarketMeta
    .load() calls info.meta(), which returns the original perp dex only."""
    mm = MarketMeta(_stub_info_for_meta())
    mm.load()
    info = _info_with_dexes(
        dexes_response=[None, {"name": "xyz"}],
        meta_by_dex={"xyz": {"universe": [
            {"name": "xyz:MU", "szDecimals": 3},
            {"name": "xyz:SKHY", "szDecimals": 2},
        ]}},
    )
    assert register_hip3_dexes(info, market_meta=mm) == 2
    assert mm._size_decimals_for("xyz:MU") == 3
    assert mm._size_decimals_for("xyz:SKHY") == 2
    assert mm.round_size("xyz:MU", 0.0143) == 0.014


def test_market_meta_not_updated_when_fetch_fails(no_real_sleep):
    """Blind stays blind — the rounder must NOT end up with a guess."""
    mm = MarketMeta(_stub_info_for_meta())
    mm.load()
    info = MagicMock()
    info.coin_to_asset = {}
    info.post.side_effect = RuntimeError("network down")
    assert register_hip3_dexes(info, market_meta=mm) == 0
    assert not mm.has_size_decimals("xyz:MU")


def test_market_meta_ingest_failure_does_not_abort_registration():
    """A broken sink must not cost us the SDK coin-map registration."""
    mm = MagicMock()
    mm.register_dex_assets.side_effect = RuntimeError("boom")
    info = _info_with_dexes(
        dexes_response=[None, {"name": "xyz"}],
        meta_by_dex={"xyz": {"universe": [{"name": "xyz:MU", "szDecimals": 3}]}},
    )
    assert register_hip3_dexes(info, market_meta=mm) == 1
    assert info.coin_to_asset["xyz:MU"] == 110_000


def _stub_info_for_meta() -> MagicMock:
    info = MagicMock()
    info.meta.return_value = {"universe": [{"name": "BTC", "szDecimals": 5}]}
    info.spot_meta.return_value = {"universe": [], "tokens": []}
    return info
