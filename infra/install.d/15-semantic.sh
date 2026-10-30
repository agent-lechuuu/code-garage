#!/usr/bin/env bash
# Search by meaning on a server (root; idempotent; run by infra/install.sh). Optional: SEMANTIC=0 removes it again.
#   venv   /opt/garage/embed-venv (root-owned) with the exact pins in 15-semantic.requirements.txt; only the
#          embedding service uses it (the garage CLI, the MCP and the tailnet image stay on the base venv)
#   model  /opt/garage/models/all-MiniLM-L6-v2/<revision>: pinned files from Hugging Face, each checked by sha256
#   units  garage-embed.socket (enabled) + garage-embed.service (socket activated, exits after an hour idle)
#   index  `garage index` as user garage, so the topics get their vectors now (garage-sync keeps them current)
# Usage: 15-semantic.sh [section...]   (no args = all: venv model units index)
set -euo pipefail
[[ $EUID -eq 0 ]] || exec sudo -- "$0" "$@"
HERE=$(dirname "$(readlink -f "$0")")
INFRA=$(dirname "$HERE")
TOOLS=$(dirname "$INFRA")/tools
GARAGE_HOME=${GARAGE_HOME:-/data/apps/garage}
VENV=/opt/garage/embed-venv
MODELS=/opt/garage/models
log() { printf '\n== %s\n' "$*"; }
py() { GARAGE_MODELS=$MODELS GARAGE_HOME=$GARAGE_HOME "$VENV/bin/python" -I -c \
  'import runpy, sys; sys.path.insert(0, sys.argv[1]); sys.argv = ["garage.semantic"] + sys.argv[2:]
runpy.run_module("garage.semantic", run_name="__main__", alter_sys=True)' "$TOOLS" "$@"; }

sec_venv() {
  log "venv: $VENV (pinned: 15-semantic.requirements.txt)"
  install -d -m 755 /opt/garage
  [[ -x $VENV/bin/python ]] || python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --disable-pip-version-check --no-input --only-binary :all: \
    -r "$HERE/15-semantic.requirements.txt"
  "$VENV/bin/pip" check -q >/dev/null
  chmod -R go-w "$VENV"
  "$VENV/bin/python" -I -c 'import importlib.metadata as m; print("  ok", *(f"{p} {m.version(p)}" for p in ("numpy", "onnxruntime", "tokenizers")))'
}

sec_model() {
  log "model: $MODELS (sha256 checked)"
  install -d -m 755 "$MODELS"
  py fetch | sed 's/^/  /'
  py verify | sed 's/^/  /'
  chmod -R a+rX,go-w "$MODELS"
}

sec_units() {
  log "units: garage-embed.socket, garage-embed.service"
  local u changed=0
  for u in garage-embed.socket garage-embed.service; do
    if ! cmp -s "$INFRA/systemd/$u" "/etc/systemd/system/$u"; then
      install -m 644 "$INFRA/systemd/$u" /etc/systemd/system/
      changed=1
    fi
  done
  systemctl daemon-reload
  systemd-analyze verify /etc/systemd/system/garage-embed.{socket,service} 2>&1 | sed 's/^/  /' || true
  if [[ ! -f $GARAGE_HOME/repo/tools/garage/semantic.py ]]; then   # the service runs the deployed code
    echo "  $GARAGE_HOME/repo has no garage/semantic.py yet: units installed, socket not enabled (rerun after deploy)"
    return
  fi
  systemctl enable --now garage-embed.socket
  # new code or unit: the running service (if any) picks it up at its next start
  if (( changed )) || [[ ${GARAGE_EMBED_RESTART:-0} == 1 ]]; then systemctl try-restart garage-embed.service; fi
  py status --socket "$GARAGE_HOME/run/embed.sock" | sed 's/^/  /'
}

sec_index() {
  log "index: vectors for the topics (garage index as garage)"
  if [[ ! -x /usr/local/bin/garage ]]; then echo "  no /usr/local/bin/garage yet (10-base.sh wrappers): skipped"; return; fi
  (cd / && runuser -u garage -- env GARAGE_HOME="$GARAGE_HOME" /usr/local/bin/garage index --json) |
    python3 -I -c 'import json, sys; d = json.load(sys.stdin); print("  %s rows, %s vectors (%s new), %s s" % (d["rows"], d.get("vectors"), d.get("vectors_new"), d["seconds"]))'
}

sec_remove() {
  log "remove: search by meaning off (the garage works as before: keyword search)"
  systemctl disable --now garage-embed.socket garage-embed.service 2>/dev/null || true
  rm -f /etc/systemd/system/garage-embed.{socket,service}
  systemctl daemon-reload
  rm -rf "$VENV" "$MODELS"
}

sections=("$@")
if (( ! ${#sections[@]} )); then
  if [[ ${SEMANTIC:-1} == 0 ]]; then sections=(remove); else sections=(venv model units index); fi
fi
for s in "${sections[@]}"; do "sec_$s"; done
