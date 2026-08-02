from fastapi import HTTPException, Request, UploadFile

from app.core.config import settings
from app.media.application import (
    ALLOWED_IMAGE_TYPES,
    InvalidUpload,
    delete_public_file,
    public_file_url as build_public_file_url,
    upload_image,
)
from app.media.providers import get_file_storage
from app.media.public_urls import resolve_public_base_url


def remove_stored_file_if_ours(public_url: str | None) -> None:
    delete_public_file(get_file_storage(), public_url)


def public_file_url(request: Request, filename: str) -> str:
    return build_public_file_url(
        get_file_storage(),
        filename,
        resolve_public_base_url(request_base_url=str(request.base_url)),
    )


async def save_image_upload(file: UploadFile, request: Request) -> str:
    """Сохраняет изображение на диск, возвращает публичный URL. Бросает HTTPException при ошибке."""
    body = await file.read()
    try:
        return upload_image(
            get_file_storage(),
            original_filename=file.filename,
            content_type=file.content_type,
            body=body,
            max_mb=settings.upload_max_mb,
            request_base_url=resolve_public_base_url(
                request_base_url=str(request.base_url),
            ),
        )
    except InvalidUpload as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


async def save_player_card_image(file: UploadFile, request: Request) -> str:
    return await save_image_upload(file, request)
