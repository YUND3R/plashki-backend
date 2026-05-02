from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["local", "development", "production"] = Field(
        default="local",
        validation_alias=AliasChoices("ENVIRONMENT", "APP_ENV"),
    )

    database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DATABASE_URL"),
    )

    cors_origins: str = Field(
        default="",
        validation_alias=AliasChoices("CORS_ORIGINS"),
    )

    expose_openapi: bool = Field(
        default=True,
        validation_alias=AliasChoices("EXPOSE_OPENAPI"),
    )

    jwt_secret_key: str = Field(
        default="",
        validation_alias=AliasChoices("JWT_SECRET_KEY", "SECRET_KEY"),
    )

    access_token_expire_minutes: int = Field(
        default=60 * 24 * 7,
        ge=1,
        validation_alias=AliasChoices("ACCESS_TOKEN_EXPIRE_MINUTES"),
    )

    upload_dir: str = Field(
        default="uploads",
        validation_alias=AliasChoices("UPLOAD_DIR"),
    )
    upload_max_mb: int = Field(
        default=5,
        ge=1,
        le=50,
        validation_alias=AliasChoices("UPLOAD_MAX_MB"),
    )
    public_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("PUBLIC_BASE_URL"),
        description="Публичный URL API (https://api.example.com): файлы и ссылка подтверждения email, если нет FRONTEND_VERIFY_EMAIL_URL.",
    )
    frontend_reset_password_url: str = Field(
        default="",
        validation_alias=AliasChoices("FRONTEND_RESET_PASSWORD_URL"),
        description="Базовый URL страницы сброса пароля на фронтенде (без token).",
    )
    frontend_verify_email_url: str = Field(
        default="",
        validation_alias=AliasChoices("FRONTEND_VERIFY_EMAIL_URL"),
        description="Базовый URL страницы подтверждения email на фронтенде (без token).",
    )
    reset_token_ttl_minutes: int = Field(
        default=30,
        ge=5,
        le=180,
        validation_alias=AliasChoices("RESET_TOKEN_TTL_MINUTES"),
    )
    email_verification_token_ttl_minutes: int = Field(
        default=60 * 24,
        ge=30,
        le=60 * 24 * 14,
        validation_alias=AliasChoices("EMAIL_VERIFICATION_TOKEN_TTL_MINUTES"),
    )
    smtp_host: str = Field(default="", validation_alias=AliasChoices("SMTP_HOST"))
    smtp_port: int = Field(default=587, ge=1, le=65535, validation_alias=AliasChoices("SMTP_PORT"))
    smtp_user: str = Field(default="", validation_alias=AliasChoices("SMTP_USER"))
    smtp_password: str = Field(default="", validation_alias=AliasChoices("SMTP_PASSWORD"))
    smtp_from_email: str = Field(
        default="",
        validation_alias=AliasChoices("SMTP_FROM_EMAIL"),
    )
    smtp_use_tls: bool = Field(default=True, validation_alias=AliasChoices("SMTP_USE_TLS"))
    smtp_use_ssl: bool = Field(
        default=False,
        validation_alias=AliasChoices("SMTP_USE_SSL"),
        description="Явный SMTP over SSL (например порт 465); иначе при SMTP_PORT=465 используется SSL автоматически.",
    )
    alert_email_to: str = Field(default="", validation_alias=AliasChoices("ALERT_EMAIL_TO"))
    telegram_bot_token: str = Field(default="", validation_alias=AliasChoices("TELEGRAM_BOT_TOKEN"))
    telegram_alert_chat_id: str = Field(
        default="",
        validation_alias=AliasChoices("TELEGRAM_ALERT_CHAT_ID"),
    )

    @model_validator(mode="after")
    def validate_database_url(self) -> "Settings":
        if self.database_url is not None and self.database_url.strip() != "":
            return self
        if self.environment == "local":
            object.__setattr__(
                self,
                "database_url",
                "postgresql+asyncpg://plashki:plashki@localhost:5432/plashki",
            )
            return self
        raise ValueError("DATABASE_URL обязателен в .env для development/production")

    @model_validator(mode="after")
    def validate_production_jwt_secret(self) -> "Settings":
        if self.environment != "production":
            return self
        if self.jwt_secret_key.strip() and len(self.jwt_secret_key.strip()) < 32:
            raise ValueError(
                "JWT_SECRET_KEY (или SECRET_KEY) в production — не короче 32 символов"
            )
        return self

    @property
    def dev_endpoints_enabled(self) -> bool:
        return self.environment != "production"

    @property
    def cors_origin_list(self) -> list[str]:
        raw = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if raw:
            return raw
        # Иначе fetch с Vite (другой origin) даёт «Failed to fetch» без CORS.
        if self.environment in ("local", "development"):
            return [
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:3000",
                "http://127.0.0.1:3000",
            ]
        return []

    @property
    def alert_email_list(self) -> list[str]:
        return [email.strip() for email in self.alert_email_to.split(",") if email.strip()]


settings = Settings()
