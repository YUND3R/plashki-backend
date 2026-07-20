#!/usr/bin/env bash
# Восстановление PostgreSQL + uploads из каталога бэкапа. Перезаписывает данные.
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.test.yml}"
DB_USER="${POSTGRES_USER:-plashki}"
DB_NAME="${POSTGRES_DB:-plashki}"
DB_SERVICE="${DB_SERVICE:-db}"
API_SERVICE="${API_SERVICE:-api}"

BACKUP_DIR="${1:-}"
if [[ -z "$BACKUP_DIR" || ! -d "$BACKUP_DIR" ]]; then
  echo "Usage: $0 /path/to/backup_dir" >&2
  exit 1
fi

db_dump="$BACKUP_DIR/db.dump"
uploads="$BACKUP_DIR/uploads.tar.gz"

[[ -f "$db_dump" ]] || { echo "Missing $db_dump" >&2; exit 1; }
[[ -f "$uploads" ]] || { echo "Missing $uploads" >&2; exit 1; }

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "COMPOSE_FILE=$COMPOSE_FILE not found. Run from backend/." >&2
  exit 1
fi

compose() {
  docker compose -f "$COMPOSE_FILE" "$@"
}

db_container="$(compose ps -q "$DB_SERVICE" | tr -d '\r\n')"
api_container="$(compose ps -q "$API_SERVICE" | tr -d '\r\n')"

if [[ -z "$db_container" ]]; then
  echo "DB container not running. Start stack first: compose up -d db" >&2
  exit 1
fi
if [[ -z "$api_container" ]]; then
  echo "API container not running. compose up -d" >&2
  exit 1
fi

echo "Restoring from: $BACKUP_DIR"

compose stop "$API_SERVICE" || true

echo "1/2 Restoring database..."
docker cp "$db_dump" "$db_container:/tmp/db.dump"
compose exec -T "$DB_SERVICE" sh -lc "dropdb -U $DB_USER --if-exists $DB_NAME && createdb -U $DB_USER $DB_NAME"
compose exec -T "$DB_SERVICE" pg_restore -U "$DB_USER" -d "$DB_NAME" --clean --if-exists /tmp/db.dump || true
compose exec -T "$DB_SERVICE" rm -f /tmp/db.dump

echo "2/2 Restoring uploads..."
docker cp "$uploads" "$api_container:/tmp/uploads.tar.gz"
compose exec -T "$API_SERVICE" sh -lc 'rm -rf /app/uploads/* /app/uploads/.[!.]* 2>/dev/null; tar -xzf /tmp/uploads.tar.gz -C /app/uploads'
compose exec -T "$API_SERVICE" rm -f /tmp/uploads.tar.gz

compose start "$API_SERVICE" || compose up -d "$API_SERVICE"

echo "Restore complete."
