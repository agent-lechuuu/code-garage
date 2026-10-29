#!/usr/bin/env bash
# T1 checks (catalog, garage CLI core, search, generated INDEX/dist, CI). Read-only on the repo; builds a throwaway
# index in a temporary GARAGE_HOME to measure. Prints PASS|FAIL|WAIT lines; exits 1 on any FAIL.
# Usage: infra/checks/t1.sh [REPO]   (default: the checkout this script is in)
set -uo pipefail
REPO=$(readlink -f "${1:-$(dirname "$(readlink -f "$0")")/../..}")
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
export GARAGE_REPO=$REPO GARAGE_HOME=$TMP/home
# The deployed repo belongs to user garage; run as anyone else (root via sudo, lechuuu) git refuses it as "dubious
# ownership". Trust this one repo for this script's git calls only (command-line scope, nothing written to a config).
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=$REPO
G=(python3 -I "$REPO/tools/garage")

pass=0 fail=0 wait=0
check() {  # check "label" command...
  local label=$1; shift
  if "$@" >"$TMP/out" 2>&1; then echo "PASS  $label"; pass=$((pass + 1))
  else echo "FAIL  $label"; sed 's/^/      /' "$TMP/out" | head -8; fail=$((fail + 1)); fi
}
later() {  # evidence that shows up once the other tracks / the install have run
  local label=$1; shift
  if "$@" >/dev/null 2>&1; then echo "PASS  $label"; pass=$((pass + 1)); else echo "WAIT  $label"; wait=$((wait + 1)); fi
}

check "catalog valid: schema, unique ids, see_also, policy (garage validate)" "${G[@]}" validate
check "INDEX.md and dist/ are fresh (garage build --check)" "${G[@]}" build --check
check "unit tests tests/t1" python3 -I -m unittest discover -s "$REPO/tests/t1"
if command -v yamllint >/dev/null; then
  check "yamllint catalog/" yamllint --strict -d "{extends: relaxed, rules: {line-length: disable, truthy: disable}}" \
    "$REPO/catalog"
fi
check "repo guard: nothing in git that shouldn't be" bash -c \
  "set -o pipefail; cd '$REPO' && git ls-files -z --cached --others --exclude-standard | grep -zv '__pycache__/' \
   | xargs -0 ${G[*]} validate --guard"
check "workflow actions pinned by commit sha" bash -c \
  "! grep -E '^\s*-?\s*uses:' '$REPO/.github/workflows/validate.yml' | grep -vE '@[0-9a-f]{40}(\s|$)'"
check "pyproject: scripts garage + garage-mcp, exact pins" python3 -I - "$REPO/pyproject.toml" <<'PY'
import re, sys, tomllib
p = tomllib.load(open(sys.argv[1], "rb"))
assert p["project"]["scripts"] == {"garage": "garage.cli:main", "garage-mcp": "garage.mcp_server:main"}
assert all(re.fullmatch(r"[A-Za-z0-9_.-]+==[0-9][\w.]*", d) for d in p["project"]["dependencies"])
assert all("==" in r for r in p["build-system"]["requires"])
PY

check "index builds from scratch in < 60 s" python3 -I - "$REPO" <<'PY'
import sys, time
sys.path.insert(0, sys.argv[1] + "/tools")
from garage import index
s = index.build()
print(s)
assert s["seconds"] < 60, s
print(f"index: {s['rows']} rows, {s['kb']} kB, {s['seconds']} s", file=sys.stderr)
PY
echo "      $(sed -n 's/^index: /index: /p' "$TMP/out" 2>/dev/null)"
check "search: median < 10 ms, every answer <= 3 KB, the obvious topic first" python3 -I - "$REPO" <<'PY'
import json, sys, time
sys.path.insert(0, sys.argv[1] + "/tools")
from garage import search
qs = ["headless dialog react", "postgres migration linter", "mcp server for github", "auth", "rate limiting",
      "vector database", "background jobs node", "s3 upload", "date picker", "playwright e2e", "password hashing",
      "terraform modules", "kubernetes ingress", "oauth library python", "pdf generation", "react charts"]
for q in qs:
    search.search(q)
ms, size = [], []
for q in qs:
    t = time.perf_counter()
    r = search.search(q)
    ms.append((time.perf_counter() - t) * 1000)
    size.append(len(json.dumps(r).encode()))
ms.sort()
print(f"search: median {ms[len(ms) // 2]:.1f} ms, max {ms[-1]:.1f} ms; answers {min(size)}-{max(size)} B")
assert ms[len(ms) // 2] < 10 and max(size) <= 3072
assert search.search("postgres migration linter")[0]["id"] == "backend.safe-db.migration-linters"
PY
echo "      $(grep '^search:' "$TMP/out")"

echo "== deployed"
later "/usr/local/bin/garage answers (search --json)" bash -c \
  "env -u GARAGE_REPO -u GARAGE_HOME /usr/local/bin/garage search --json headless dialog | python3 -I -c 'import json,sys; assert json.load(sys.stdin)'"
later "deployed index /data/apps/garage/index/garage.db exists" test -s /data/apps/garage/index/garage.db
later "deployed doctor has no FAIL" bash -c "env -u GARAGE_REPO -u GARAGE_HOME /usr/local/bin/garage doctor"

printf '\nt1: %d passed, %d failed, %d waiting\n' "$pass" "$fail" "$wait"
(( fail == 0 ))
