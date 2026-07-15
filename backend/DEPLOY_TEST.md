# Тестовый деплой на VPS

## 1. `.env`

Скопируй блок **TEST VPS** из `.env.example`, раскомментируй, подставь IP → вставь в GitHub secret **`TEST_ENV_FILE`**.

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

Фронт: `VITE_API_URL=http://IP:8000` в `.env.local`

## Production

Блок **PRODUCTION** из `.env.example` → secret **`PROD_ENV_FILE`**. См. `backup/PROD_CICD_SETUP.md`.
