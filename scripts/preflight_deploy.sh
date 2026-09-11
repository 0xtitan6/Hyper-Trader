#!/usr/bin/env bash
# Deploy-target assertion. Run BEFORE any restart of the live engine.
#
# 2026-09-11: the working tree was left checked out on a PR branch for days.
# The live engine ran from it, and the strategist committed its config changes
# there instead of main. Nothing was broken, but main stopped being the source
# of truth -- which is how a surprise gets staged for later.
#
# Exit non-zero = do NOT deploy.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2
fail=0

b=$(git branch --show-current)
if [ "$b" != "main" ]; then
  echo "FAIL  on branch '$b', expected main"; fail=1
else
  echo "ok    on main"
fi

git fetch origin -q 2>/dev/null
read -r behind ahead < <(git rev-list --left-right --count origin/main...main 2>/dev/null | awk '{print $1, $2}')
if [ "${behind:-0}" != "0" ]; then
  echo "FAIL  local main is $behind behind origin/main -- pull first"; fail=1
else
  echo "ok    not behind origin"
fi
[ "${ahead:-0}" != "0" ] && echo "warn  $ahead unpushed commit(s) -- push after deploying"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "FAIL  uncommitted tracked changes -- commit or stash"; fail=1
else
  echo "ok    working tree clean"
fi

n=$(ps -eo pid,cmd | grep '[s]rc.main' | wc -l)
if [ "$n" -gt 1 ]; then
  echo "FAIL  $n engines running -- DOUBLE RUN, stop before restarting"; fail=1
else
  echo "ok    $n engine running"
fi

[ $fail -eq 0 ] && echo "DEPLOY OK" || echo "DEPLOY BLOCKED"
exit $fail
