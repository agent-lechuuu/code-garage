#!/usr/bin/env bash
# Base of the Code Garage on a server (root; idempotent; run by infra/install.sh):
#   user     system user + group `garage` (no sudo, no login shell, home /var/lib/garage)
#   dirs     $GARAGE_HOME/{repo,index,state}, owned by garage, world-readable (no secrets in there)
#   venv     /opt/garage/venv (root-owned) with the exact pins in 10-base.requirements.txt
#   wrappers /usr/local/bin/garage and /usr/local/bin/garage-mcp (the package in $GARAGE_HOME/repo/tools + the venv)
# Usage: 10-base.sh [section...]   (no args = all)
set -euo pipefail
[[ $EUID -eq 0 ]] || exec sudo -- "$0" "$@"
HERE=$(dirname "$(readlink -f "$0")")
GARAGE_HOME=${GARAGE_HOME:-/data/apps/garage}
VENV=/opt/garage/venv
log() { printf '\n== %s\n' "$*"; }

sec_user() {
  log "user: garage"
  getent group garage >/dev/null || groupadd --system garage
  if ! id garage >/dev/null 2>&1; then
    useradd --system --gid garage --home-dir /var/lib/garage --create-home --shell /usr/sbin/nologin \
      --comment "Code Garage (sync, index)" garage
  fi
  install -d -m 750 -o garage -g garage /var/lib/garage
  id garage | sed 's/^/  /'
}

sec_dirs() {
  log "dirs: $GARAGE_HOME"
  install -d -m 755 -o garage -g garage "$GARAGE_HOME"
  local d
  for d in repo index state; do install -d -m 755 -o garage -g garage "$GARAGE_HOME/$d"; done
  stat -c '  %A %U:%G %n' "$GARAGE_HOME" "$GARAGE_HOME"/{repo,index,state}
}

sec_venv() {
  log "venv: $VENV (pinned: 10-base.requirements.txt)"
  install -d -m 755 /opt/garage
  [[ -x $VENV/bin/python ]] || python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --disable-pip-version-check --no-input -r "$HERE/10-base.requirements.txt"
  "$VENV/bin/pip" check -q >/dev/null
  install -m 644 "$HERE/10-base.requirements.txt" /opt/garage/requirements.txt
  chmod -R go-w /opt/garage
  "$VENV/bin/python" -I -c 'import importlib.metadata as m; print("  ok mcp", m.version("mcp"), "PyYAML", m.version("PyYAML"))'
}

wrapper() {  # wrapper NAME MODULE
  local tmp
  tmp=$(mktemp)
  cat >"$tmp" <<EOF
#!/bin/sh
# $1: Code Garage (installed by code-garage infra/install.d/10-base.sh; the code is \$GARAGE_REPO/tools).
: "\${GARAGE_HOME:=$GARAGE_HOME}"
export GARAGE_HOME
exec $VENV/bin/python -I -c '
import runpy, sys
sys.path.insert(0, sys.argv[1])
sys.argv = ["$1"] + sys.argv[2:]
runpy.run_module("$2", run_name="__main__", alter_sys=True)' "\${GARAGE_REPO:-\$GARAGE_HOME/repo}/tools" "\$@"
EOF
  install -m 755 "$tmp" "/usr/local/bin/$1"
  rm -f "$tmp"
}

sec_wrappers() {
  log "wrappers: /usr/local/bin/garage, /usr/local/bin/garage-mcp"
  wrapper garage garage
  wrapper garage-mcp garage.mcp_server
  /usr/local/bin/garage-mcp --version | sed 's/^/  /'
}

sections=("$@")
(( ${#sections[@]} )) || sections=(user dirs venv wrappers)
for s in "${sections[@]}"; do "sec_$s"; done
