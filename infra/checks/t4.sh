#!/usr/bin/env bash
# T4 checks (safety: scanners, trust, policy, review/promote, the assistant's quarantine guard). Read-only; the
# planted fixture is only read by the scanners. Prints PASS|FAIL|WAIT lines; exits 1 on any FAIL.
# Usage: infra/checks/t4.sh [REPO]   (default: the checkout this script is in)
set -uo pipefail
REPO=$(readlink -f "${1:-$(dirname "$(readlink -f "$0")")/../..}")
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
G=(python3 -I "$REPO/tools/garage")
FX=$REPO/tests/t4/fixtures

pass=0 fail=0 wait=0
check() {  # check "label" command...
  local label=$1; shift
  if "$@" >"$TMP/out" 2>&1; then echo "PASS  $label"; pass=$((pass + 1))
  else echo "FAIL  $label"; sed 's/^/      /' "$TMP/out" | head -8; fail=$((fail + 1)); fi
}
later() {  # evidence that shows up once the install / the other tracks have run
  local label=$1; shift
  if "$@" >/dev/null 2>&1; then echo "PASS  $label"; pass=$((pass + 1)); else echo "WAIT  $label"; wait=$((wait + 1)); fi
}
hook() {  # hook JSON -> the installed hook's answer, as user claude (needs sudo)
  printf '%s' "$1" | (cd / && sudo -n -u claude -H env LECHU_JOB=garage-t4-check LECHU_JOB_CLASS=p1 \
    /usr/local/sbin/lechu-claude-hook)
}

check "unit tests tests/t4 (trust, policy, scan, review, promote)" \
  python3 -I -m unittest discover -s "$REPO/tests/t4" -t "$REPO/tests/t4"
check "trust registry valid and policy clean (trust + policy modules)" python3 -I -c "
import sys; sys.path.insert(0, '$REPO/tools')
import os; os.environ['GARAGE_REPO'] = '$REPO'
from garage import catalog, pins, policy, trust
errs = trust.validate(trust.load()) + [e for e in policy.check(catalog.load(), pins.all(), trust.load())
                                        if e.split(':')[0] in trust.load()]
print('\n'.join(errs)); sys.exit(1 if errs else 0)"
check "no trusted record without an owner approval id" python3 -I -c "
import sys, yaml; reg = yaml.safe_load(open('$REPO/trust/registry.yaml')) or {}
bad = [r for r, x in reg.items() if x.get('trust') == 'trusted' and not (x.get('approved_by') == 'owner'
       and isinstance(x.get('approval'), int))]
print(bad); sys.exit(1 if bad else 0)"
check "planted malicious fixture fails the scan (own checks; scanners if installed)" bash -c \
  "! ${G[*]} scan --path '$FX/evil-skill' --kind skill > '$TMP/evil.txt' && grep -q 'garage-checks.*fail' '$TMP/evil.txt'"
check "clean fixture passes the scan" "${G[@]}" scan --path "$FX/clean-skill" --kind skill
later "scanners installed (/opt/garage/scanners: skillspector, aguara, mcp-scanner, gitleaks)" bash -c \
  "test -x /opt/garage/scanners/venv/bin/skillspector && test -x /opt/garage/scanners/bin/aguara &&
   test -x /opt/garage/scanners/venv/bin/mcp-scanner && test -x /opt/garage/scanners/bin/gitleaks"
later "all required scanners ran on the fixture (none skipped)" bash -c \
  "grep -E '^  (skillspector|aguara|gitleaks) ' '$TMP/evil.txt' | grep -vqE 'skipped|error' &&
   ! grep -E '^  (skillspector|aguara|gitleaks) ' '$TMP/evil.txt' | grep -qE 'skipped|error'"
later "scanners run in bubblewrap as user garage (read-only, no network)" bash -c \
  "cd / && sudo -n -u garage bwrap --ro-bind / / --dev /dev --proc /proc --tmpfs /tmp --unshare-net --die-with-parent \
   sh -c '! touch /var/lib/garage/x 2>/dev/null && ! getent ahosts github.com >/dev/null'"
check "promote --dry-run builds the card and sends nothing" bash -c \
  "GARAGE_LECHU_ASK=/nonexistent ${G[*]} promote --propose --dry-run >/dev/null"
if [[ -x /usr/local/sbin/lechu-claude-hook ]]; then
  later "installed hook denies python3 /data/apps/garage/quarantine/x/y.py for claude" bash -c \
    "$(declare -f hook); hook '{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"python3 /data/apps/garage/quarantine/x/y.py\"},\"cwd\":\"/srv/brain\"}' | grep -q 'quarantine'"
  later "installed hook allows a normal command and reading the quarantine" bash -c \
    "$(declare -f hook); ! hook '{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"ls -la\"},\"cwd\":\"/srv/brain\"}' | grep -q deny &&
     ! hook '{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"cat /data/apps/garage/quarantine/a/SKILL.md\"},\"cwd\":\"/srv/brain\"}' | grep -q deny"
  later "approval kind garage.promote in /etc/lechu/approvals.yaml" grep -q '^  garage.promote:' /etc/lechu/approvals.yaml
  later "garage-review job in /etc/lechu/jobs.yaml" grep -q '^  garage-review:' /etc/lechu/jobs.yaml
  later "garage-promote.service installed (timer enabled only with --enable-promote)" \
    test -f /etc/systemd/system/garage-promote.service
  later "review inbox writable by group claude" bash -c \
    "[[ \$(stat -c %G:%a /data/apps/garage/state/review-inbox) == claude:2775 ]]"
fi

echo
echo "$pass passed, $fail failed$( (( wait )) && echo ", $wait not yet")"
(( fail == 0 ))
