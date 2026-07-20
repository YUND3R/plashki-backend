#!/usr/bin/env bash
# Бэкап PostgreSQL + uploads (Docker Compose). Запуск из каталога backend на VPS.
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.test.yml}"
OUTPUT_ROOT="${OUTPUT_ROOT:-./backups}"
DB_USER="${POSTGRES_USER:-plashki}"
DB_NAME="${POSTGRES_DB:-plashki}"
DB_SERVICE="${DB_SERVICE:-db}"
API_SERVICE="${API_SERVICE:-api}"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "COMPOSE_FILE=$COMPOSE_FILE not found. Run from backend/ (e.g. /opt/plashki-test)." >&2
  exit 1
fi

compose() {
  docker compose -f "$COMPOSE_FILE" "$@"
}

timestamp="$(date +%Y%m%d_%H%M%S)"
backup_dir="${OUTPUT_ROOT%/}/$timestamp"
mkdir -p "$backup_dir"

echo "Creating backup in: $backup_dir"

echo "Stopping API for consistent dump (optional)..."
compose stop "$API_SERVICE" 2>/dev/null || true

echo "1/3 Dumping database..."
compose exec -T "$DB_SERVICE" pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc >"$backup_dir/db.dump"

echo "Starting API..."
compose start "$API_SERVICE" 2>/dev/null || compose up -d "$API_SERVICE"

echo "2/3 Archiving uploads..."
compose exec -T "$API_SERVICE" sh -lc 'tar -czf - -C /app/uploads .' >"$backup_dir/uploads.tar.gz"

echo "3/3 Checksums..."
{
  echo "# SHA256"
  sha256sum "$backup_dir/db.dump" | awk '{print $1 "  db.dump"}'
  sha256sum "$backup_dir/uploads.tar.gz" | awk '{print $1 "  uploads.tar.gz"}'
} >"$backup_dir/checksums.txt"

echo "Backup complete:"
echo "  $backup_dir/db.dump"
echo "  $backup_dir/uploads.tar.gz"
echo "  $backup_dir/checksums.txt"
