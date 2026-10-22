#!/usr/bin/env bash
# Run ONLY via monthly timer during maintenance window; never prune unrelated repositories.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 && "$#" == 0 ]] || exit 11
[[ -f /etc/mateerp/backup-enabled ]] || exit 12
[[ -f /etc/mateerp/backup.env && "$(stat -c %a /etc/mateerp/backup.env)" == 600 ]] || exit 13
# shellcheck disable=SC1091
source /etc/mateerp/backup.env
: "${RESTIC_REPOSITORY:?}"
: "${RESTIC_PASSWORD_FILE:?}"
[[ "$RESTIC_REPOSITORY" == /opt/MateERP/backups/repository ]] || exit 14
export RESTIC_REPOSITORY RESTIC_PASSWORD_FILE
exec 9>/opt/MateERP/backups/.backup.lock
flock -n 9 || exit 15
nice -n 15 restic forget --tag mateerp --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --keep-yearly 2 --prune
nice -n 15 restic check --read-data-subset=1/20
echo "[OK] MateERP local retention and partial read verification complete"
