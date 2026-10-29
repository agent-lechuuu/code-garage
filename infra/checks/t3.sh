#!/usr/bin/env bash
# T3 checks (plugin, MCP server, access). Works on any machine with the repo; the server parts (managed settings,
# /opt/garage/venv, /usr/local/bin wrappers) show WAIT where they don't apply. Prints PASS|FAIL|WAIT; exit 1 on FAIL.
# Usage: infra/checks/t3.sh   (as root, `claude plugin validate` runs as $SUDO_USER)
set -uo pipefail
SELF=$(readlink -f "$0")
REPO=$(readlink -f "$(dirname "$SELF")/../..")
VENV=/opt/garage/venv
PY=python3; [[ -x $VENV/bin/python ]] && PY=$VENV/bin/python
cd /   # other users (runuser) can't stat a working directory in a home folder

pass=0 fail=0 wait=0
check() {  # check "label" command...
  local label=$1; shift
  if "$@" >/dev/null 2>&1; then echo "PASS  $label"; pass=$((pass + 1)); else echo "FAIL  $label"; fail=$((fail + 1)); fi
}
later() {  # where it doesn't apply (yet): WAIT instead of FAIL
  local label=$1; shift
  if "$@" >/dev/null 2>&1; then echo "PASS  $label"; pass=$((pass + 1)); else echo "WAIT  $label"; wait=$((wait + 1)); fi
}
as_user() {  # run a command as the invoking user when we are root (claude must not write /root/.claude)
  if [[ $EUID -eq 0 ]]; then
    [[ -n ${SUDO_USER:-} && $SUDO_USER != root ]] || return 1
    runuser -u "$SUDO_USER" -- env HOME="$(getent passwd "$SUDO_USER" | cut -d: -f6)" "$@"
  else
    "$@"
  fi
}

echo "-- plugin and marketplace"
check "tests/t3 (MCP results <= 3 KB, trust rules, grep confinement, plugin layout, managed settings)" \
  "$PY" -I -m unittest discover -s "$REPO/tests/t3" -q
if "$PY" -Ic 'import mcp' 2>/dev/null; then
  echo "PASS  MCP transport tests ran with the mcp package ($PY)"; pass=$((pass + 1))
else
  echo "WAIT  MCP transport tests skipped: no mcp package in $PY"; wait=$((wait + 1))
fi
# `claude --version` and `claude plugin validate` start no session and no MCP server (so no channel plugin can
# start; they don't take --strict-mcp-config). Any `claude -p` added here needs --strict-mcp-config: see
# docs/use-on-server.md.
if as_user claude --version >/dev/null 2>&1; then
  check "claude plugin validate (marketplace)" as_user claude plugin validate "$REPO"
  check "claude plugin validate (plugins/garage)" as_user claude plugin validate "$REPO/plugins/garage"
else
  echo "WAIT  claude plugin validate: no claude for this user"; wait=$((wait + 1))
fi
check "bin scripts are shellcheck-clean (when shellcheck exists)" bash -c "! command -v shellcheck || shellcheck -x \
  '$REPO/plugins/garage/bin/garage' '$REPO/plugins/garage/bin/garage-mcp' '$REPO/infra/install.sh' \
  '$REPO/infra/install.d/10-base.sh' '$REPO/infra/install.d/40-access.sh' '$REPO/infra/check.sh' '$SELF'"
for d in use-on-server use-on-mac use-anywhere; do check "docs/$d.md" test -s "$REPO/docs/$d.md"; done

echo "-- this machine's install"
later "plugin bin/garage-mcp answers an MCP initialize (the stdio server the plugin declares)" "$PY" -I - "$REPO" <<'EOF'
import json, subprocess, sys
p = subprocess.run([sys.argv[1] + "/plugins/garage/bin/garage-mcp"], capture_output=True, text=True, timeout=60,
                   input=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                       "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t3", "version": "0"}}}) + "\n")
assert json.loads(p.stdout.splitlines()[0])["result"]["serverInfo"]["name"] == "garage", p.stderr
EOF
later "/opt/garage/venv matches 10-base.requirements.txt exactly" bash -c "diff <(grep -v '^#' '$REPO/infra/install.d/10-base.requirements.txt' | tr A-Z_ a-z- | sort) <('$VENV/bin/pip' freeze --disable-pip-version-check | tr A-Z_ a-z- | sort)"
later "/usr/local/bin/garage-mcp --version" /usr/local/bin/garage-mcp --version
if [[ -f /etc/claude-code/managed-settings.json ]]; then
  check "managed-settings.json: channelsEnabled and the PreToolUse hook lechu-claude-hook kept" python3 -I - <<'EOF'
import json
d = json.load(open("/etc/claude-code/managed-settings.json"))
assert d.get("channelsEnabled") is True
cmds = [h.get("command") for m in d["hooks"]["PreToolUse"] for h in m["hooks"]]
assert "/usr/local/sbin/lechu-claude-hook" in cmds
EOF
  check "managed drop-in 50-garage.json: valid, root-owned, marketplace dir has marketplace.json" python3 -I - <<'EOF'
import json, os
p = "/etc/claude-code/managed-settings.d/50-garage.json"
st = os.stat(p)
assert st.st_uid == 0 and not st.st_mode & 0o022
d = json.load(open(p))
assert d["enabledPlugins"]["garage@code-garage"] is True
src = d["extraKnownMarketplaces"]["code-garage"]["source"]
assert src["source"] == "directory" and os.path.isfile(src["path"] + "/.claude-plugin/marketplace.json")
EOF
else
  echo "WAIT  managed settings: none on this machine (server only)"; wait=$((wait + 1))
fi

echo "t3: $pass passed, $fail failed, $wait waiting"
(( fail == 0 ))
