from pydantic import field_serializer

from app.media.public_urls import rewrite_public_file_url, rewrite_public_file_urls


class PublicMediaResponseMixin:
    @field_serializer("avatar_url", check_fields=False)
    def _serialize_avatar_url(self, value: str | None) -> str | None:
        return rewrite_public_file_url(value)

    @field_serializer("photo_url", check_fields=False)
    def _serialize_photo_url(self, value: str | None) -> str | None:
        return rewrite_public_file_url(value)

    @field_serializer("lobby_photo_url", check_fields=False)
    def _serialize_lobby_photo_url(self, value: str | None) -> str | None:
        return rewrite_public_file_url(value)

    @field_serializer("url", check_fields=False)
    def _serialize_public_file_url(self, value: str | None) -> str | None:
        return rewrite_public_file_url(value)

    @field_serializer("photo_urls", check_fields=False)
    def _serialize_photo_urls(self, value: list[str]) -> list[str]:
        return rewrite_public_file_urls(value)
