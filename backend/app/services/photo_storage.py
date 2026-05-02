import re
import uuid
from pathlib import Path

from fastapi import HTTPException, Request, UploadFile

from app.core.config import settings

# Имена из save_image_upload: 32 hex + расширение (удаление старого аватара при замене).
_STORED_UPLOAD_NAME: re.Pattern[str] = re.compile(
    r"^[a-f0-9]{32}\.(jpg|png|webp|gif)$",
    re.IGNORECASE,
)

ALLOWED_IMAGE_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _upload_root() -> Path:
    p = Path(settings.upload_dir)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


def remove_stored_file_if_ours(public_url: str | None) -> None:
    """Удаляет файл из upload_dir, если URL указывает на наш `/files/<uuid>.<ext>`."""
    if not public_url or not str(public_url).strip():
        return
    s = str(public_url).strip()
    marker = "/files/"
    idx = s.rfind(marker)
    if idx < 0:
        return
    name = s[idx + len(marker) :].split("?", 1)[0].strip()
    if not _STORED_UPLOAD_NAME.match(name):
        return
    path = _upload_root() / name
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def public_file_url(request: Request, filename: str) -> str:
    path = f"/files/{filename}"
    base = settings.public_base_url.strip().rstrip("/")
    if base:
        return f"{base}{path}"
    return str(request.base_url).rstrip("/") + path


async def save_image_upload(file: UploadFile, request: Request) -> str:
    """Сохраняет изображение на диск, возвращает публичный URL. Бросает HTTPException при ошибке."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Пустое имя файла")

    ct = (file.content_type or "").split(";")[0].strip().lower()
    ext = ALLOWED_IMAGE_TYPES.get(ct)
    if ext is None:
        raise HTTPException(
            status_code=400,
            detail=f"Недопустимый тип файла: {ct or 'unknown'}. Разрешены: JPEG, PNG, WebP, GIF.",
        )

    max_bytes = settings.upload_max_mb * 1024 * 1024
    body = await file.read()
    if len(body) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Файл больше {settings.upload_max_mb} МБ",
        )
    if len(body) == 0:
        raise HTTPException(status_code=400, detail="Пустой файл")

    root = _upload_root()
    root.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    (root / name).write_bytes(body)
    return public_file_url(request, name)


async def save_player_card_image(file: UploadFile, request: Request) -> str:
    return await save_image_upload(file, request)
