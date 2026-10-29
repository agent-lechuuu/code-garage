#!/usr/bin/env bash
# The mirror of the Code Garage (root; idempotent; run by infra/install.sh after 10-base.sh):
#   disk     $GARAGE_HOME/{mirror,quarantine} as nested btrfs subvolumes of @apps (snapper's @apps snapshots skip
#            nested subvolumes, so 15-30 GB of upstream snapshots never land in the hourly timeline), zstd from the mount
#   tools    vendir (Carvel) and lychee (link checker) at exact versions, sha256 verified; compsize (apt)
#   github   user garage's own gh login (token from `lechu-secret show github TOKEN`, as 55-brain.sh does for claude),
#            stored in /var/lib/garage (mode 750, outside the world-readable $GARAGE_HOME)
#   units    garage-sync.{service,timer} (daily) and garage-verify.{service,timer} (Sun 04:30), installed always;
#            the timers are enabled only once asked: GARAGE_TIMERS=1 20-mirror.sh (remembered in state/timers.enabled),
#            so the first full sync stays a deliberate step
# Usage: 20-mirror.sh [section...]   (no args = all: disk tools github units)
set -euo pipefail
[[ $EUID -eq 0 ]] || exec sudo -- "$0" "$@"
HERE=$(dirname "$(readlink -f "$0")")
INFRA=$(readlink -f "$HERE/..")
GARAGE_HOME=${GARAGE_HOME:-/data/apps/garage}
VENDIR_VERSION=0.46.3
VENDIR_SHA256=5af8823ecc67b3ce2359bb0b70e72a5dbd765135722ca0ff42c16bc4d7409847   # vendir-linux-amd64, checksums.txt
LYCHEE_VERSION=0.24.2
LYCHEE_SHA256=1f4e0ef7f6554a6ed33dd7ac144fb2e1bbed98598e7af973042fc5cd43951c9a   # lychee-x86_64-unknown-linux-gnu.tar.gz
log() { printf '\n== %s\n' "$*"; }
die() { echo "  $*" >&2; exit 1; }

sec_disk() {
  log "disk: $GARAGE_HOME/{mirror,quarantine} as nested btrfs subvolumes"
  local apps=/data/apps
  [[ $(findmnt -no FSTYPE "$apps") == btrfs ]] || die "$apps is not btrfs"
  findmnt -no FSROOT "$apps" | grep -qx '/@apps' || die "$apps is not the @apps subvolume"
  findmnt -no OPTIONS "$apps" | grep -q 'compress=zstd' || echo "  note: $apps is mounted without compress=zstd"
  getent group garage >/dev/null || groupadd --system garage   # normally 10-base.sh made these
  id garage >/dev/null 2>&1 || useradd --system --gid garage --home-dir /var/lib/garage --create-home \
    --shell /usr/sbin/nologin --comment "Code Garage (sync, index)" garage
  install -d -m 750 -o garage -g garage /var/lib/garage
  install -d -m 755 -o garage -g garage "$GARAGE_HOME" "$GARAGE_HOME/state" "$GARAGE_HOME/index"
  # garage-sync runs `garage mirror` and `garage index` as garage: whatever root left there becomes garage's
  find "$GARAGE_HOME/index" "$GARAGE_HOME/state" \! -user garage -exec chown -h garage:garage {} +
  local d p
  for d in mirror quarantine; do
    p=$GARAGE_HOME/$d
    if [[ -d $p ]] && ! btrfs subvolume show "$p" >/dev/null 2>&1; then
      [[ -z $(ls -A "$p") ]] || die "$p is a plain folder with files: move them away, then rerun"
      rmdir "$p"
    fi
    [[ -d $p ]] || btrfs subvolume create "$p" >/dev/null
    chown garage:garage "$p"
    chmod 755 "$p"
    printf '  %s  subvolume id %s, %s\n' "$p" "$(btrfs subvolume show "$p" | awk '/Subvolume ID:/ {print $3}')" \
      "$(stat -c '%A %U:%G' "$p")"
  done
  # Nested subvolumes are not part of a snapshot of their parent: snapper's @apps snapshots hold an empty folder.
  if snapper -c apps get-config >/dev/null 2>&1; then
    echo "  snapper config apps covers $apps; nested subvolumes stay out of its snapshots (t2.sh checks the next one)"
  fi
}

fetch_verified() {  # fetch_verified URL SHA256 DEST
  local tmp
  tmp=$(mktemp)
  curl -fsSL --retry 3 -o "$tmp" "$1"
  if ! echo "$2  $tmp" | sha256sum -c --quiet -; then rm -f "$tmp"; die "checksum mismatch for $1"; fi
  mv "$tmp" "$3"
}

sec_tools() {
  log "tools: vendir $VENDIR_VERSION, lychee $LYCHEE_VERSION, compsize"
  if [[ $(/usr/local/bin/vendir version 2>/dev/null | head -1) != "vendir version $VENDIR_VERSION" ]]; then
    fetch_verified "https://github.com/carvel-dev/vendir/releases/download/v$VENDIR_VERSION/vendir-linux-amd64" \
      "$VENDIR_SHA256" /tmp/vendir.$$
    install -m 755 /tmp/vendir.$$ /usr/local/bin/vendir
    rm -f /tmp/vendir.$$
  fi
  echo "  $(/usr/local/bin/vendir version | head -1)"
  if [[ $(/usr/local/bin/lychee --version 2>/dev/null) != "lychee $LYCHEE_VERSION" ]]; then
    local t
    t=$(mktemp -d)
    fetch_verified "https://github.com/lycheeverse/lychee/releases/download/lychee-v$LYCHEE_VERSION/lychee-x86_64-unknown-linux-gnu.tar.gz" \
      "$LYCHEE_SHA256" "$t/l.tgz"
    tar -xzf "$t/l.tgz" -C "$t" lychee-x86_64-unknown-linux-gnu/lychee
    install -m 755 "$t/lychee-x86_64-unknown-linux-gnu/lychee" /usr/local/bin/lychee
    rm -rf "$t"
  fi
  echo "  $(/usr/local/bin/lychee --version)"
  command -v compsize >/dev/null || NEEDRESTART_SUSPEND=1 DEBIAN_FRONTEND=noninteractive apt-get install -y -qq btrfs-compsize >/dev/null
  echo "  compsize $(dpkg-query -W -f '${Version}' btrfs-compsize)"
}

sec_github() {
  log "github: gh login for user garage (verify PRs, git pull of the private repo)"
  cd /
  local as=(runuser -u garage -- env HOME=/var/lib/garage)
  if "${as[@]}" gh auth status --hostname github.com >/dev/null 2>&1; then
    echo "  already logged in"
  elif lechu-secret show github TOKEN >/dev/null 2>&1; then
    lechu-secret show github TOKEN | "${as[@]}" gh auth login --hostname github.com --git-protocol https --with-token
    "${as[@]}" gh auth setup-git --hostname github.com
  else
    echo "  no github TOKEN secret yet (sudo lechu-secret set github TOKEN): verify will write its report, no PR"
    return 0
  fi
  "${as[@]}" gh auth status --hostname github.com 2>&1 | grep -E 'Logged in|Token scopes' | sed 's/^ */  /' || true
  chmod -R go-rwx /var/lib/garage/.config 2>/dev/null || true
}

sec_units() {
  log "units: garage-sync, garage-verify"
  local u changed=0
  for u in garage-sync.service garage-sync.timer garage-verify.service garage-verify.timer; do
    if ! cmp -s "$INFRA/systemd/$u" "/etc/systemd/system/$u"; then
      install -m 644 "$INFRA/systemd/$u" /etc/systemd/system/
      changed=1
    fi
  done
  (( changed )) && systemctl daemon-reload
  systemd-analyze verify /etc/systemd/system/garage-{sync,verify}.{service,timer} 2>&1 | grep -v 'lechu-alert' \
    | sed 's/^/  /' || true
  local flag=$GARAGE_HOME/state/timers.enabled
  if [[ ${GARAGE_TIMERS:-0} == 1 ]]; then
    install -m 644 -o garage -g garage /dev/null "$flag"
  fi
  if [[ -f $flag ]]; then
    systemctl enable --now garage-sync.timer garage-verify.timer
    systemctl list-timers 'garage-*' --no-pager | head -3 | sed 's/^/  /'
  else
    echo "  timers installed, not enabled (first full sync is the coordinator's: GARAGE_TIMERS=1 $0 units)"
  fi
}

sections=("$@")
(( ${#sections[@]} )) || sections=(disk tools github units)
for s in "${sections[@]}"; do "sec_$s"; done
