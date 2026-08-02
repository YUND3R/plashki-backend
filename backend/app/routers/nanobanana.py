import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.deps.auth import get_current_user_id
from app.schemas.nanobanana import NanoBananaProcessResponse
from app.media.application import ALLOWED_IMAGE_TYPES, InvalidUpload
from app.media.ports import FileStorage
from app.media.providers import get_file_storage
from app.media.public_urls import resolve_public_base_url
from app.nanobanana.application import process_and_store_image
from app.nanobanana.ports import NanoBananaClient
from app.nanobanana.providers import get_nanobanana_client

router = APIRouter(prefix="/images", tags=["images"])


@router.post(
    "/nanobanana/process",
    response_model=NanoBananaProcessResponse,
    summary="Обработать изображение через Nano Banana",
    description="Нужен JWT+CSRF. Сохраняет результат в /files и возвращает URL.",
)
async def process_image_via_nanobanana(
    request: Request,
    file: UploadFile = File(..., description="Исходное изображение"),
    prompt: str = Form(..., min_length=1, max_length=4000),
    negative_prompt: str | None = Form(default=None, max_length=4000),
    _owner_user_id: uuid.UUID = Depends(get_current_user_id),
    _session: AsyncSession = Depends(get_session),
    client: NanoBananaClient = Depends(get_nanobanana_client),
    storage: FileStorage = Depends(get_file_storage),
) -> NanoBananaProcessResponse:
    ct = (file.content_type or "").split(";")[0].strip().lower()
    if ct not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Недопустимый тип файла: {ct or 'unknown'}. Разрешены: JPEG, PNG, WebP, GIF.",
        )

    body = await file.read()
    if len(body) == 0:
        raise HTTPException(status_code=400, detail="Пустой файл.")
    max_bytes = settings.upload_max_mb * 1024 * 1024
    if len(body) > max_bytes:
        raise HTTPException(status_code=413, detail=f"Файл больше {settings.upload_max_mb} МБ")

    try:
        url, out_mime, size = await process_and_store_image(
            client,
            storage,
            image_bytes=body,
            source_mime=ct,
            prompt=prompt,
            negative_prompt=negative_prompt,
            request_base_url=resolve_public_base_url(
                request_base_url=str(request.base_url),
            ),
        )
    except InvalidUpload as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return NanoBananaProcessResponse(
        url=url,
        output_mime=out_mime,
        size_bytes=size,
    )
