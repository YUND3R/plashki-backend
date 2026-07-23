import re
import uuid
from dataclasses import dataclass

from app.media.ports import FileStorage

ALLOWED_IMAGE_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
_STORED_UPLOAD_NAME = re.compile(
    r"^[a-f0-9]{32}\.(jpg|png|webp|gif)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class InvalidUpload(ValueError):
    status_code: int
    detail: str


def upload_image(
    storage: FileStorage,
    *,
    original_filename: str | None,
    content_type: str | None,
    body: bytes,
    max_mb: int,
    request_base_url: str = "",
) -> str:
    if not original_filename:
        raise InvalidUpload(400, "Пустое имя файла")
    mime = (content_type or "").split(";")[0].strip().lower()
    extension = ALLOWED_IMAGE_TYPES.get(mime)
    if extension is None:
        raise InvalidUpload(
            400,
            f"Недопустимый тип файла: {mime or 'unknown'}. Разрешены: JPEG, PNG, WebP, GIF.",
        )
    if len(body) > max_mb * 1024 * 1024:
        raise InvalidUpload(413, f"Файл больше {max_mb} МБ")
    if not body:
        raise InvalidUpload(400, "Пустой файл")
    filename = f"{uuid.uuid4().hex}{extension}"
    storage.save(filename, body)
    return storage.public_url(filename, request_base_url)


def store_generated_image(
    storage: FileStorage,
    *,
    body: bytes,
    mime: str,
    request_base_url: str = "",
) -> str:
    extension = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
    }.get(mime)
    if extension is None:
        raise InvalidUpload(
            502,
            f"Nano Banana вернул неподдерживаемый mime: {mime or 'unknown'}",
        )
    filename = f"{uuid.uuid4().hex}{extension}"
    storage.save(filename, body)
    return storage.public_url(filename, request_base_url)


def public_file_url(
    storage: FileStorage,
    filename: str,
    request_base_url: str = "",
) -> str:
    return storage.public_url(filename, request_base_url)


def delete_public_file(storage: FileStorage, public_url: str | None) -> None:
    if not public_url or not str(public_url).strip():
        return
    marker = "/files/"
    value = str(public_url).strip()
    index = value.rfind(marker)
    if index < 0:
        return
    filename = value[index + len(marker) :].split("?", 1)[0].strip()
    if _STORED_UPLOAD_NAME.fullmatch(filename):
        storage.delete(filename)
