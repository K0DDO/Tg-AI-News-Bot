#!/usr/bin/env bash
# Nightly PostgreSQL backup for Briefly (keep last 7).
# Intended to run on the VPS host via cron, from /opt/briefly.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

KEEP="${BACKUP_KEEP:-7}"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
OUT_DIR="$ROOT/backups"
mkdir -p "$OUT_DIR"

if ! docker compose --env-file .env.production ps --status running --services 2>/dev/null | grep -qx postgres; then
  echo "postgres container is not running" >&2
  exit 1
fi

# shellcheck disable=SC1091
if [[ -f "$ROOT/.env.production" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ROOT/.env.production"
  set +a
elif [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ROOT/.env"
  set +a
fi

USER_NAME="${POSTGRES_USER:-briefly}"
DB_NAME="${POSTGRES_DB:-briefly}"
FILE="$OUT_DIR/briefly_${STAMP}.sql.gz"

echo "[backup] dumping ${DB_NAME} -> ${FILE}"
docker compose --env-file .env.production exec -T postgres \
  pg_dump -U "$USER_NAME" -d "$DB_NAME" --clean --if-exists \
  | gzip -c > "$FILE"

# Rotate
mapfile -t OLD < <(ls -1t "$OUT_DIR"/briefly_*.sql.gz 2>/dev/null || true)
if ((${#OLD[@]} > KEEP)); then
  for f in "${OLD[@]:$KEEP}"; do
    rm -f -- "$f"
    echo "[backup] removed $f"
  done
fi

echo "[backup] done ($(du -h "$FILE" | awk '{print $1}'))"
