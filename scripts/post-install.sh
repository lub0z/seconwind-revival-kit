#!/usr/bin/env bash
# Seconwind post-install setup for a fresh Linux Mint install.
#
#   sudo ./post-install.sh            # dry run: shows what it would do, changes nothing
#   sudo ./post-install.sh --apply    # does it
#
# It never touches disks or partitions. Every step is safe to run twice.
set -euo pipefail

APPLY=0
EXTRA_PACKAGES="${EXTRA_PACKAGES:-vlc hplip-gui}"
LOG=/var/log/seconwind-revival.log

for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

say()  { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
note() { printf '    %s\n' "$*"; }
run() {
  if [[ $APPLY -eq 1 ]]; then
    printf '    $ %s\n' "$*" | tee -a "$LOG"
    "$@" 2>&1 | tee -a "$LOG"
  else
    printf '    would run: %s\n' "$*"
  fi
}

if [[ $EUID -ne 0 ]]; then
  echo "Please run with sudo." >&2; exit 1
fi
. /etc/os-release
if [[ "${ID:-}" != "linuxmint" ]]; then
  echo "This is ${PRETTY_NAME:-an unknown system}, not Linux Mint. Stopping." >&2; exit 1
fi
if [[ -d /rofs || "$(findmnt -n -o FSTYPE /)" == "overlay" ]]; then
  echo "This looks like the live USB session. Run this on the installed system after first boot." >&2; exit 1
fi

[[ $APPLY -eq 1 ]] && echo "=== $(date -Is) post-install on ${PRETTY_NAME} ===" >> "$LOG"
[[ $APPLY -eq 0 ]] && echo "DRY RUN: nothing will change. Add --apply to do it."

say "1. Update everything"
run apt-get update
run env DEBIAN_FRONTEND=noninteractive apt-get -y full-upgrade

say "2. Automatic updates (security and everything else, via Update Manager)"
if command -v mintupdate-automation >/dev/null; then
  run mintupdate-automation upgrade enable
  run mintupdate-automation autoremove enable
else
  note "mintupdate-automation not found: turn on automatic updates in Update Manager > Edit > Preferences > Automation."
fi

say "3. Firewall on (blocks incoming connections, allows everything outgoing)"
run ufw default deny incoming
run ufw default allow outgoing
run ufw --force enable

say "4. Extra apps: ${EXTRA_PACKAGES}"
# shellcheck disable=SC2086
run env DEBIAN_FRONTEND=noninteractive apt-get -y install ${EXTRA_PACKAGES}

say "5. Things to check by hand"
if command -v ubuntu-drivers >/dev/null; then
  drivers="$(ubuntu-drivers devices 2>/dev/null | grep -E 'recommended' || true)"
  if [[ -n "$drivers" ]]; then
    note "Driver Manager recommends:"; note "$drivers"
    note "Install from Menu > Driver Manager, then reboot."
  else
    note "No extra drivers recommended."
  fi
fi
if command -v fwupdmgr >/dev/null; then
  note "Firmware updates available (if any):"
  fwupdmgr get-updates --no-unreported-check 2>/dev/null | sed 's/^/      /' | head -20 || true
fi
note "Timeshift: open it once and choose RSYNC snapshots on this disk (weekly, keep 2)."
note "Test: Wi-Fi, sound, webcam, printer, and that the customer's files open."

say "Done"
[[ $APPLY -eq 1 ]] && note "Log: $LOG" || note "Nothing changed. Run again with --apply."
