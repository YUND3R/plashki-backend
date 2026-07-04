# Тестовый деплой Plashki API

Проверка функционала на VPS **без домена и HTTPS**. Не используйте эту конфигурацию как production.

## Требования

- VPS с Docker и Docker Compose v2
- Открыт порт **8000** (API)
- Фронтенд — отдельно (Vite на `:5173` или свой хостинг)

## Быстрый старт

```bash
cd backend
cp .env.test.example .env
# Отредактируйте .env: YOUR_SERVER_IP → IP VPS, CORS_ORIGINS → URL фронта

docker compose -f docker-compose.test.yml up -d --build
docker compose -f docker-compose.test.yml ps
curl http://127.0.0.1:8000/health
```

Или одной командой (если `.env` уже настроен):

```bash
bash scripts/test-deploy.sh
```

## Первый пользователь (без SMTP)

При `ENVIRONMENT=development` доступны dev-ручки:

```bash
# Админ (логин dev_admin / пароль admin — поменяйте после теста)
curl -X POST "http://YOUR_SERVER_IP:8000/dev/test-admin" \
  -H "Content-Type: application/json" \
  -d '{"username":"dev_admin","email":"admin@test.local","password":"admin"}'

# Обычный user с role=admin для проверки прав
curl -X POST "http://YOUR_SERVER_IP:8000/dev/test-user" \
  -H "Content-Type: application/json" \
  -d '{"username":"tester","email":"test@test.local","password":"test1234","role":"user"}'
```

Вход: `POST /auth/login` → cookie + CSRF. Swagger: `http://YOUR_SERVER_IP:8000/docs`

## Фронтенд

В `.env` фронта укажите API:

```
VITE_API_URL=http://YOUR_SERVER_IP:8000
```

В `backend/.env` **CORS_ORIGINS** должен содержать origin фронта, например:

```
CORS_ORIGINS=http://YOUR_SERVER_IP:5173
```

## Что работает в тестовом режиме

| Функция | Статус |
|---------|--------|
| Auth (login, register, reset) | ✅ |
| Лобби, overlay, player cards | ✅ |
| Shop (mock purchase — бесплатные плашки) | ✅ |
| OpenAPI `/docs` | ✅ (`EXPOSE_OPENAPI=true`) |
| Dev `/dev/*` | ✅ только при `development` |
| Реальная оплата | ❌ mock |
| HTTPS | ❌ нужен reverse proxy + `production` |

## Email без SMTP

- Регистрация создаёт аккаунт, но письмо не уйдёт.
- Подтверждение email: dev-пользователи уже verified; для register — настройте SMTP или подтвердите через SQL / `POST /auth/verify-email` если есть ссылка из логов.

## Остановка и логи

```bash
docker compose -f docker-compose.test.yml logs -f api
docker compose -f docker-compose.test.yml down          # данные в volume сохранятся
docker compose -f docker-compose.test.yml down -v       # удалить БД и uploads
```

## Переход на production

Используйте `docker-compose.prod.yml`, `.env.prod.example`, `ENVIRONMENT=production`, HTTPS, закройте `/dev/*`, настройте SMTP и YooKassa (когда будет).
