#!/usr/bin/env bash
# shellcheck disable=SC2016  # the bash -c bodies are single-quoted on purpose
# T2 checks (pins, mirror, freshness): prints PASS|FAIL|WAIT lines, exits non-zero on any FAIL. Read-only apart from
# the offline unit tests (temporary folders) and `garage mirror --check` (reads the mirror).
# Usage: infra/checks/t2.sh
set -uo pipefail
[[ $EUID -eq 0 ]] || exec sudo -- "$0" "$@"
REPO=$(readlink -f "$(dirname "$(readlink -f "$0")")/../..")
cd /
GARAGE_HOME=${GARAGE_HOME:-/data/apps/garage}
PY=/opt/garage/venv/bin/python; [[ -x $PY ]] || PY=python3
pass=0 fail=0 wait=0
check() { local l=$1; shift; if "$@" >/dev/null 2>&1; then echo "PASS  $l"; pass=$((pass + 1)); else echo "FAIL  $l"; fail=$((fail + 1)); fi; }
later() { local l=$1; shift; if "$@" >/dev/null 2>&1; then echo "PASS  $l"; pass=$((pass + 1)); else echo "WAIT  $l"; wait=$((wait + 1)); fi; }
as_garage() { runuser -u garage -- env HOME=/var/lib/garage GARAGE_HOME="$GARAGE_HOME" GARAGE_REPO="$REPO_G" "$@"; }
gpy() { as_garage "$PY" -I -c "import sys; sys.path.insert(0, '$REPO_G/tools'); $1"; }
REPO_G=$GARAGE_HOME/repo   # what garage runs (the deployed copy; the dev tree under /home is not readable by garage)

echo "== disk"
check "/data/apps is btrfs @apps with zstd" bash -c '[[ $(findmnt -no FSTYPE,FSROOT /data/apps) == "btrfs /@apps" ]] && findmnt -no OPTIONS /data/apps | grep -q compress=zstd'
for d in mirror quarantine; do
  check "$d is a btrfs subvolume" btrfs subvolume show "$GARAGE_HOME/$d"
  check "$d is garage:garage 755" bash -c "[[ \$(stat -c %U:%G:%a $GARAGE_HOME/$d) == garage:garage:755 ]]"
done
snap_ok() {  # the newest @apps snapshot holds mirror/ and quarantine/ as empty folders while the live ones are not
  local s
  s=$(find /data/apps/.snapshots -mindepth 2 -maxdepth 2 -name snapshot 2>/dev/null | sort -V | tail -1)
  [[ -n $s && -d $s/garage/mirror && -z $(ls -A "$s/garage/mirror") && -z $(ls -A "$s/garage/quarantine") ]] &&
    [[ -n $(ls -A "$GARAGE_HOME/mirror") || -n $(ls -A "$GARAGE_HOME/quarantine") ]]
}
later "snapper @apps snapshots skip mirror/ and quarantine/ (nested subvolumes)" snap_ok

echo "== tools"
check "vendir 0.46.3" bash -c '[[ $(/usr/local/bin/vendir version | head -1) == "vendir version 0.46.3" ]]'
check "lychee 0.24.2" bash -c '[[ $(/usr/local/bin/lychee --version) == "lychee 0.24.2" ]]'
check "compsize" command -v compsize
later "garage has its own gh login" runuser -u garage -- env HOME=/var/lib/garage gh auth status --hostname github.com
check "/var/lib/garage is not world-readable" bash -c '[[ $(stat -c %a /var/lib/garage) == 750 ]]'

echo "== units"
for u in garage-sync.service garage-sync.timer garage-verify.service garage-verify.timer; do
  check "$u installed = repo copy" cmp -s "$REPO/infra/systemd/$u" "/etc/systemd/system/$u"
done
check "units pass systemd-analyze verify" bash -c '! systemd-analyze verify /etc/systemd/system/garage-{sync,verify}.service 2>&1 | grep -v lechu-alert | grep -q .'
check "units hardened (User=garage, ProtectSystem=strict, NoNewPrivileges, MemoryMax)" bash -c 'for u in sync verify; do f=/etc/systemd/system/garage-$u.service; grep -qx User=garage $f && grep -qx ProtectSystem=strict $f && grep -qx NoNewPrivileges=yes $f && grep -q ^MemoryMax= $f && grep -qx "ReadWritePaths=/data/apps/garage /var/lib/garage" $f || exit 1; done'
later "timers enabled (after the first full sync: GARAGE_TIMERS=1 20-mirror.sh units)" systemctl is-enabled garage-sync.timer garage-verify.timer

echo "== pins"
check "lock/pins.yaml validates against the schema rules" "$PY" -I -c "
import sys; sys.path.insert(0, '$REPO/tools')
import yaml
from garage import pins
d = yaml.safe_load(open('$REPO/lock/pins.yaml'))
assert len(d) > 3000 and not pins.validate(d)"
check "schema/pins.schema.json is valid JSON with the frozen fields" "$PY" -I -c "
import json; s = json.load(open('$REPO/schema/pins.schema.json'))
assert sorted(s['\$defs']['pin']['required']) == sorted(['repo','sha','path','pinned','license_at_pin','size_kb','policy'])"
check "offline tests (tests/t2)" bash -c "cd '$REPO' && sudo -u ${SUDO_USER:-lechuuu} python3 -I -m unittest discover -s tests/t2"

echo "== mirror"
if [[ -d $REPO_G/tools/garage && -f $REPO_G/tools/garage/mirror.py ]]; then
  check "no sha mismatch or tampered manifest in the mirror (garage mirror --check)" \
    gpy "from garage import mirror; sys.exit(mirror.main(['--check']))"
else
  echo "WAIT  deployed repo has no tools/garage/mirror.py yet (infra/install.sh --src)"; wait=$((wait + 1))
fi
check "no exec bits inside quarantine/" bash -c "[[ -z \$(find $GARAGE_HOME/quarantine -type f -perm /111 -print -quit) ]]"
check "every unit in mirror/ says location mirror" bash -c "! grep -L '\"location\": \"mirror\"' $GARAGE_HOME/mirror/*/*/.garage.json 2>/dev/null | grep -q ."
check "every unit in quarantine/ says location quarantine" bash -c "! grep -L '\"location\": \"quarantine\"' $GARAGE_HOME/quarantine/*/*/.garage.json 2>/dev/null | grep -q ."
check "no .git folders in the mirror" bash -c "[[ -z \$(find $GARAGE_HOME/mirror $GARAGE_HOME/quarantine -maxdepth 3 -name .git -print -quit) ]]"
later "mirror holds snapshots" bash -c "ls $GARAGE_HOME/mirror/*/current/.garage.json >/dev/null"

echo "T2: $pass passed, $fail failed, $wait waiting"
(( fail == 0 ))
