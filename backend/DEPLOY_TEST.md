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
```

Фронт: `VITE_API_BASE_URL=http://IP:8000` в `.env.production` / `.env.local`

`/dev/*` доступен только при `ENVIRONMENT=local` и не должен использоваться на VPS.
Для публичного Nginx включи HTTPS redirect, `server_tokens off`, HSTS после проверки всех
поддоменов и ограничение запросов. Production compose публикует API только на `127.0.0.1`;
Nginx должен проксировать на этот адрес и быть единственной внешней точкой входа:

```nginx
limit_req_zone $binary_remote_addr zone=auth:10m rate=10r/m;

location ~ ^/auth/(login|register|forgot-password|resend-verification)$ {
    limit_req zone=auth burst=10 nodelay;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_pass http://127.0.0.1:8000;
}
```

## Production

Блок **PRODUCTION** из `.env.example` → secret **`PROD_ENV_FILE`**. См. `backup/PROD_CICD_SETUP.md`.
