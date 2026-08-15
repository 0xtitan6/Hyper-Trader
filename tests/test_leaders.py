from unittest.mock import MagicMock

from src.config import DiscoveryConfig
from src.leaders import discover_leaders
from src.liquidiction import Trader


def _disc(top_n=3, min_trades=10, min_volume=100, min_pnl=10) -> DiscoveryConfig:
    return DiscoveryConfig(
        period="7d",
        top_n=top_n,
        min_trades=min_trades,
        min_volume_usd=min_volume,
        min_pnl_usd=min_pnl,
        refresh_seconds=600,
    )


def _t(addr: str, rank: int, pnl=1000, trades=100, volume=10000) -> Trader:
    return Trader(address=addr, rank=rank, pnl=pnl, trades=trades, volume=volume)


def test_filters_by_min_trades():
    client = MagicMock()
    client.top_traders.return_value = [
        _t("0xa", 1, trades=200),
        _t("0xb", 2, trades=5),  # filtered out (below min_trades=10)
        _t("0xc", 3, trades=50),
    ]
    leaders = discover_leaders(client, _disc(top_n=3, min_trades=10))
    assert [t.address for t in leaders] == ["0xa", "0xc"]


def test_filters_by_min_volume_and_pnl():
    client = MagicMock()
    client.top_traders.return_value = [
        _t("0xa", 1, volume=50),  # below min_volume
        _t("0xb", 2, pnl=-5),  # below min_pnl
        _t("0xc", 3),  # passes
    ]
    leaders = discover_leaders(client, _disc(top_n=5))
    assert [t.address for t in leaders] == ["0xc"]


def test_returns_at_most_top_n():
    client = MagicMock()
    client.top_traders.return_value = [_t(f"0x{i}", i) for i in range(20)]
    leaders = discover_leaders(client, _disc(top_n=3))
    assert len(leaders) == 3


def test_empty_input_returns_empty():
    client = MagicMock()
    client.top_traders.return_value = []
    leaders = discover_leaders(client, _disc())
    assert leaders == []


def test_all_filtered_out_returns_empty():
    client = MagicMock()
    client.top_traders.return_value = [_t("0xa", 1, trades=1)]
    leaders = discover_leaders(client, _disc(min_trades=100))
    assert leaders == []


# ---------- always_follow operator override ----------


def _disc_with_always(addrs: list[str], top_n: int = 3) -> DiscoveryConfig:
    return DiscoveryConfig(
        period="7d",
        top_n=top_n,
        min_trades=10,
        min_volume_usd=100,
        min_pnl_usd=10,
        refresh_seconds=600,
        always_follow=addrs,
    )


def test_always_follow_appends_known_address():
    """If the always-follow address is in candidates, include the real Trader."""
    client = MagicMock()
    client.top_traders.return_value = [
        _t("0xa", 1, trades=200),
        _t("0xrwa", 31, pnl=2297, trades=88),  # would normally pass coarse anyway
    ]
    leaders = discover_leaders(client, _disc_with_always(["0xrwa"], top_n=1))
    addrs = [t.address for t in leaders]
    assert "0xa" in addrs
    assert "0xrwa" in addrs
    rwa = next(t for t in leaders if t.address == "0xrwa")
    assert rwa.rank == 31  # full Trader record preserved
    assert rwa.pnl == 2297


def test_always_follow_synthesizes_unknown_address():
    """If the always-follow address is NOT in candidates, synthesize a stub."""
    client = MagicMock()
    client.top_traders.return_value = [_t("0xa", 1, trades=200)]
    leaders = discover_leaders(
        client, _disc_with_always(["0xunknown"], top_n=1)
    )
    addrs = [t.address for t in leaders]
    assert "0xa" in addrs
    assert "0xunknown" in addrs
    stub = next(t for t in leaders if t.address == "0xunknown")
    assert stub.rank == -1  # synthetic marker
    assert stub.pnl == 0.0


def test_always_follow_bypasses_coarse_filter():
    """An always-follow address with low trades/volume/pnl is included anyway."""
    client = MagicMock()
    client.top_traders.return_value = [_t("0xnoise", 99, trades=1, volume=1, pnl=1)]
    leaders = discover_leaders(client, _disc_with_always(["0xnoise"], top_n=3))
    assert [t.address for t in leaders] == ["0xnoise"]


def test_always_follow_dedupes_against_normal_selection():
    """If a leader is selected normally AND in always_follow, only include once."""
    client = MagicMock()
    client.top_traders.return_value = [_t("0xa", 1, trades=200)]
    leaders = discover_leaders(client, _disc_with_always(["0xa"], top_n=3))
    assert [t.address for t in leaders] == ["0xa"]


def test_always_follow_case_insensitive_dedupe():
    """Mixed-case override addresses still dedupe against lowercase candidates."""
    client = MagicMock()
    client.top_traders.return_value = [_t("0xa", 1, trades=200)]
    leaders = discover_leaders(client, _disc_with_always(["0xA"], top_n=3))
    assert len(leaders) == 1


def test_always_follow_added_on_top_of_top_n():
    """always_follow adds to top_n, not into it — operator gets all picks."""
    client = MagicMock()
    client.top_traders.return_value = [_t(f"0x{i}", i, trades=200) for i in range(5)]
    leaders = discover_leaders(client, _disc_with_always(["0xrwa"], top_n=2))
    addrs = [t.address for t in leaders]
    # top 2 from candidates + 1 forced
    assert len(leaders) == 3
    assert "0xrwa" in addrs


# ---------- per-leader weight (Sharpe-based + explicit override) ----------


def test_default_weight_is_one():
    """No weight config = every leader keeps default 1.0 weight."""
    client = MagicMock()
    client.top_traders.return_value = [_t("0xa", 1, trades=200)]
    leaders = discover_leaders(client, _disc(top_n=3))
    assert len(leaders) == 1
    assert leaders[0].weight == 1.0


def test_explicit_leader_weights_override():
    """leader_weights config sets per-address weight, case-insensitive."""
    client = MagicMock()
    client.top_traders.return_value = [_t("0xab", 1, trades=200)]
    cfg = DiscoveryConfig(
        period="7d",
        top_n=3,
        min_trades=10,
        min_volume_usd=100,
        min_pnl_usd=10,
        refresh_seconds=600,
        leader_weights={"0xAB": 2.5},  # mixed case key
    )
    leaders = discover_leaders(client, cfg)
    assert leaders[0].weight == 2.5


def test_explicit_weight_applies_to_always_follow_synthetic():
    """always_follow stub gets weight from leader_weights map."""
    client = MagicMock()
    client.top_traders.return_value = []
    cfg = DiscoveryConfig(
        period="7d",
        top_n=3,
        min_trades=10,
        min_volume_usd=100,
        min_pnl_usd=10,
        refresh_seconds=600,
        always_follow=["0x" + "b" * 40],
        leader_weights={"0x" + "b" * 40: 3.0},
    )
    leaders = discover_leaders(client, cfg)
    assert len(leaders) == 1
    assert leaders[0].weight == 3.0
    assert leaders[0].rank == -1  # was a synthetic stub


# --- solvency gate (2026-08-15) ---------------------------------------------
# 0x9551e7d4 held a live leader slot for a day at $0 equity / 0 positions /
# last fill 19.4h old. It passed every quality check because 42% of its flow is
# xyz: perps — the filter measured perp FRACTION but never whether the wallet
# had any money. A sweep of the top 60 found 44 at zero perp equity.

def _info_with_equity(equity_by_addr: dict, fills=None):
    """An info double whose user_state reports per-address perp equity."""
    info = MagicMock()
    info.user_state.side_effect = lambda a: {
        "marginSummary": {"accountValue": str(equity_by_addr.get(a.lower(), 0.0))}
    }
    info.user_fills_by_time.return_value = fills if fills is not None else []
    return info


def test_zero_equity_leader_is_rejected(monkeypatch):
    from src import leaders as leaders_mod

    monkeypatch.setattr(
        leaders_mod, "load_metrics", lambda *a, **k: MagicMock(realized_pnl_sharpe=1.0)
    )
    monkeypatch.setattr(leaders_mod, "meets_quality", lambda *a, **k: (True, ""))
    client = MagicMock()
    client.top_traders.return_value = [
        Trader(address="0xdead", rank=1, pnl=9999.0, trades=999, volume=1e6),
    ]
    cfg = DiscoveryConfig(
        period="7d", top_n=2, min_trades=1, min_volume_usd=0, min_pnl_usd=0,
        refresh_seconds=600, use_quality_filter=True, min_leader_equity_usd=500.0,
    )
    out = discover_leaders(client, cfg, info=_info_with_equity({"0xdead": 0.0}))
    assert out == []


def test_funded_leader_passes_the_solvency_gate(monkeypatch):
    from src import leaders as leaders_mod

    monkeypatch.setattr(
        leaders_mod, "load_metrics", lambda *a, **k: MagicMock(realized_pnl_sharpe=1.0)
    )
    monkeypatch.setattr(leaders_mod, "meets_quality", lambda *a, **k: (True, ""))
    client = MagicMock()
    client.top_traders.return_value = [
        Trader(address="0xrich", rank=1, pnl=9999.0, trades=999, volume=1e6),
    ]
    cfg = DiscoveryConfig(
        period="7d", top_n=2, min_trades=1, min_volume_usd=0, min_pnl_usd=0,
        refresh_seconds=600, use_quality_filter=True, min_leader_equity_usd=500.0,
    )
    out = discover_leaders(client, cfg, info=_info_with_equity({"0xrich": 25_000.0}))
    assert [t.address for t in out] == ["0xrich"]


def test_equity_probe_failure_does_not_disqualify(monkeypatch):
    """Fail OPEN: an info blip must never silently drop a good leader."""
    from src import leaders as leaders_mod

    monkeypatch.setattr(
        leaders_mod, "load_metrics", lambda *a, **k: MagicMock(realized_pnl_sharpe=1.0)
    )
    monkeypatch.setattr(leaders_mod, "meets_quality", lambda *a, **k: (True, ""))
    client = MagicMock()
    client.top_traders.return_value = [
        Trader(address="0xflaky", rank=1, pnl=9999.0, trades=999, volume=1e6),
    ]
    info = MagicMock()
    info.user_state.side_effect = RuntimeError("503")
    cfg = DiscoveryConfig(
        period="7d", top_n=2, min_trades=1, min_volume_usd=0, min_pnl_usd=0,
        refresh_seconds=600, use_quality_filter=True, min_leader_equity_usd=500.0,
    )
    out = discover_leaders(client, cfg, info=info)
    assert [t.address for t in out] == ["0xflaky"]
