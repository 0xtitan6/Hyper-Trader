# Sally gate — how to enable

`scripts/sally_gate.sh` is Sally as an ExecStartPre wrapper. Composes:
- `preflight_deploy.sh` (on main, not behind, tree clean, 1 engine)
- `invariant_check.py` (INV #12 mute, #5 zero-cap, #2 per-clearinghouse)
- ruff check + ruff format --check + pytest (60s cap)

Break-glass: `SALLY_OVERRIDE=1 SALLY_OVERRIDE_REASON="..."` — writes
`state/sally_override_<epoch>.json` audit + Telegram alert from the
wrapper itself.

## Do NOT wire live yet — current state is red

Ran it 2026-09-25 18:47Z. Findings:
1. Warren is on branch `exec/maker-shadow-harness`, not main.
2. Local main is 8 commits behind origin/main.
3. Uncommitted `config.yaml` diff (leader_exit_auto_close true→false).
4. ruff check + ruff format --check both fail.

Wiring as ExecStartPre now would refuse the next start of
`hyper-trader.service`. Any transient crash → permanent outage.

## Enable procedure (once above is clean)

Once branch is on main, tree is clean, ruff passes:

```bash
sudo systemctl edit hyper-trader
```

Add:
```
[Service]
ExecStartPre=/home/ec2-user/.openclaw/workspace/hyper-trader/scripts/sally_gate.sh
```

Then a scheduled window:
```bash
sudo systemctl daemon-reload
sudo systemctl restart hyper-trader
journalctl -u hyper-trader -f   # watch it come up clean
```

Verify by intentionally breaking one invariant, e.g. add a leader with
weight 0.30 in a temp config, `sudo systemctl restart hyper-trader`
must refuse and log the specific Sally failure.

## Break-glass drill

```bash
sudo systemctl edit hyper-trader --runtime
```

Add:
```
[Service]
Environment=SALLY_OVERRIDE=1
Environment=SALLY_OVERRIDE_REASON="drill: verify audit + telegram"
```

Then restart. Must accept, must write `state/sally_override_<epoch>.json`,
must fire Telegram. `--runtime` means override clears on next reboot.
