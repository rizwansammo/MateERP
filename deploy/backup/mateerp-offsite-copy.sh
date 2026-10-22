#!/usr/bin/env bash
# Copy encrypted local MateERP snapshots to an independently controlled off-server restic repo.
# Must run as root, after backup; offsite credentials provided ONLY at go-live.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 && "$#" == 0 ]] || exit 11
[[ -f /etc/mateerp/backup-enabled ]] || exit 12
CONF=/etc/mateerp/backup.env
[[ -f "$CONF" && "$(stat -c %a "$CONF")" == 600 ]] || exit 13
# shellcheck disable=SC1090
set -a
source "$CONF"
set +a
: "${RESTIC_REPOSITORY:?}"
: "${RESTIC_PASSWORD_FILE:?}"
: "${MATEERP_OFFSITE_REPOSITORY:?Offsite required before go-live}"
: "${MATEERP_OFFSITE_PASSWORD_FILE:?Offsite key required}"
[[ -s "$MATEERP_OFFSITE_PASSWORD_FILE" && "$(stat -c %a "$MATEERP_OFFSITE_PASSWORD_FILE")" == 600 ]] || exit 14
[[ "$MATEERP_OFFSITE_REPOSITORY" != "$RESTIC_REPOSITORY" && "$MATEERP_OFFSITE_REPOSITORY" != /* ]] || exit 15
export RESTIC_PASSWORD_FILE RESTIC_REPOSITORY
exec 9>/opt/MateERP/backups/.offsite-copy.lock
flock -n 9 || exit 16
nice -n 15 restic -r "$MATEERP_OFFSITE_REPOSITORY" --password-file "$MATEERP_OFFSITE_PASSWORD_FILE" copy \
  --from-repo "$RESTIC_REPOSITORY" --from-password-file "$RESTIC_PASSWORD_FILE"
restic -r "$MATEERP_OFFSITE_REPOSITORY" --password-file "$MATEERP_OFFSITE_PASSWORD_FILE" snapshots --json >/dev/null
echo "[PASS] Offsite restic copy completed"
