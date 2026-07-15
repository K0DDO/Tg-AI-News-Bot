#!/usr/bin/env bash
# Safe production deploy for Briefly ONLY (/opt/briefly).
# Called by GitHub Actions after git pull, or manually on the VPS as user deploy.
#
# Allowed: briefly compose project, briefly-* containers, backup under ./backups
# Forbidden: docker compose down, system prune, volume rm, iptables/firewall,
#            Amnezia, /opt/moex-bot, other compose projects, other systemd units.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE=(docker compose --env-file .env.production)
APP_IMAGE="${BRIEFLY_APP_IMAGE:-briefly-briefly-app}"
ROLLBACK_TAG="${APP_IMAGE}:predeploy"
MAX_WAIT="${HEALTH_WAIT_SECONDS:-60}"

log() { echo "[ci-deploy] $*"; }
err() { echo "[ci-deploy] ERROR: $*" >&2; }

die() {
  err "$*"
  exit 1
}

assert_cwd() {
  [[ "$(pwd)" == "/opt/briefly" ]] || die "refusing to run outside /opt/briefly (pwd=$(pwd))"
}

assert_files() {
  [[ -f docker-compose.yml ]] || die "missing docker-compose.yml"
  [[ -f Dockerfile ]] || die "missing Dockerfile"
  [[ -f .env.production ]] || die "missing .env.production (server-only; never from CI)"
}

# Read only DB name/user for pg_dump — never print password or other secrets.
read_pg_identity() {
  local line val
  POSTGRES_USER="briefly"
  POSTGRES_DB="briefly"
  if line="$(grep -E '^POSTGRES_USER=' .env.production | head -n1 || true)"; then
    val="${line#POSTGRES_USER=}"
    val="${val%\"}"
    val="${val#\"}"
    val="${val%\'}"
    val="${val#\'}"
    [[ -n "$val" ]] && POSTGRES_USER="$val"
  fi
  if line="$(grep -E '^POSTGRES_DB=' .env.production | head -n1 || true)"; then
    val="${line#POSTGRES_DB=}"
    val="${val%\"}"
    val="${val#\"}"
    val="${val%\'}"
    val="${val#\'}"
    [[ -n "$val" ]] && POSTGRES_DB="$val"
  fi
}

save_rollback_image() {
  if docker image inspect "${APP_IMAGE}:latest" >/dev/null 2>&1; then
    docker tag "${APP_IMAGE}:latest" "${ROLLBACK_TAG}"
    log "saved rollback image ${ROLLBACK_TAG}"
    return 0
  fi
  if docker inspect briefly-app --format='{{.Image}}' >/dev/null 2>&1; then
    local img
    img="$(docker inspect briefly-app --format='{{.Image}}')"
    docker tag "$img" "${ROLLBACK_TAG}"
    log "saved rollback image from running container → ${ROLLBACK_TAG}"
    return 0
  fi
  log "no previous briefly-app image (first deploy?) — rollback tag skipped"
}

rollback_app() {
  if ! docker image inspect "${ROLLBACK_TAG}" >/dev/null 2>&1; then
    err "rollback image missing — cannot auto-rollback"
    return 1
  fi
  log "ROLLBACK: restoring previous briefly-app image"
  docker tag "${ROLLBACK_TAG}" "${APP_IMAGE}:latest"
  "${COMPOSE[@]}" up -d --no-deps --no-build briefly-app || true
}

dump_logs() {
  log "---- briefly-app logs (tail 100) ----"
  "${COMPOSE[@]}" logs --tail=100 briefly-app || true
  log "---- postgres logs (tail 100) ----"
  "${COMPOSE[@]}" logs --tail=100 postgres || true
  log "---- redis logs (tail 100) ----"
  "${COMPOSE[@]}" logs --tail=100 redis || true
}

wait_healthy() {
  local name="$1"
  local i status
  for i in $(seq 1 "$MAX_WAIT"); do
    status="$(docker inspect "$name" --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null || echo missing)"
    if [[ "$status" == "healthy" ]]; then
      log "${name}: healthy (${i}s)"
      return 0
    fi
    if [[ "$status" == "running" && "$name" == "briefly-app" ]]; then
      # app may have no HEALTHCHECK — running is enough
      log "${name}: running (${i}s)"
      return 0
    fi
    sleep 1
  done
  err "${name} not healthy within ${MAX_WAIT}s (last=${status:-unknown})"
  return 1
}

# ----- main -----
assert_cwd
assert_files

log "======== compose config ========"
if ! "${COMPOSE[@]}" config -q; then
  die "docker compose config failed — abort (no container changes)"
fi
log "OK: compose config valid"

log "======== ensure postgres/redis up (no rebuild) ========"
# Starts if stopped; does not recreate or rebuild images.
"${COMPOSE[@]}" up -d --no-build postgres redis

log "======== backup PostgreSQL ========"
mkdir -p backups
read_pg_identity
STAMP="$(date +%F_%H-%M)"
BACKUP_FILE="backups/predeploy_${STAMP}.sql"
log "pg_dump → ${BACKUP_FILE} (user=${POSTGRES_USER} db=${POSTGRES_DB})"
if ! docker exec briefly-postgres pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" > "${BACKUP_FILE}"; then
  rm -f "${BACKUP_FILE}"
  die "pg_dump failed — deploy cancelled"
fi
if [[ ! -s "${BACKUP_FILE}" ]]; then
  rm -f "${BACKUP_FILE}"
  die "backup file empty — deploy cancelled"
fi
log "OK: backup $(wc -c < "${BACKUP_FILE}") bytes"

save_rollback_image

log "======== build briefly-app only ========"
"${COMPOSE[@]}" build briefly-app

log "======== migrate (new image, no long-running entrypoint) ========"
if ! "${COMPOSE[@]}" run --rm --no-deps --entrypoint alembic briefly-app upgrade head; then
  err "alembic failed"
  dump_logs
  rollback_app || true
  die "migration failed — rolled back if possible"
fi
log "OK: migrations applied"

log "======== up briefly-app (no compose down) ========"
if ! "${COMPOSE[@]}" up -d --no-deps --no-build briefly-app; then
  err "failed to start briefly-app"
  dump_logs
  rollback_app || true
  die "app start failed"
fi

log "======== compose ps ========"
"${COMPOSE[@]}" ps

log "======== health checks (max ${MAX_WAIT}s) ========"
FAIL=0
wait_healthy briefly-postgres || FAIL=1
wait_healthy briefly-redis || FAIL=1
# briefly-app: must be running
APP_STATE="$(docker inspect briefly-app --format='{{.State.Status}}' 2>/dev/null || echo missing)"
if [[ "$APP_STATE" != "running" ]]; then
  err "briefly-app status=${APP_STATE}"
  FAIL=1
else
  log "briefly-app: running"
fi

if [[ "$FAIL" -ne 0 ]]; then
  dump_logs
  rollback_app || true
  die "health check failed — see logs above"
fi

log "DONE — Briefly updated; other VPS services untouched"
exit 0
