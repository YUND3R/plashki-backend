import uuid
from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, computed_field, model_validator

from app.db.base import Role, Subscription


class LoginBody(BaseModel):
    login: str = Field(
        min_length=1,
        max_length=255,
        validation_alias=AliasChoices("login", "username", "email"),
    )
    password: str = Field(min_length=1, max_length=128)


class ForgotPasswordBody(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class ResetPasswordBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    new_password: str = Field(min_length=8, max_length=128)
    token_id: uuid.UUID | None = None
    signature: str | None = Field(None, max_length=64)
    token: str | None = Field(
        None,
        validation_alias=AliasChoices("token"),
    )

    @model_validator(mode="after")
    def _payload(self) -> "ResetPasswordBody":
        sig = (self.signature or "").strip()
        if self.token_id is not None and sig:
            if len(sig) != 64:
                raise ValueError("signature must be 64 hex chars")
            self.signature = sig
            return self
        raw = (self.token or "").strip()
        if raw:
            if len(raw) < 10:
                raise ValueError("token too short")
            self.token = raw
            return self
        raise ValueError("Укажите token_id и signature или устаревший token")


class VerifyEmailBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    token_id: uuid.UUID | None = None
    signature: str | None = Field(None, max_length=64)
    code: str | None = Field(
        None,
        validation_alias=AliasChoices("code", "token"),
    )

    @model_validator(mode="after")
    def _payload(self) -> "VerifyEmailBody":
        sig = (self.signature or "").strip()
        if self.token_id is not None and sig:
            if len(sig) != 64:
                raise ValueError("signature must be 64 hex chars")
            self.signature = sig
            return self
        c = (self.code or "").strip()
        if c:
            if len(c) < 8:
                raise ValueError("code too short")
            self.code = c
            return self
        raise ValueError("Укажите token_id и signature или code (устаревший способ)")


class MessageResponse(BaseModel):
    message: str


class AuthSessionResponse(BaseModel):
    message: str


class PatchMeProfileBody(BaseModel):
    """Смена имени и фамилии аккаунта (только для авторизованного пользователя)."""

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)


from app.schemas.public_media import PublicMediaResponseMixin


class UserMe(PublicMediaResponseMixin, BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str
    first_name: str
    last_name: str
    avatar_url: str | None = None
    nickname: str
    role: Role
    email_verified_at: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None


class AdminUpdateUserAccessBody(BaseModel):
    role: Role | None = None
    subscription: Subscription | None = None


class AdminUserAccessResponse(BaseModel):
    id: uuid.UUID
    role: Role
    subscription: Subscription


class AdminRegisteredUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    first_name: str
    email: str
    role: Role
    subscription: Subscription
    created_at: datetime
