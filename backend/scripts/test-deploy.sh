#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="docker-compose.test.yml"
API_PORT="${API_PORT:-8000}"

if [[ ! -f .env ]]; then
  if [[ -f .env.test.example ]]; then
    cp .env.test.example .env
    echo "Создан .env из .env.test.example"
    echo "Отредактируйте YOUR_SERVER_IP и CORS_ORIGINS, затем запустите скрипт снова."
    exit 1
  fi
  echo "Нет .env и .env.test.example"
  exit 1
fi

# shellcheck disable=SC1091
set -a
source .env
set +a

if [[ "${PUBLIC_BASE_URL:-}" == *"YOUR_SERVER_IP"* ]]; then
  echo "Замените YOUR_SERVER_IP в .env (PUBLIC_BASE_URL, CORS_ORIGINS, FRONTEND_*)."
  exit 1
fi

echo "Сборка и запуск (docker compose -f ${COMPOSE_FILE})..."
docker compose -f "$COMPOSE_FILE" up -d --build

echo ""
docker compose -f "$COMPOSE_FILE" ps

echo ""
echo -n "Health: "
curl -sf "http://127.0.0.1:${API_PORT}/health"
echo ""
echo "Swagger: http://127.0.0.1:${API_PORT}/docs"
