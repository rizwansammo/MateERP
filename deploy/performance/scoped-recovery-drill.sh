#!/usr/bin/env bash
# Phase 7D controlled failure/recovery drill: only temporary mateerp7d containers.
set -Eeuo pipefail
DB=mateerp7d-database-1
API=mateerp7d-backend-e2e-1
BASE=http://127.0.0.1:8101/api/v1/health/
for name in "$DB" "$API"; do
  owner="$(sudo -n docker inspect "$name" --format '{{index .Config.Labels "com.docker.compose.project"}}')"
  [[ "$owner" == mateerp7d ]] || { echo "Refusing non-test container $name" >&2; exit 40; }
done
[[ "$(curl -sS --max-time 5 -o /dev/null -w '%{http_code}' "$BASE")" == 200 ]] || exit 41

# Database row counts before and after both disruptions must match.
count_before="$(sudo -n docker exec "$DB" psql -U mateerp7d -d mateerp_e2e_phase7d -Atqc 'select count(*) from django_migrations')"
[[ "$count_before" =~ ^[0-9]+$ && "$count_before" -gt 0 ]] || exit 42

echo "[7D] Restarting only disposable backend"
sudo -n docker restart --time 10 "$API" >/dev/null
for i in $(seq 1 35); do
  status="$(curl -s --max-time 2 -o /dev/null -w '%{http_code}' "$BASE" || true)"
  if [[ "$status" == 200 ]]; then break; fi
  sleep 1
done
[[ "$status" == 200 ]] || { echo "Backend failed recovery" >&2; exit 43; }
echo "[PASS] Backend returns HTTP 200 after scoped restart"

echo "[7D] Simulating temporary isolated database freeze"
sudo -n docker pause "$DB" >/dev/null
paused=yes
cleanup() {
  if [[ "${paused:-}" == yes ]]; then
    sudo -n docker unpause "$DB" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM
bad_status="$(curl -s --max-time 7 -o /dev/null -w '%{http_code}' "$BASE" || true)"
sudo -n docker unpause "$DB" >/dev/null
paused=no
echo "[OBSERVED] DB unavailable: health HTTP=$bad_status"
[[ "$bad_status" != 200 ]] || { echo "Failure health incorrectly remained OK" >&2; exit 44; }
for i in $(seq 1 35); do
  status="$(curl -s --max-time 2 -o /dev/null -w '%{http_code}' "$BASE" || true)"
  if [[ "$status" == 200 ]]; then break; fi
  sleep 1
done
[[ "$status" == 200 ]] || { echo "Database health did not recover" >&2; exit 45; }
count_after="$(sudo -n docker exec "$DB" psql -U mateerp7d -d mateerp_e2e_phase7d -Atqc 'select count(*) from django_migrations')"
[[ "$count_after" == "$count_before" ]] || { echo "Schema records changed after disruption" >&2; exit 46; }
echo "[PASS] Database outage detected, health recovered, migration records preserved: $count_after"
