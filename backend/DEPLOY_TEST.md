# Тестовый деплой на VPS

## 1. `.env`

Скопируй **полный** рабочий `.env` (все строки: `POSTGRES_*`, `JWT_*`, `DATABASE_URL`, SMTP…) → GitHub secret **`TEST_ENV_FILE`**.  
Не передавай через SSH одной строкой вручную — CI кладёт файл через SCP (см. `dev-cicd.yml`). Без placeholder-текста в паролях.

## 2. GitHub Secrets (environment `test`)

`TEST_SSH_HOST`, `TEST_SSH_PORT`, `TEST_SSH_USER`, `TEST_SSH_PRIVATE_KEY`, `TEST_APP_DIR`, `TEST_ENV_FILE`

## 3. Деплой

```bash
git push origin dev
```

Или Actions → **Dev CI/CD** → Run workflow

## 4. Проверка

```bash
curl http://IP:8000/health
curl -X POST http://IP:8000/dev/test-admin -H "Content-Type: application/json" -d '{"username":"admin","email":"a@t.local","password":"admin"}'
```

Фронт: `VITE_API_BASE_URL=http://IP:8000` в `.env.production` / `.env.local`

## Перенос на другой VPS

См. **`MIGRATE_VDS.md`** (бэкап → новый сервер → `restore.sh` → обновить `TEST_SSH_HOST` и фронт).

## Production

Блок **PRODUCTION** из `.env.example` → secret **`PROD_ENV_FILE`**. См. `backup/PROD_CICD_SETUP.md`.
