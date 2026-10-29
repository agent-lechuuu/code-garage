#!/usr/bin/env bash
# Install or update the Code Garage on a server (root; rerunnable):
#   1. the garage user and $GARAGE_HOME (install.d/10-base.sh user dirs, from this tree)
#   2. the repo in $GARAGE_HOME/repo: --src PATH copies a working tree (during the build), otherwise git clone/pull
#      of https://github.com/agent-lechuuu/code-garage as user garage (its own git credentials; while the repo is
#      private and garage has none, a one-shot credential from `lechu-secret show github TOKEN`, never stored)
#   3. every infra/install.d/NN-*.sh of the deployed repo, in order (each one idempotent)
# Usage: install.sh [--src PATH] [--only 10,40]
# Env: GARAGE_HOME (default /data/apps/garage), GARAGE_GIT_URL (default the GitHub repo).
set -euo pipefail
[[ $EUID -eq 0 ]] || exec sudo -- "$0" "$@"
HERE=$(dirname "$(readlink -f "$0")")
export GARAGE_HOME=${GARAGE_HOME:-/data/apps/garage}
export GARAGE_REPO=$GARAGE_HOME/repo
URL=${GARAGE_GIT_URL:-https://github.com/agent-lechuuu/code-garage}
SRC="" ONLY=""
while (( $# )); do
  case $1 in
    --src) SRC=$(readlink -f "$2"); shift 2 ;;
    --only) ONLY=$2; shift 2 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
log() { printf '\n== %s\n' "$*"; }

bash "$HERE/install.d/10-base.sh" user dirs

git_garage() {  # git as user garage, without prompts; falls back to the server's token while the repo is private
  if GIT_TERMINAL_PROMPT=0 runuser -u garage -- git ls-remote -q "$URL" HEAD >/dev/null 2>&1; then
    (cd "$GARAGE_HOME" && GIT_TERMINAL_PROMPT=0 runuser -u garage -- git "$@")
    return
  fi
  local tok
  tok=$(lechu-secret show github TOKEN 2>/dev/null) || tok=""
  [[ -n $tok ]] || { echo "  garage can't read $URL and there is no github TOKEN secret" >&2; return 1; }
  # The token travels in the environment of one git process owned by garage, never on a command line or on disk.
  # shellcheck disable=SC2016
  (cd "$GARAGE_HOME" && GARAGE_GIT_TOKEN=$tok GIT_TERMINAL_PROMPT=0 runuser -u garage -- git -c credential.helper= \
    -c 'credential.helper=!f() { echo username=x-access-token; echo "password=$GARAGE_GIT_TOKEN"; }; f' "$@")
}

if [[ -n $SRC ]]; then
  log "repo: copy of $SRC (build mode)"
  [[ -f $SRC/.claude-plugin/marketplace.json && -d $SRC/tools/garage ]] || { echo "  $SRC is not a code-garage tree" >&2; exit 1; }
  reg=$GARAGE_REPO/trust/registry.yaml
  if [[ -f $reg ]] && ! cmp -s "$reg" "$SRC/trust/registry.yaml"; then   # reviews made on the server: never lost
    install -d -o garage -g garage "$GARAGE_HOME/state/registry-backups"
    cp -p "$reg" "$GARAGE_HOME/state/registry-backups/registry.$(date +%Y%m%dT%H%M%S).yaml"
    echo "  WARNING: the server's trust/registry.yaml differs from $SRC's: kept a copy in state/registry-backups/" >&2
  fi
  rsync -a --delete --chown=garage:garage --chmod=go-w \
    --exclude .git --exclude __pycache__ --exclude '*.pyc' --exclude .pytest_cache --exclude .venv \
    "$SRC/" "$GARAGE_REPO/"
elif [[ -d $GARAGE_REPO/.git ]]; then
  log "repo: git pull ($URL)"
  # --rebase --autostash: local trust commits (garage review/promote, not pushed yet) stay on top, nothing is reset
  git_garage -c user.name=garage -c user.email=garage@localhost -C "$GARAGE_REPO" pull -q --rebase --autostash
else
  log "repo: git clone $URL"
  if [[ -n $(ls -A "$GARAGE_REPO") ]]; then
    echo "  $GARAGE_REPO holds files but no .git (a --src copy): move it away, then rerun" >&2; exit 1
  fi
  git_garage clone -q "$URL" "$GARAGE_REPO"
fi
echo "  $(find "$GARAGE_REPO" -type f -not -path '*/.git/*' | wc -l) files in $GARAGE_REPO"

for f in "$GARAGE_REPO"/infra/install.d/[0-9][0-9]-*.sh; do
  n=$(basename "$f"); n=${n%%-*}
  [[ -z $ONLY || ,$ONLY, == *,$n,* ]] || continue
  log "install.d/$(basename "$f")"
  bash "$f"
done
