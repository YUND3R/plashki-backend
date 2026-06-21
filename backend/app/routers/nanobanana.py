import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.deps.auth import get_current_user_id
from app.schemas.nanobanana import NanoBananaProcessResponse
from app.services.nanobanana import process_with_nanobanana
from app.services.photo_storage import ALLOWED_IMAGE_TYPES, public_file_url

router = APIRouter(prefix="/images", tags=["images"])


_EXT_BY_MIME: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


def _upload_root() -> Path:
    p = Path(settings.upload_dir)
    if not p.is_absolute():
        p = Path.cwd() / p
    p.mkdir(parents=True, exist_ok=True)
    return p


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

    out_bytes, out_mime = await process_with_nanobanana(
        image_bytes=body,
        source_mime=ct,
        prompt=prompt,
        negative_prompt=negative_prompt,
    )
    ext = _EXT_BY_MIME.get(out_mime)
    if ext is None:
        raise HTTPException(
            status_code=502,
            detail=f"Nano Banana вернул неподдерживаемый mime: {out_mime or 'unknown'}",
        )

    name = f"{uuid.uuid4().hex}{ext}"
    (_upload_root() / name).write_bytes(out_bytes)

    return NanoBananaProcessResponse(
        url=public_file_url(request, name),
        output_mime=out_mime,
        size_bytes=len(out_bytes),
    )
