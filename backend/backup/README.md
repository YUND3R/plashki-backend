# Backup

Скрипты для бэкапа/восстановления PostgreSQL и папки `uploads`.

## Что сохраняется

- `db.dump` — дамп базы `plashki` (формат `pg_dump -Fc`)
- `uploads.tar.gz` — все файлы из `/app/uploads`
- `checksums.txt` — SHA256 суммы

## Требования

- Docker и Docker Compose
- Запущенные сервисы `db` и `api`
- Запускать из папки `backend`

## Бэкап

```powershell
cd backend
powershell -ExecutionPolicy Bypass -File .\backup\backup.ps1
```

Опционально:

```powershell
powershell -ExecutionPolicy Bypass -File .\backup\backup.ps1 -OutputRoot "D:\plashki-backups"
```

## Восстановление

```powershell
cd backend
powershell -ExecutionPolicy Bypass -File .\backup\restore.ps1 -BackupDir "C:\backups\plashki\20260621_200000"
```

## Linux / VPS (тестовый деплой)

Из каталога на сервере (`/opt/plashki-test`):

```bash
export COMPOSE_FILE=docker-compose.test.yml
chmod +x backup/backup.sh backup/restore.sh
./backup/backup.sh
./backup/restore.sh ./backups/20260720_120000
```

## Примечание

Перед восстановлением убедись, что это нужный проект/окружение, потому что данные базы и `uploads` будут перезаписаны.
