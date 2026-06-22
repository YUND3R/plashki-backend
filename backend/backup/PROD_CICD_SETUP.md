# Production CI/CD setup

This project now includes `.github/workflows/prod-cicd.yml`.

Pipeline stages:
1. `quality` - lint and tests.
2. `build-and-push` - build `backend/Dockerfile` and push image to GHCR.
3. `deploy-production` - upload compose file and deploy on remote host over SSH.

## 1) Prepare GitHub environment

Create GitHub Environment: `production`.

Recommended protection:
- Required reviewers for deploy approvals.
- Restrict deployment branches (`main` and/or `prod`).

## 2) Configure secrets in `production` environment

Required:
- `PROD_SSH_HOST` - production server host/IP.
- `PROD_SSH_PORT` - usually `22`.
- `PROD_SSH_USER` - SSH username.
- `PROD_SSH_PRIVATE_KEY` - private key for deploy user.
- `PROD_APP_DIR` - absolute deploy path on server, e.g. `/opt/plashki`.
- `GHCR_USERNAME` - GitHub username/org with package read access.
- `GHCR_TOKEN` - GitHub PAT with `read:packages`.
- `PROD_ENV_FILE` - full multiline contents of backend production `.env`.

Example `PROD_ENV_FILE` source: `backend/.env.prod.example` (fill with real values).

## 3) Prepare production host

Install on server:
- Docker engine
- Docker Compose plugin (`docker compose`)

Create deploy directory:
- `mkdir -p /opt/plashki`

## 4) Trigger deploy

Automatic:
- Push to `main` or `prod` with backend changes.

Manual:
- Actions -> `Prod CI/CD` -> `Run workflow` -> keep `deploy=true`.

## 5) Rollback

On server:
- Edit `.env` in `${PROD_APP_DIR}` and set `IMAGE_TAG` to a previous tag (`sha-...` or branch tag).
- Run:
  - `docker compose -f docker-compose.prod.yml pull`
  - `docker compose -f docker-compose.prod.yml up -d`
