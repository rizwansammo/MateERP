#!/usr/bin/env bash
# Install root-owned at /usr/local/sbin/mateerp-deploy with no CLI args.
# Stays inert unless TWO independent production authorisation gates are set.
set -Eeuo pipefail
[[ "$#" == 0 ]] || exit 15
IFS=' ' read -r action tag actor extra || exit 16
[[ "$action" == deploy && -z "${extra:-}" && "$tag" =~ ^sha-[0-9a-f]{40}$ && "$actor" =~ ^[a-zA-Z0-9-]{1,39}$ ]] || exit 17
[[ "$(id -u)" -eq 0 && -f /etc/mateerp/auto-deploy-enabled ]] || exit 18
# Short-lived GITHUB_TOKEN arrives only on stdin via restricted SSH.
# No long-lived GHCR PAT is stored on the production server.
IFS= read -r ghcr_token || exit 26
[[ "${#ghcr_token}" -ge 24 && "${#ghcr_token}" -le 500 ]] || exit 26
umask 077
DOCKER_CONFIG="$(mktemp -d /run/mateerp-ghcr.XXXXXXXX)"
export DOCKER_CONFIG
trap 'rm -rf -- "$DOCKER_CONFIG"' EXIT
printf '%s\n' "$ghcr_token" | docker login ghcr.io -u "$actor" --password-stdin >/dev/null 2>&1
unset ghcr_token
exec 9>/run/lock/mateerp-deploy.lock
flock -n 9 || { echo 'Another release is active' >&2; exit 19; }
cd /opt/MateERP
[[ -f compose.production.yml && -f .env.production ]] || exit 20
[[ "$(stat -c %a .env.production)" == 600 ]] || { echo 'Unsafe secret-file mode' >&2; exit 21; }
export MATEERP_IMAGE_TAG="$tag"
C=(docker compose --project-name mateerp --env-file .env.production -f compose.production.yml)
"${C[@]}" config --quiet

# Never build locally or expose Docker TCP/socket to the deployment account.
"${C[@]}" pull backend frontend database
"${C[@]}" up -d --wait --wait-timeout 180 database

# Backup before any production schema migrations. An invalid snapshot aborts release.
install -d -m 700 /opt/MateERP/backups
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup="/opt/MateERP/backups/before-${tag}-${stamp}.dump"
"${C[@]}" exec -T database sh -c 'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$backup"
[[ -s "$backup" ]] || { echo 'Backup is empty; aborting' >&2; exit 22; }
"${C[@]}" exec -T database pg_restore -l < "$backup" >/dev/null
sha256sum "$backup" > "$backup.sha256"
echo "Validated backup: $(basename "$backup")"

# Fail before application replacement if Django config or migrations are invalid.
"${C[@]}" run --rm --no-deps backend python manage.py check --deploy
"${C[@]}" run --rm --no-deps backend python manage.py migrate --noinput
"${C[@]}" up -d --wait --wait-timeout 180 backend frontend

# Validate browser origin, not merely Docker health status.
curl --fail --silent --show-error --max-time 15 \
  --resolve erp.netamate.com:443:127.0.0.1 \
  https://erp.netamate.com/api/v1/health/ > /dev/null
curl --fail --silent --show-error --max-time 15 \
  --resolve erp.netamate.com:443:127.0.0.1 \
  https://erp.netamate.com/login > /dev/null
printf '%s\n' "$tag" > /opt/MateERP/.deployed-image-tag
printf 'MateERP released %s (%s)\n' "$tag" "$(date -u +%FT%TZ)"
# Migrations may change database schema. Do NOT automatically restore a live DB
# on failure. Refer to the Phase 7E tested rollback plan and backup snapshots.
