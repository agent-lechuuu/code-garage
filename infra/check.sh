#!/usr/bin/env bash
# Every track's checks: runs infra/checks/t*.sh in order. Each prints PASS|FAIL|WAIT lines; this script prints a total
# and exits 1 when any line is a FAIL (or a check script fails without printing one).
# Usage: check.sh [t1 t3 ...]   (no args = all)
set -uo pipefail
HERE=$(dirname "$(readlink -f "$0")")
pass=0 fail=0 wait=0
for f in "$HERE"/checks/t*.sh; do
  n=$(basename "$f" .sh)
  if (( $# )) && [[ " $* " != *" $n "* ]]; then continue; fi
  printf '\n== %s\n' "$n"
  out=$(bash "$f" 2>&1); rc=$?
  printf '%s\n' "$out"
  p=$(grep -c '^PASS' <<<"$out"); x=$(grep -c '^FAIL' <<<"$out"); w=$(grep -c '^WAIT' <<<"$out")
  if (( rc != 0 && x == 0 )); then echo "FAIL  $n exited $rc"; x=1; fi
  pass=$((pass + p)) fail=$((fail + x)) wait=$((wait + w))
done
printf '\n%d passed, %d failed, %d waiting\n' "$pass" "$fail" "$wait"
(( fail == 0 ))
