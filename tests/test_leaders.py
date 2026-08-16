from unittest.mock import MagicMock

from src.config import DiscoveryConfig
from src.leaders import _perp_equity_usd, discover_leaders, hip3_dex_names
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
# The gate exists because a leaderboard rank is 30d of history: a trader who
# withdrew or blew up keeps their rank while trading nothing. `0x166866a2` is
# genuinely empty on every clearinghouse despite 1,375 recent fills.
#
# It originally read `user_state` only, and the claims made from that read —
# that `0x9551e7d4` was a "$0 equity dead slot", and that "44 of the top 60
# have zero perp equity" — were BOTH artifacts of INV 1: `user_state` covers
# the base dex only. 0x9551e7d4 holds $8,104 on xyz. Neither is established;
# see the per-dex tests below and P0c in BACKLOG.md.

def _info_with_equity(equity_by_addr: dict, fills=None):
    """An info double whose user_state reports per-address BASE perp equity.

    `perpDexs` answers `[]` — this wallet has no HIP-3 clearinghouse, so base
    is the whole story and the gate's verdict rests on it alone.
    """
    info = MagicMock()
    info.user_state.side_effect = lambda a: {
        "marginSummary": {"accountValue": str(equity_by_addr.get(a.lower(), 0.0))}
    }
    info.post.side_effect = lambda _p, payload: [] if payload.get("type") == "perpDexs" else None
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
    # Every clearinghouse unreadable: base raises, and so does the enumeration.
    info = MagicMock()
    info.user_state.side_effect = RuntimeError("503")
    info.post.side_effect = RuntimeError("503")
    cfg = DiscoveryConfig(
        period="7d", top_n=2, min_trades=1, min_volume_usd=0, min_pnl_usd=0,
        refresh_seconds=600, use_quality_filter=True, min_leader_equity_usd=500.0,
    )
    out = discover_leaders(client, cfg, info=info)
    assert [t.address for t in out] == ["0xflaky"]


# --- solvency gate reads EVERY clearinghouse (P0c, 2026-08-15) ---------------
# `_perp_equity_usd` used `user_state`, which is BASE-dex only (INV 1 — the
# same misread shipped in three modules that day). Leaders whose collateral
# sits on a HIP-3 dex read $0 and were rejected as insolvent, measured live:
#
#     0x819d06c0   base $0.00  ->    $514 on xyz   <- our PINNED incumbent
#     0x9551e7d4   base $0.00  ->  $8,104 on xyz
#     0x810b41bd   base $0.00  -> $62,955 on xyz
#     0x2649bb08   base $0.00  -> $15,109 on xyz
#
# 18-21 of 60 candidates were rejected this way.


class _PerDexInfo:
    """An info double holding a separate equity per clearinghouse.

    `base` is what `user_state` reports; `dexes` maps HIP-3 dex name -> equity.
    A name in `unreadable` raises when its `clearinghouseState` is asked for,
    `perp_dexs_ok=False` fails the enumeration itself, and `base_ok=False`
    fails the base read — the three ways INV 4's "unknown" arises here.
    """

    def __init__(self, base=0.0, dexes=None, unreadable=(), perp_dexs_ok=True, base_ok=True):
        self.base = base
        self.dexes = dict(dexes or {})
        self.unreadable = set(unreadable)
        self.perp_dexs_ok = perp_dexs_ok
        self.base_ok = base_ok
        self.posts: list[dict] = []

    def user_state(self, address):
        if not self.base_ok:
            raise RuntimeError("503 user_state")
        return {"marginSummary": {"accountValue": str(self.base)}}

    def post(self, _path, payload):
        self.posts.append(payload)
        kind = payload.get("type")
        if kind == "perpDexs":
            if not self.perp_dexs_ok:
                raise RuntimeError("503 perpDexs")
            # HL answers with a leading null for the base dex; the real
            # response shape, so the isinstance filter is exercised.
            return [None] + [{"name": n} for n in self.dexes]
        if kind == "clearinghouseState":
            dex = payload["dex"]
            if dex in self.unreadable:
                raise RuntimeError(f"503 {dex}")
            return {"marginSummary": {"accountValue": str(self.dexes.get(dex, 0.0))}}
        raise AssertionError(f"unexpected /info type {kind!r}")


def test_equity_base_only_wallet_passes():
    info = _PerDexInfo(base=25_000.0, dexes={"xyz": 0.0})
    assert _perp_equity_usd(info, "0xrich", min_usd=500.0, dex_names=hip3_dex_names(info)) == 25_000.0


def test_equity_funded_on_base_skips_the_per_dex_reads():
    """Base already clears the bar, so no HIP-3 read can change the verdict.

    Worth pinning: discovery screens ~60 wallets a cycle, so this keeps the
    common case at one call per wallet rather than one per wallet per dex.
    """
    info = _PerDexInfo(base=25_000.0, dexes={"xyz": 1.0, "flx": 2.0})
    names = hip3_dex_names(info)
    info.posts.clear()  # drop the one-per-cycle enumeration above
    assert _perp_equity_usd(info, "0xrich", min_usd=500.0, dex_names=names) == 25_000.0
    assert [p["type"] for p in info.posts] == []


def test_equity_hip3_only_wallet_passes():
    """THE HEADLINE REGRESSION: 0x9551e7d4 reads $0 on base, $8,104 on xyz."""
    info = _PerDexInfo(base=0.0, dexes={"xyz": 8_104.0})
    assert _perp_equity_usd(info, "0x9551e7d4", min_usd=500.0, dex_names=hip3_dex_names(info)) == 8_104.0


def test_equity_split_across_base_and_dex_takes_the_best_not_the_sum():
    """INV 2: each dex settles against its OWN collateral.

    $300 on base plus $300 on xyz is not a $600 wallet on either, so a $500
    threshold must reject it. Summing would wrongly pass it.
    """
    info = _PerDexInfo(base=300.0, dexes={"xyz": 300.0})
    assert _perp_equity_usd(info, "0xsplit", min_usd=500.0, dex_names=hip3_dex_names(info)) == 300.0


def test_equity_takes_the_largest_readable_clearinghouse():
    info = _PerDexInfo(base=100.0, dexes={"xyz": 514.0, "flx": 20.0})
    assert _perp_equity_usd(info, "0x819d06c0", min_usd=500.0, dex_names=hip3_dex_names(info)) == 514.0


def test_equity_empty_on_every_clearinghouse_is_rejected():
    """INV 4's other direction: fail-open must not become never-act.

    `0x166866a2` really is empty everywhere despite 1,375 recent fills. A
    complete read that finds nothing is a FACT, and must still reject.
    """
    info = _PerDexInfo(base=0.0, dexes={"xyz": 0.0, "flx": 0.0})
    assert _perp_equity_usd(info, "0x166866a2", min_usd=500.0, dex_names=hip3_dex_names(info)) == 0.0


def test_equity_unreadable_dex_is_unknown_not_a_rejection():
    """INV 4: an unreadable dex could be holding the collateral."""
    info = _PerDexInfo(base=0.0, dexes={"xyz": 0.0}, unreadable={"xyz"})
    assert _perp_equity_usd(info, "0xflaky", min_usd=500.0, dex_names=hip3_dex_names(info)) is None


def test_equity_unreadable_dex_ignored_when_another_already_clears():
    """A blip on one dex cannot blind us to money we already found."""
    info = _PerDexInfo(base=0.0, dexes={"xyz": 8_104.0, "flx": 0.0}, unreadable={"flx"})
    assert _perp_equity_usd(info, "0x9551e7d4", min_usd=500.0, dex_names=hip3_dex_names(info)) == 8_104.0


def test_equity_unenumerable_dexes_is_unknown_not_a_rejection():
    """`perpDexs` failed 215 times in August; that is unknown, not insolvent."""
    info = _PerDexInfo(base=12.0, perp_dexs_ok=False)
    assert _perp_equity_usd(info, "0xflaky", min_usd=500.0, dex_names=hip3_dex_names(info)) is None


def test_equity_unreadable_base_still_passes_on_a_funded_dex():
    info = _PerDexInfo(dexes={"xyz": 62_955.0}, base_ok=False)
    assert _perp_equity_usd(info, "0x810b41bd", min_usd=500.0, dex_names=hip3_dex_names(info)) == 62_955.0


def test_equity_unreadable_everywhere_is_unknown():
    info = _PerDexInfo(base_ok=False, perp_dexs_ok=False)
    assert _perp_equity_usd(info, "0xdark", min_usd=500.0, dex_names=hip3_dex_names(info)) is None


def test_equity_no_hip3_dexes_at_all_is_a_complete_read():
    """`[]` means 'genuinely none', unlike None. Base alone decides."""
    info = _PerDexInfo(base=12.0, dexes={})
    assert _perp_equity_usd(info, "0xpoor", min_usd=500.0, dex_names=hip3_dex_names(info)) == 12.0


def test_equity_malformed_clearinghouse_state_is_unreadable_not_zero():
    """Junk in the payload is a failed read (INV 4), never $0."""
    info = _PerDexInfo(base=0.0, dexes={"xyz": 0.0})
    info.post = lambda _p, payload: (
        [{"name": "xyz"}] if payload.get("type") == "perpDexs" else {"marginSummary": "nonsense"}
    )
    assert _perp_equity_usd(info, "0xjunk", min_usd=500.0, dex_names=hip3_dex_names(info)) is None


def test_dex_enumeration_happens_once_per_cycle_not_once_per_candidate(monkeypatch):
    """`perpDexs` describes the exchange, so screening 30 wallets fetches it once.

    Per-candidate enumeration would add ~60 identical /info calls to every
    discovery cycle, and INV 7 records HL 429-ing us over back-to-back calls.
    """
    from src import leaders as leaders_mod

    monkeypatch.setattr(
        leaders_mod, "load_metrics", lambda *a, **k: MagicMock(realized_pnl_sharpe=1.0)
    )
    monkeypatch.setattr(leaders_mod, "meets_quality", lambda *a, **k: (True, ""))
    client = MagicMock()
    client.top_traders.return_value = [
        Trader(address=f"0x{i:02d}", rank=i, pnl=9999.0, trades=999, volume=1e6)
        for i in range(30)
    ]
    cfg = DiscoveryConfig(
        period="7d", top_n=30, min_trades=1, min_volume_usd=0, min_pnl_usd=0,
        refresh_seconds=600, use_quality_filter=True, min_leader_equity_usd=500.0,
    )
    # base $0 everywhere, so every candidate takes the per-dex path.
    info = _PerDexInfo(base=0.0, dexes={"xyz": 8_104.0})
    discover_leaders(client, cfg, info=info)
    assert [p["type"] for p in info.posts].count("perpDexs") == 1


def test_hip3_only_leader_is_selected_end_to_end(monkeypatch):
    """The pinned-incumbent case, through `discover_leaders` rather than the helper.

    `config.yaml` warns that 0x819d06c0 would be dropped if ever unpinned;
    this base-$0 / xyz-$514 shape is exactly that mechanism.
    """
    from src import leaders as leaders_mod

    monkeypatch.setattr(
        leaders_mod, "load_metrics", lambda *a, **k: MagicMock(realized_pnl_sharpe=1.0)
    )
    monkeypatch.setattr(leaders_mod, "meets_quality", lambda *a, **k: (True, ""))
    client = MagicMock()
    client.top_traders.return_value = [
        Trader(address="0x819d06c0", rank=1, pnl=9999.0, trades=999, volume=1e6),
    ]
    cfg = DiscoveryConfig(
        period="7d", top_n=2, min_trades=1, min_volume_usd=0, min_pnl_usd=0,
        refresh_seconds=600, use_quality_filter=True, min_leader_equity_usd=500.0,
    )
    info = _PerDexInfo(base=0.0, dexes={"xyz": 514.0})
    out = discover_leaders(client, cfg, info=info)
    assert [t.address for t in out] == ["0x819d06c0"]
