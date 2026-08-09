import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.password import validate_password_strength
from app.core.safe_url import validate_outbound_https_url


def _deployed_settings(**values) -> Settings:
    defaults = {
        "ENVIRONMENT": "development",
        "DATABASE_URL": "postgresql+asyncpg://plashki:plashki@db:5432/plashki",
        "CORS_ORIGINS": "https://plash-ki.ru",
        "JWT_SECRET_KEY": "x" * 32,
    }
    defaults.update(values)
    return Settings(**defaults)


def test_dev_routes_are_local_only() -> None:
    assert Settings(ENVIRONMENT="local").dev_endpoints_enabled is True
    assert _deployed_settings().dev_endpoints_enabled is False


@pytest.mark.parametrize("secret", ["", "short"])
def test_deployed_environment_requires_strong_jwt_secret(secret: str) -> None:
    with pytest.raises(ValidationError):
        _deployed_settings(JWT_SECRET_KEY=secret)


def test_production_rejects_openapi() -> None:
    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="production",
            DATABASE_URL="postgresql+asyncpg://plashki:plashki@db:5432/plashki",
            CORS_ORIGINS="https://plash-ki.ru",
            JWT_SECRET_KEY="x" * 32,
            FRONTEND_VERIFY_EMAIL_URL="https://plash-ki.ru/verify-email",
            FRONTEND_RESET_PASSWORD_URL="https://plash-ki.ru/reset-password",
            EXPOSE_OPENAPI=True,
        )


def test_password_policy_requires_eight_characters() -> None:
    assert validate_password_strength("short") is not None
    assert validate_password_strength("long-enough") is None


@pytest.mark.parametrize(
    "url",
    [
        "http://provider.example/result.png",
        "https://127.0.0.1/result.png",
        "https://evil.example/result.png",
        "https://user:pass@provider.example/result.png",
    ],
)
def test_outbound_result_url_rejects_unsafe_destinations(url: str) -> None:
    with pytest.raises(ValueError):
        validate_outbound_https_url(url, allowed_hosts=frozenset({"provider.example"}))


def test_outbound_result_url_allows_known_https_host() -> None:
    assert (
        validate_outbound_https_url(
            "https://provider.example/image.png",
            allowed_hosts=frozenset({"provider.example"}),
        )
        == "https://provider.example/image.png"
    )
