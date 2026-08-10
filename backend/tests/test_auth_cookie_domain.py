from app.core.config import Settings


def test_derives_auth_cookie_domain_from_public_api_url() -> None:
    settings = Settings(
        ENVIRONMENT="development",
        DATABASE_URL="postgresql+asyncpg://plashki:plashki@db:5432/plashki",
        PUBLIC_BASE_URL="https://api.plash-ki.ru",
        CORS_ORIGINS="https://plash-ki.ru",
        JWT_SECRET_KEY="x" * 32,
        FRONTEND_VERIFY_EMAIL_URL="https://plash-ki.ru/verify-email",
        FRONTEND_RESET_PASSWORD_URL="https://plash-ki.ru/reset-password",
    )
    assert settings.auth_cookie_domain == ".plash-ki.ru"


def test_keeps_explicit_auth_cookie_domain() -> None:
    settings = Settings(
        ENVIRONMENT="development",
        DATABASE_URL="postgresql+asyncpg://plashki:plashki@db:5432/plashki",
        PUBLIC_BASE_URL="https://api.plash-ki.ru",
        AUTH_COOKIE_DOMAIN=".custom.example",
        CORS_ORIGINS="https://plash-ki.ru",
        JWT_SECRET_KEY="x" * 32,
        FRONTEND_VERIFY_EMAIL_URL="https://plash-ki.ru/verify-email",
        FRONTEND_RESET_PASSWORD_URL="https://plash-ki.ru/reset-password",
    )
    assert settings.auth_cookie_domain == ".custom.example"
