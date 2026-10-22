#!/usr/bin/env bash
# Restores a snapshot ONLY into a new isolated temporary location and ephemeral PostgreSQL 18 container.
# Never connects to production PostgreSQL or overwrites production document storage.
set -Eeuo pipefail
trap 'echo "Restore drill stopped at script line $LINENO" >&2' ERR
umask 077
[[ "$(id -u)" == 0 && "$#" == 1 && "$1" =~ ^[a-f0-9]{8,64}$ ]] || exit 11
snapshot="$1"
CONF=/etc/mateerp/backup.env
[[ -f "$CONF" && "$(stat -c %a "$CONF")" == 600 ]] || exit 12
# shellcheck disable=SC1090
source "$CONF"
: "${RESTIC_REPOSITORY:?}"
: "${RESTIC_PASSWORD_FILE:?}"
[[ -s "$RESTIC_PASSWORD_FILE" ]] || exit 13
export RESTIC_REPOSITORY RESTIC_PASSWORD_FILE
work="$(mktemp -d /opt/MateERP/backups/.dr-test-XXXXXXXX)"
name="mateerp-dr-$$"
cleanup() {
  docker rm -f "$name" >/dev/null 2>&1 || true
  rm -rf -- "$work"
}
trap cleanup EXIT INT TERM
echo "[RESTORE] Recover encrypted snapshot to isolated directory"
restic restore "$snapshot" --target "$work/recovered" >/dev/null
mapfile -t manifests < <(find "$work/recovered" -type f -name SHA256SUMS)
[[ "${#manifests[@]}" -eq 1 ]] || { echo "Missing or ambiguous manifest" >&2; exit 14; }
bundle="$(dirname "${manifests[0]}")"
(cd "$bundle" && sha256sum -c SHA256SUMS)
pg_restore --list "$bundle/database.dump" >/dev/null
echo "[FILES] Validate tar members; recover only regular files/directories into isolated destination"
mkdir -p "$work/documents"
python3 - "$bundle/documents.tar" "$work/documents" <<'PY'
import pathlib, sys, tarfile
src, dest = sys.argv[1], pathlib.Path(sys.argv[2])
with tarfile.open(src, 'r:') as tar:
    for member in tar:
        p=pathlib.PurePosixPath(member.name)
        if p.is_absolute() or '..' in p.parts or not (member.isfile() or member.isdir()):
            raise SystemExit(f'Unsafe tar member: {member.name!r}')
        target=dest.joinpath(*p.parts)
        if member.isdir():
            target.mkdir(parents=True,exist_ok=True)
        elif member.isfile():
            target.parent.mkdir(parents=True,exist_ok=True)
            with tar.extractfile(member) as f, target.open('wb') as out:
                while block := f.read(1024*1024):
                    out.write(block)
print('Private document archive extracted to isolated directory')
PY
echo "[DB] Create ephemeral PostgreSQL with no network, no published ports and no production mounts"
mkdir -p "$work/isolated-db"
# The PG18 Alpine runtime uses UID 70. Keep the volume private while allowing
# its database process to create its isolated cluster under restrictive umask.
chown 70:70 "$work/isolated-db"
chmod 700 "$work/isolated-db"
docker run -d --name "$name" --network none --cpus 0.75 --memory 768m --pids-limit 160 \
  --mount "type=bind,src=$work/isolated-db,dst=/var/lib/postgresql" \
  -e POSTGRES_DB=mateerp_dr -e POSTGRES_USER=mateerp_dr \
  -e POSTGRES_PASSWORD=temporary-isolated-only postgres:18.6-alpine >/dev/null
for i in $(seq 1 40); do
  if ! [[ "$(docker inspect -f '{{.State.Running}}' "$name")" == true ]]; then
    echo "Isolated PostgreSQL failed to start; limited diagnostic:" >&2
    docker logs --tail 30 "$name" >&2 || true
    exit 17
  fi
  docker exec "$name" pg_isready -U mateerp_dr -d mateerp_dr >/dev/null 2>&1 && break
  sleep 1
done
docker exec "$name" pg_isready -U mateerp_dr -d mateerp_dr >/dev/null
docker exec -i "$name" pg_restore --exit-on-error --no-owner --no-acl -U mateerp_dr -d mateerp_dr < "$bundle/database.dump"
tables="$(docker exec "$name" psql -U mateerp_dr -d mateerp_dr -Atqc "select count(*) from information_schema.tables where table_schema='public'")"
[[ "$tables" =~ ^[0-9]+$ && "$tables" -gt 0 ]] || { echo "No application tables restored" >&2; exit 19; }
# In the built-in acceptance fixture, also validate both real data rows.
fixture_table="$(docker exec "$name" psql -U mateerp_dr -d mateerp_dr -Atqc "select to_regclass('public.recovery_fixture') is not null")"
if [[ "$fixture_table" == t ]]; then
  fixture_count="$(docker exec "$name" psql -U mateerp_dr -d mateerp_dr -Atqc "select count(*) from public.recovery_fixture where (id=1 and value='ledger-preserved') or (id=2 and value='document-preserved')")"
  [[ "$fixture_count" == 2 ]] || { echo "Test fixture values did not survive recovery" >&2; exit 20; }
  echo "[PASS] Recovered test records match both original values"
fi
echo "[PASS] Isolated database restore, public tables=$tables; private documents and checksums verified"
