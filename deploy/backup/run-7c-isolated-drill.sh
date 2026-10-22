#!/usr/bin/env bash
# Self-contained isolated Phase 7C acceptance test. Safe on shared MateServer.
# Uses no production DB, data volume, secret, network, service or open port.
set -Eeuo pipefail
[[ "$(id -u)" == 0 ]] || { echo "Run as root for disposable Docker checks" >&2; exit 20; }
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN="$(mktemp -d /tmp/mateerp7c-accept-XXXXXXXX)"
DB="mateerp7c-fixture-$$"
cleanup() {
  docker rm -f "$DB" >/dev/null 2>&1 || true
  rm -rf -- "$RUN"
}
trap cleanup EXIT INT TERM
mkdir -p "$RUN"/{local-repo,offsite-repo,bundle,private}
printf 'Private invoice fixture for restored files\n' > "$RUN/private/fixture.pdf"
printf 'application env fixture only\n' > "$RUN/bundle/application.env.production"
printf 'compose fixture only\n' > "$RUN/bundle/compose.production.yml"
openssl rand -base64 48 > "$RUN/local-key"
openssl rand -base64 48 > "$RUN/offsite-key"
docker run -d --name "$DB" --network none --cpus 0.5 --memory 512m --pids-limit 140 \
  --tmpfs /var/lib/postgresql:rw,size=384m \
  -e POSTGRES_DB=mateerp_test -e POSTGRES_USER=mateerp_test -e POSTGRES_PASSWORD=disposable-only \
  postgres:18.6-alpine >/dev/null
for _ in $(seq 1 35); do
  docker exec "$DB" pg_isready -U mateerp_test -d mateerp_test >/dev/null 2>&1 && break
  sleep 1
done
docker exec "$DB" pg_isready -U mateerp_test -d mateerp_test >/dev/null
docker exec "$DB" psql -v ON_ERROR_STOP=1 -U mateerp_test -d mateerp_test -c \
  "CREATE TABLE recovery_fixture(id int PRIMARY KEY, value text NOT NULL); INSERT INTO recovery_fixture VALUES (1, 'ledger-preserved'), (2, 'document-preserved');" >/dev/null
docker exec "$DB" pg_dump --format=custom -U mateerp_test -d mateerp_test > "$RUN/bundle/database.dump"
pg_restore --list "$RUN/bundle/database.dump" >/dev/null
tar -C "$RUN/private" -cf "$RUN/bundle/documents.tar" .
cat > "$RUN/bundle/manifest.txt" <<EOF
product=MateERP
format=phase7c-1
created_utc=$(date -u +%FT%TZ)
postgresql_major=18
EOF
(cd "$RUN/bundle" && sha256sum database.dump documents.tar manifest.txt application.env.production compose.production.yml > SHA256SUMS)
export RESTIC_REPOSITORY="$RUN/local-repo" RESTIC_PASSWORD_FILE="$RUN/local-key"
restic init >/dev/null
restic backup --tag mateerp --tag test "$RUN/bundle" >/dev/null
restic check >/dev/null
restic -r "$RUN/offsite-repo" --password-file "$RUN/offsite-key" init >/dev/null
restic -r "$RUN/offsite-repo" --password-file "$RUN/offsite-key" copy \
  --from-repo "$RUN/local-repo" --from-password-file "$RUN/local-key" >/dev/null
restic -r "$RUN/offsite-repo" --password-file "$RUN/offsite-key" check >/dev/null
snapshot="$(restic -r "$RUN/offsite-repo" --password-file "$RUN/offsite-key" snapshots --json --tag mateerp | python3 -c 'import json,sys; print(json.load(sys.stdin)[-1]["id"])')"
[[ "$snapshot" =~ ^[a-f0-9]{64}$ ]]
cat > "$RUN/test-backup.env" <<EOF
RESTIC_REPOSITORY="$RUN/offsite-repo"
RESTIC_PASSWORD_FILE="$RUN/offsite-key"
EOF
chmod 600 "$RUN/test-backup.env"
python3 - "$ROOT/mateerp-restore-drill.sh" "$RUN/restore-test.sh" "$RUN" <<'PY'
import pathlib,sys
src,dst,root=map(pathlib.Path,sys.argv[1:])
s=src.read_text()
assert 'CONF=/etc/mateerp/backup.env' in s
assert 'mktemp -d /opt/MateERP/backups/.dr-test-XXXXXXXX' in s
s=s.replace('CONF=/etc/mateerp/backup.env',f'CONF={root}/test-backup.env')
s=s.replace('mktemp -d /opt/MateERP/backups/.dr-test-XXXXXXXX',f'mktemp -d {root}/restoration-XXXXXXXX')
dst.write_text(s)
dst.chmod(0o700)
PY
echo "[DRILL] Exercising actual restore script against independent encrypted offsite copy"
bash "$RUN/restore-test.sh" "$snapshot"
echo "[PASS] DB restored, integrity validated, and isolated document archive recovered"
