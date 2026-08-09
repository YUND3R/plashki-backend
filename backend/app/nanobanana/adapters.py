import base64
import binascii
from typing import Any

import httpx
from fastapi import HTTPException

from app.core.safe_url import allowed_host_from_url, validate_outbound_https_url

def as_full_url(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


def guess_mime_from_bytes(body: bytes) -> str:
    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if body[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if body.startswith(b"RIFF") and body[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def extract_base64_field(data: Any) -> str | None:
    candidates = []
    if isinstance(data, dict):
        candidates.extend(
            [data.get("image_base64"), data.get("b64_json"), data.get("image"), data.get("output")]
        )
        if isinstance(data.get("data"), list) and data["data"]:
            first = data["data"][0]
            if isinstance(first, dict):
                candidates.extend([first.get("b64_json"), first.get("image_base64"), first.get("image")])
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def extract_image_url(data: Any) -> str | None:
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


class HttpNanoBananaClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        path: str,
        model: str,
        timeout_seconds: float,
        allowed_result_hosts: frozenset[str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key.strip()
        self._base_url = base_url.strip()
        self._path = path
        self._model = model.strip()
        self._timeout = timeout_seconds
        self._transport = transport
        self._allowed_result_hosts = allowed_result_hosts or frozenset(
            {allowed_host_from_url(self._base_url)}
        )

    async def process(self, *, image_bytes: bytes, source_mime: str, prompt: str, negative_prompt: str | None = None) -> tuple[bytes, str]:
        if not self._api_key:
            raise HTTPException(status_code=500, detail="NANOBANANA_API_KEY не задан.")
        if not self._base_url:
            raise HTTPException(status_code=500, detail="NANOBANANA_BASE_URL не задан.")
        if not self._model:
            raise HTTPException(status_code=500, detail="NANOBANANA_MODEL не задан.")
        payload: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt.strip(),
            "image_base64": base64.b64encode(image_bytes).decode("ascii"),
            "input_mime": source_mime,
        }
        if negative_prompt and negative_prompt.strip():
            payload["negative_prompt"] = negative_prompt.strip()
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout),
            transport=self._transport,
        ) as client:
            try:
                response = await client.post(
                    as_full_url(self._base_url, self._path),
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                )
            except httpx.RequestError as exc:
                raise HTTPException(status_code=502, detail=f"Nano Banana недоступен: {exc}") from exc
            if response.status_code >= 400:
                detail = response.text.strip()[:500] or f"HTTP {response.status_code}"
                raise HTTPException(status_code=502, detail=f"Ошибка Nano Banana: {detail}")
            content_type = (response.headers.get("content-type") or "").lower()
            if content_type.startswith("image/"):
                return response.content, content_type.split(";")[0].strip()
            data = response.json()
            encoded = extract_base64_field(data)
            if encoded:
                raw = encoded.split(",", 1)[1] if encoded.startswith("data:") and "," in encoded else encoded
                try:
                    output = base64.b64decode(raw, validate=False)
                except binascii.Error as exc:
                    raise HTTPException(status_code=502, detail="Некорректный base64 от Nano Banana.") from exc
                return output, guess_mime_from_bytes(output)
            image_url = extract_image_url(data)
            if image_url:
                try:
                    safe_url = validate_outbound_https_url(
                        image_url, allowed_hosts=self._allowed_result_hosts
                    )
                    image_response = await client.get(safe_url, follow_redirects=False)
                except (ValueError, httpx.RequestError) as exc:
                    raise HTTPException(status_code=502, detail=f"Не удалось скачать результат Nano Banana: {exc}") from exc
                if image_response.status_code >= 400:
                    raise HTTPException(status_code=502, detail="Nano Banana вернул URL результата, но файл недоступен.")
                mime = (image_response.headers.get("content-type") or "").split(";")[0].strip().lower()
                if not mime.startswith("image/"):
                    raise HTTPException(status_code=502, detail="Nano Banana вернул результат не в формате изображения.")
                if len(image_response.content) > 10 * 1024 * 1024:
                    raise HTTPException(status_code=502, detail="Результат Nano Banana слишком большой.")
                return image_response.content, mime or guess_mime_from_bytes(image_response.content)
        raise HTTPException(status_code=502, detail="Nano Banana вернул неожиданный формат ответа.")
