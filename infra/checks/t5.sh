#!/usr/bin/env bash
# T5 checks (search by meaning: garage.semantic, garage-embed.{socket,service}, the fusion in garage.search).
# Read-only except a temporary index for the measured comparison. Prints PASS|FAIL|WAIT lines; exits 1 on any FAIL.
# Usage: infra/checks/t5.sh [REPO]   (default: the checkout this script is in)
set -uo pipefail
REPO=$(readlink -f "${1:-$(dirname "$(readlink -f "$0")")/../..}")
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
GARAGE_HOME=${GARAGE_HOME:-/data/apps/garage}
SOCK=$GARAGE_HOME/run/embed.sock
VENV=/opt/garage/embed-venv
SEM=(env GARAGE_MODELS=/opt/garage/models GARAGE_HOME="$GARAGE_HOME" "$VENV/bin/python" -I -c
     'import runpy, sys; sys.path.insert(0, sys.argv[1]); sys.argv = ["garage.semantic"] + sys.argv[2:]
runpy.run_module("garage.semantic", run_name="__main__", alter_sys=True)' "$REPO/tools")

pass=0 fail=0 wait=0
check() {  # check "label" command...
  local label=$1; shift
  if "$@" >"$TMP/out" 2>&1; then echo "PASS  $label"; pass=$((pass + 1))
  else echo "FAIL  $label"; sed 's/^/      /' "$TMP/out" | head -8; fail=$((fail + 1)); fi
}
later() {  # evidence that shows up once infra/install.d/15-semantic.sh has run
  local label=$1; shift
  if "$@" >"$TMP/out" 2>&1; then echo "PASS  $label"; pass=$((pass + 1)); else echo "WAIT  $label"; wait=$((wait + 1)); fi
}

check "unit tests tests/t5 (vectors, fusion, filters, fall-back, answer cap, pins)" \
  env GARAGE_SEMANTIC=0 python3 -I -m unittest discover -s "$REPO/tests/t5" -t "$REPO/tests/t5"
check "search unchanged without a service (t1 owner needs, GARAGE_EMBED_SOCKET=/nonexistent)" \
  env GARAGE_EMBED_SOCKET=/nonexistent python3 -I -m unittest discover -s "$REPO/tests/t1" -t "$REPO/tests/t1" -k OwnerNeeds
later "embed venv $VENV with the exact pins" bash -c \
  "$VENV/bin/pip freeze --disable-pip-version-check | sort > '$TMP/frz' && grep -v '^#' '$REPO/infra/install.d/15-semantic.requirements.txt' | sort | diff - '$TMP/frz'"
later "model files match their sha256 (/opt/garage/models)" "${SEM[@]}" verify
later "garage-embed.socket enabled and listening, mode 0666" bash -c \
  "systemctl is-enabled --quiet garage-embed.socket && systemctl is-active --quiet garage-embed.socket &&
   [[ \$(stat -c %a '$SOCK') == 666 ]]"
later "service answers a query vector (socket activation)" bash -c \
  "GARAGE_HOME='$GARAGE_HOME' python3 -I -c \"import sys; sys.path.insert(0, '$REPO/tools')
from garage import semantic; r = semantic.ask({'op': 'query', 'q': 'ring buffer'}, timeout=15)
sys.exit(0 if r and len(r['v']) == 384 else 1)\""
later "service memory under its cap (MemoryMax=512M)" bash -c \
  "systemctl cat garage-embed.service >/dev/null && [[ \$(systemctl show -p MemoryMax --value garage-embed.service) == 536870912 ]] &&
   m=\$(systemctl show -p MemoryCurrent --value garage-embed.service) && [[ \$m == '[not set]' || \$m -lt 536870912 ]]"
later "deployed index has topic vectors" bash -c \
  "python3 -I -c \"import sqlite3, sys; c = sqlite3.connect('file:$GARAGE_HOME/index/garage.db?mode=ro', uri=True)
n = c.execute('select count(*) from vec').fetchone()[0]; t = c.execute(\\\"select count(*) from docs where src='topic'\\\").fetchone()[0]
print(n, t); sys.exit(0 if n and n >= 0.95 * t else 1)\""
later "tailnet container reaches the service through its read-only mount" bash -c \
  "sudo -n docker exec garage-mcp python -I -c \"import sys; sys.path.insert(0, '/data/apps/garage/repo/tools')
from garage import semantic; sys.exit(0 if semantic.ask({'op': 'ping'}, timeout=15) else 1)\""
later "measured: hybrid >= FTS on needs.yaml, +4 on plain words, owner needs kept (RealEval)" bash -c \
  "python3 -I -m unittest discover -s '$REPO/tests/t5' -t '$REPO/tests/t5' -k RealEval 2>&1 | tee '$TMP/eval' |
   grep -q '^OK\$' && ! grep -q 'skipped' '$TMP/eval'"
[[ -f $TMP/eval ]] && grep '^T5 ' "$TMP/eval" | sed 's/^/      /'

echo
echo "$pass passed, $fail failed$( (( wait )) && echo ", $wait not yet")"
(( fail == 0 ))
