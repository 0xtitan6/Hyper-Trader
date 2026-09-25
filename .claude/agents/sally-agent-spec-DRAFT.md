# Sally agent — spec (DRAFT, not yet wired)

Written 2026-09-25, session-close. Neil said "yeah sure" to build next session.

## What Sally does today (scripts, no LLM)
- `scripts/preflight_deploy.sh` — git hygiene gate
- `scripts/invariant_check.py` — config-parse invariants (INV #12/#5/#2)
- `scripts/sally_gate.sh` — composes both + ruff + pytest, break-glass via SALLY_OVERRIDE
- Tests: 801 pytest, covers KILL surfaces + zombie detection

## What Sally-agent would add (LLM, cron)
- Daily 06:00 UTC audit run (~10 min, ~200k tokens, ~$0.60/day)
- Reads: `state/tier1.log`, `state/jeff.alerts`, `state/escalations.log`, `state/sally_override_*.json`
- Runs: `sally_gate.sh` + inspects failures
- Proposes: new invariants when escalations reveal blind spots
- Escalates: via `scripts/escalate.sh sally orange "<summary>"`
- On-demand: also spawnable when tier1 fires or Warren wants to ship

## Prompt shape (borrow from quant-mm-analyst.md)
- Read-only on live code
- Cannot ship. Cannot commit. Proposes edits, Quorra approves.
- Report format ends with `## Verdict` (Clean / Blocked-fix-needed / Investigation)
- Under 3 min wallclock, under 300k tokens

## Wiring
- File: `.claude/agents/sally.md` (spec)
- Cron: systemd --user timer `hyper-sally-agent.timer` daily 06:00 UTC
- Runner: `scripts/run_sally_agent.sh` that invokes claude with the persona spec + reads
- Output: `state/sally/daily_<date>.md`
- Escalation: only if audit finds anything not-clean

## Cost & budget
- $0.60/day scheduled × 30 = $18/mo scheduled
- On-demand: 5-10 runs/mo × $0.30 = $3/mo
- Total: ~$21/mo — fits $100/mo budget with room

## Not doing this session
- Actual .claude/agents/sally.md spec (weekend work)
- systemd timer wiring
- Runner script
