from src.alerts import NullAlerter, WebhookAlerter
from src.main import build_alerter, install_signal_handler, parse_args


def test_parse_args_defaults():
    ns = parse_args([])
    assert ns.config == "config.yaml"
    assert ns.preflight is False
    assert ns.skip_preflight is False


def test_parse_args_preflight_flag():
    ns = parse_args(["--preflight"])
    assert ns.preflight is True


def test_parse_args_custom_config():
    ns = parse_args(["--config", "foo.yaml"])
    assert ns.config == "foo.yaml"


def test_parse_args_skip_preflight():
    ns = parse_args(["--skip-preflight"])
    assert ns.skip_preflight is True


def test_build_alerter_null_when_no_url(cfg):
    alerter = build_alerter(cfg)
    assert isinstance(alerter, NullAlerter)


def test_build_alerter_webhook_when_url_set(cfg):
    from dataclasses import replace

    cfg2 = replace(cfg, webhook_url="https://hooks.slack.example/x")
    alerter = build_alerter(cfg2)
    assert isinstance(alerter, WebhookAlerter)


def test_install_signal_handler_returns_unset_event():
    e = install_signal_handler()
    assert not e.is_set()


# --- dropped-leader wiring (BACKLOG P1) ------------------------------------
#
# main() cannot be exercised in tests: INV 8 — the API URL comes from
# `network.hyperliquid_env`, env vars do NOT override it, so importing and
# running it starts a REAL SECOND LIVE ENGINE (done accidentally 2026-08-15).
# These are source-level guards on the two things that are easy to get wrong.


def _main_source() -> str:
    import inspect

    import src.main as m

    return inspect.getsource(m.main)


def test_dropped_leader_check_runs_at_startup_and_on_refresh():
    src = _main_source()
    assert 'check_dropped_leaders("startup")' in src
    assert 'check_dropped_leaders("refresh")' in src


def test_dropped_leader_check_is_fed_the_current_leader_set():
    """NOT `follower.addresses`. FillFollower.follow() has no unsubscribe, so
    that list only ever grows and can never reveal a dropped leader — feeding
    it here would silently reproduce the bug this check exists to catch."""
    src = _main_source()
    import re

    call = re.search(
        r"leader_reconciler\.check_dropped_leaders\(\s*(.*?)\s*\)", src, re.S
    )
    assert call is not None, "check_dropped_leaders is never called"
    assert call.group(1) == "[t.address for t in leaders]", call.group(1)
