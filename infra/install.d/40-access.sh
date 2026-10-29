#!/usr/bin/env bash
# Access for every Claude Code user on this server (root; idempotent; run by infra/install.sh):
# registers the `code-garage` marketplace (a `directory` source read in place: $GARAGE_HOME/repo) and force-enables
# `garage@code-garage` through managed settings, so each user gets the plugin at their next session, nothing per
# project. Claude Code reads /etc/claude-code/managed-settings.d/*.json after managed-settings.json (documented;
# both 2.1.310 and 2.1.312 here carry the code), so the garage gets its own drop-in and the main file is not touched.
# If a claude binary on this machine lacks drop-in support, the two keys are merged into managed-settings.json
# instead: backup first, existing bytes kept as they are, JSON checked before the file is replaced.
# Usage: 40-access.sh [install|remove|status]   (default install)
set -euo pipefail
[[ $EUID -eq 0 ]] || exec sudo -- "$0" "$@"
HERE=$(dirname "$(readlink -f "$0")")
GARAGE_HOME=${GARAGE_HOME:-/data/apps/garage}
GARAGE_REPO=${GARAGE_REPO:-$GARAGE_HOME/repo}
ETC=${GARAGE_CLAUDE_ETC:-/etc/claude-code}   # overridable for tests only
MAIN=$ETC/managed-settings.json
DROP=$ETC/managed-settings.d/50-garage.json
TEMPLATE=$HERE/../managed-settings/50-garage.json

binaries() {  # every Claude Code binary users run here
  local b
  for b in /usr/local/bin/claude /home/*/.local/bin/claude /usr/bin/claude; do
    [[ -e $b ]] && readlink -f "$b"
  done | sort -u
}

dropins_supported() {
  local b ok=1
  for b in $(binaries); do
    if python3 -Ic 'import sys; sys.exit(0 if b"managed-settings.d" in open(sys.argv[1], "rb").read() else 1)' "$b"; then
      echo "  drop-ins: $b reads managed-settings.d"
    else
      echo "  drop-ins: $b does NOT read managed-settings.d"; ok=0
    fi
  done
  (( ok ))
}

render() {  # the drop-in for this GARAGE_REPO, as JSON on stdout
  python3 -I - "$TEMPLATE" "$GARAGE_REPO" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
d["extraKnownMarketplaces"]["code-garage"]["source"]["path"] = sys.argv[2]
print(json.dumps(d, indent=2))
EOF
}

install_dropin() {
  local tmp
  install -d -m 755 -o root -g root "$ETC/managed-settings.d"
  tmp=$(mktemp "$ETC/managed-settings.d/.garage.XXXXXX")   # hidden while written: Claude Code skips dot files
  render >"$tmp"
  python3 -Ic 'import json, sys; d = json.load(open(sys.argv[1])); assert d["enabledPlugins"]["garage@code-garage"] is True' "$tmp"
  chmod 644 "$tmp"; chown root:root "$tmp"
  if [[ -f $DROP ]] && cmp -s "$tmp" "$DROP"; then rm -f "$tmp"; echo "  $DROP: unchanged"; return; fi
  mv -f "$tmp" "$DROP"
  echo "  $DROP: installed"
}

merge_main() {  # fallback: add the two keys to managed-settings.json, keeping every existing byte
  local bak tmp
  bak=$MAIN.bak-garage-$(date +%Y%m%d-%H%M%S)
  cp -a "$MAIN" "$bak"; echo "  backup: $bak"
  tmp=$(mktemp "$ETC/.managed-settings.XXXXXX")
  render >"$tmp"
  python3 -I - "$MAIN" "$tmp" <<'EOF'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
add = json.load(open(dst))
text = open(src).read()
old = json.loads(text)
for k, v in add.items():
    if k in old and old[k] != v:
        sys.exit(f"{src} already has a different {k}: merge it by hand")
add = {k: v for k, v in add.items() if k not in old}
if add:
    end = text.rstrip().rindex("}")
    body = ",\n".join(f'  "{k}": ' + json.dumps(v, indent=2).replace("\n", "\n  ") for k, v in add.items())
    text = text[:end].rstrip() + ",\n" + body + "\n}\n"
new = json.loads(text)
assert all(new[k] == v for k, v in old.items()), "existing keys changed"
open(dst, "w").write(text)
EOF
  chmod 644 "$tmp"; chown root:root "$tmp"
  if cmp -s "$tmp" "$MAIN"; then rm -f "$tmp" "$bak"; echo "  $MAIN: already has the garage keys"; return; fi
  mv -f "$tmp" "$MAIN"
  echo "  $MAIN: garage keys merged"
}

status() {
  [[ -f $DROP ]] && echo "  drop-in: $DROP" || echo "  drop-in: none"
  python3 -Ic 'import json, sys
for p in sys.argv[1:]:
    try:
        d = json.load(open(p))
    except FileNotFoundError:
        continue
    print(f"  {p}: keys {sorted(d)}")' "$MAIN" "$DROP"
}

case ${1:-install} in
  install)
    printf '\n== access: managed settings for every user (marketplace %s)\n' "$GARAGE_REPO"
    [[ -f $GARAGE_REPO/.claude-plugin/marketplace.json ]] || echo "  note: $GARAGE_REPO has no marketplace.json yet"
    if dropins_supported; then install_dropin; else merge_main; fi
    status ;;
  merge) merge_main ;;   # the fallback on its own (tests)
  remove)
    rm -f "$DROP"; echo "  removed $DROP (a merge into $MAIN, if any, stays: restore its .bak-garage-* by hand)" ;;
  status) status ;;
  *) sed -n '2,9p' "$0"; exit 2 ;;
esac
