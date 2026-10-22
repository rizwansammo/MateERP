#!/usr/bin/env bash
# Phase 7E temporary staging-only database/documents restore and image rollback.
set -Eeuo pipefail
[[ "$(id -u)" == 0 ]] || exit 11
cd /opt/MateERP-staging
C=(docker compose -p mateerp7e --env-file .env.staging -f compose.staging.yml)
db="$("${C[@]}" ps -q database)"
[[ -n "$db" ]] || exit 12
[[ "$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$db")" == mateerp7e ]] || exit 13
[[ "$(docker volume inspect -f '{{index .Labels "com.docker.compose.project"}}' mateerp7e_documents)" == mateerp7e ]] || exit 14
original="sha-a7d8780ca1d7425a29d3a06903492dbe4e8917e5"
alternate="sha-806e5f80979417fdbc9105d3f2ca08d9789089a2"
grep -q "^MATEERP_IMAGE_TAG=$original$" .env.staging || exit 15
work="$(mktemp -d /opt/MateERP-staging/.dr-check-XXXXXXXX)"
restored="mateerp7e_dr_$$"
cleanup() {
  docker exec "$db" dropdb -U mateerp_stage --if-exists "$restored" >/dev/null 2>&1 || true
  rm -rf -- "$work"
}
trap cleanup EXIT INT TERM
echo '[TEST DATA] isolated staging-only fixture'
docker exec "$db" psql -v ON_ERROR_STOP=1 -U mateerp_stage -d mateerp_stage -c 'CREATE TABLE IF NOT EXISTS staging_restore_probe (id int PRIMARY KEY, value text NOT NULL); INSERT INTO staging_restore_probe(id,value) VALUES (1, '\''posting-intact'\''), (2, '\''document-intact'\'') ON CONFLICT DO NOTHING;' >/dev/null
docker run --rm --network none --cpus 0.3 --memory 96m --pids-limit 60 --mount 'type=volume,src=mateerp7e_documents,dst=/documents' --entrypoint sh postgres:18.6-alpine -c 'printf "%s\n" "staging-only-private-document" > /documents/staging-recovery-fixture.txt' >/dev/null
echo '[BACKUP] staging actual database and private document volume'
"${C[@]}" exec -T database sh -ec 'exec pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$work/db.dump"
[[ -s "$work/db.dump" ]] || exit 16
"${C[@]}" exec -T database pg_restore --list < "$work/db.dump" >/dev/null
docker run --rm --network none --cpus 0.3 --memory 96m --pids-limit 60 --mount 'type=volume,src=mateerp7e_documents,dst=/documents,readonly' --entrypoint tar postgres:18.6-alpine -C /documents -cf - . > "$work/documents.tar"
tar -tf "$work/documents.tar" | grep -q staging-recovery-fixture.txt
(cd "$work" && sha256sum db.dump documents.tar > CHECKSUMS && sha256sum -c CHECKSUMS)
echo '[RESTORE] into a SECOND staging-only PostgreSQL database'
docker exec "$db" createdb -U mateerp_stage "$restored"
docker exec -i "$db" pg_restore --exit-on-error --no-owner --no-acl -U mateerp_stage -d "$restored" < "$work/db.dump"
rows="$(docker exec "$db" psql -U mateerp_stage -d "$restored" -Atqc "select count(*) from staging_restore_probe where (id=1 and value='posting-intact') or (id=2 and value='document-intact')")"
[[ "$rows" == 2 ]] || { echo 'Data recovery mismatch' >&2; exit 17; }
migrations_src="$(docker exec "$db" psql -U mateerp_stage -d mateerp_stage -Atqc 'select count(*) from django_migrations')"
migrations_dst="$(docker exec "$db" psql -U mateerp_stage -d "$restored" -Atqc 'select count(*) from django_migrations')"
[[ "$migrations_src" -gt 0 && "$migrations_src" == "$migrations_dst" ]] || exit 18
echo "[PASS] Staging database and private file restore: $rows fixture rows; migrations $migrations_dst"
docker exec "$db" dropdb -U mateerp_stage "$restored"
echo '[ROLLBACK] staging-only switch SHA a7d -> 806 -> a7d'
sed -i "s/^MATEERP_IMAGE_TAG=.*/MATEERP_IMAGE_TAG=$alternate/" .env.staging
"${C[@]}" pull backend frontend >/dev/null
"${C[@]}" up -d --no-deps --wait --wait-timeout 180 backend frontend
curl -kfsS --max-time 10 --resolve erp.netamate.com:18443:127.0.0.1 -o /dev/null https://erp.netamate.com:18443/api/v1/health/
sed -i "s/^MATEERP_IMAGE_TAG=.*/MATEERP_IMAGE_TAG=$original/" .env.staging
"${C[@]}" up -d --no-deps --wait --wait-timeout 180 backend frontend
curl -kfsS --max-time 10 --resolve erp.netamate.com:18443:127.0.0.1 -o /dev/null https://erp.netamate.com:18443/api/v1/health/
last="$(docker exec "$db" psql -U mateerp_stage -d mateerp_stage -Atqc "select count(*) from staging_restore_probe")"
[[ "$last" == 2 ]] || exit 19
echo '[PASS] Both SHA image switches completed; PostgreSQL fixture rows retained'
