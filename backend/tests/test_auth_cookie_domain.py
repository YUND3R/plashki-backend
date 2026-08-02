from app.core.config import Settings


def test_derives_auth_cookie_domain_from_public_api_url() -> None:
    settings = Settings(
        ENVIRONMENT="development",
        DATABASE_URL="postgresql+asyncpg://plashki:plashki@db:5432/plashki",
        PUBLIC_BASE_URL="https://api.plash-ki.ru",
    )
    assert settings.auth_cookie_domain == ".plash-ki.ru"


def test_keeps_explicit_auth_cookie_domain() -> None:
    settings = Settings(
        ENVIRONMENT="development",
        DATABASE_URL="postgresql+asyncpg://plashki:plashki@db:5432/plashki",
        PUBLIC_BASE_URL="https://api.plash-ki.ru",
        AUTH_COOKIE_DOMAIN=".custom.example",
    )
    assert settings.auth_cookie_domain == ".custom.example"
