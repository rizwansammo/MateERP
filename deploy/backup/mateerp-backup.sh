#!/usr/bin/env bash
# MateERP encrypted backup. Install root-owned 0700 at first go-live.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 && "$#" == 0 ]] || exit 11
[[ -f /etc/mateerp/backup-enabled ]] || { echo "Backup gate disabled" >&2; exit 12; }
CONF=/etc/mateerp/backup.env
[[ -f "$CONF" && "$(stat -c %a "$CONF")" == 600 ]] || exit 13
# shellcheck disable=SC1090
source "$CONF"
: "${RESTIC_REPOSITORY:?}"
: "${RESTIC_PASSWORD_FILE:?}"
[[ -s "$RESTIC_PASSWORD_FILE" && "$(stat -c %a "$RESTIC_PASSWORD_FILE")" == 600 ]] || exit 14
export RESTIC_REPOSITORY RESTIC_PASSWORD_FILE
BACKUP_ROOT=/opt/MateERP/backups
[[ "$RESTIC_REPOSITORY" == "$BACKUP_ROOT/repository" ]] || { echo "Unexpected backup repository" >&2; exit 15; }
[[ -f /opt/MateERP/compose.production.yml && -f /opt/MateERP/.env.production ]] || exit 16
[[ "$(stat -c %a /opt/MateERP/.env.production)" == 600 ]] || exit 17
install -d -m 700 "$BACKUP_ROOT"
exec 9>"$BACKUP_ROOT/.backup.lock"
flock -n 9 || { echo "Backup already running" >&2; exit 18; }
cd /opt/MateERP
C=(docker compose --project-name mateerp --env-file .env.production -f compose.production.yml)
"${C[@]}" config --quiet
db_container="$("${C[@]}" ps -q database)"
[[ -n "$db_container" && "$(docker inspect -f '{{.State.Running}}' "$db_container")" == true ]] || exit 19
doc_volume=mateerp_documents
[[ "$(docker volume inspect -f '{{index .Labels "com.docker.compose.project"}}' "$doc_volume")" == mateerp ]] || exit 20
restic snapshots --json >/dev/null
stage="$(mktemp -d "$BACKUP_ROOT/.stage-XXXXXXXX")"
trap 'rm -rf -- "$stage"' EXIT
echo "[DB] Snapshotting PostgreSQL"
"${C[@]}" exec -T database sh -ec 'exec pg_dump --format=custom --no-owner --no-acl -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$stage/database.dump"
[[ -s "$stage/database.dump" ]] || exit 21
"${C[@]}" exec -T database pg_restore --list < "$stage/database.dump" >/dev/null
echo "[FILES] Archiving private document volume"
docker run --rm --network none --cpus 0.5 --memory 192m --pids-limit 64 \
  --mount "type=volume,src=$doc_volume,dst=/files,readonly" \
  --entrypoint tar postgres:18.6-alpine -C /files -cf - . > "$stage/documents.tar"
[[ -s "$stage/documents.tar" ]] || exit 22
tar -tf "$stage/documents.tar" >/dev/null
image_tag="$(cat /opt/MateERP/.deployed-image-tag 2>/dev/null || true)"
[[ "$image_tag" =~ ^sha-[a-f0-9]{40}$ ]] || image_tag=unknown
cat > "$stage/manifest.txt" <<EOF
product=MateERP
format=phase7c-1
created_utc=$(date -u +%FT%TZ)
postgresql_major=18
application_image_tag=$image_tag
database_format=pg_dump_custom
private_documents=tar
EOF
# Encrypted backups also preserve recovery-critical application configuration,
# but NEVER the Restic encryption password or offsite access credentials.
cp -p /opt/MateERP/.env.production "$stage/application.env.production"
cp -p /opt/MateERP/compose.production.yml "$stage/compose.production.yml"
(cd "$stage" && sha256sum database.dump documents.tar manifest.txt application.env.production compose.production.yml > SHA256SUMS)
echo "[RESTIC] Creating encrypted snapshot"
nice -n 15 restic backup --tag mateerp --tag production --host MateServer -- "$stage"
echo "[OK] Encrypted backup complete"
