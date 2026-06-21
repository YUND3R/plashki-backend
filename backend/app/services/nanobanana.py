import base64
import binascii
from typing import Any

import httpx
from fastapi import HTTPException

from app.core.config import settings


def _as_full_url(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


def _guess_mime_from_bytes(body: bytes) -> str:
    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if body[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if body.startswith(b"RIFF") and body[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def _extract_base64_field(data: Any) -> str | None:
    candidates = []
    if isinstance(data, dict):
        candidates.extend(
            [
                data.get("image_base64"),
                data.get("b64_json"),
                data.get("image"),
                data.get("output"),
            ]
        )
        if isinstance(data.get("data"), list) and data["data"]:
            first = data["data"][0]
            if isinstance(first, dict):
                candidates.extend([first.get("b64_json"), first.get("image_base64"), first.get("image")])
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_image_url(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    direct = data.get("image_url")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    if isinstance(data.get("data"), list) and data["data"]:
        first = data["data"][0]
        if isinstance(first, dict):
            url = first.get("url")
            if isinstance(url, str) and url.strip():
                return url.strip()
    return None


async def process_with_nanobanana(
    *,
    image_bytes: bytes,
    source_mime: str,
    prompt: str,
    negative_prompt: str | None = None,
) -> tuple[bytes, str]:
    api_key = settings.nanobanana_api_key.strip()
    base_url = settings.nanobanana_base_url.strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="NANOBANANA_API_KEY не задан.")
    if not base_url:
        raise HTTPException(status_code=500, detail="NANOBANANA_BASE_URL не задан.")
    if not settings.nanobanana_model.strip():
        raise HTTPException(status_code=500, detail="NANOBANANA_MODEL не задан.")

    payload: dict[str, Any] = {
        "model": settings.nanobanana_model.strip(),
        "prompt": prompt.strip(),
        "image_base64": base64.b64encode(image_bytes).decode("ascii"),
        "input_mime": source_mime,
    }
    if negative_prompt and negative_prompt.strip():
        payload["negative_prompt"] = negative_prompt.strip()

    url = _as_full_url(base_url, settings.nanobanana_path)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    timeout = httpx.Timeout(float(settings.nanobanana_timeout_seconds))
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Nano Banana недоступен: {exc}") from exc

        if resp.status_code >= 400:
            detail = resp.text.strip()[:500] or f"HTTP {resp.status_code}"
            raise HTTPException(status_code=502, detail=f"Ошибка Nano Banana: {detail}")

        ctype = (resp.headers.get("content-type") or "").lower()
        if ctype.startswith("image/"):
            return resp.content, ctype.split(";")[0].strip()

        data = resp.json()

        b64 = _extract_base64_field(data)
        if b64:
            raw_b64 = b64.split(",", 1)[1] if "," in b64 and b64.startswith("data:") else b64
            try:
                out = base64.b64decode(raw_b64, validate=False)
            except binascii.Error as exc:
                raise HTTPException(status_code=502, detail="Некорректный base64 от Nano Banana.") from exc
            return out, _guess_mime_from_bytes(out)

        image_url = _extract_image_url(data)
        if image_url:
            try:
                img_resp = await client.get(image_url)
            except httpx.RequestError as exc:
                raise HTTPException(status_code=502, detail=f"Не удалось скачать результат Nano Banana: {exc}") from exc
            if img_resp.status_code >= 400:
                raise HTTPException(status_code=502, detail="Nano Banana вернул URL результата, но файл недоступен.")
            out_mime = (img_resp.headers.get("content-type") or "").split(";")[0].strip().lower()
            return img_resp.content, out_mime or _guess_mime_from_bytes(img_resp.content)

    raise HTTPException(status_code=502, detail="Nano Banana вернул неожиданный формат ответа.")
