from app.nanobanana.adapters import (
    as_full_url as _as_full_url,
    extract_base64_field as _extract_base64_field,
    extract_image_url as _extract_image_url,
    guess_mime_from_bytes as _guess_mime_from_bytes,
)
from app.nanobanana.providers import get_nanobanana_client


async def process_with_nanobanana(
    *,
    image_bytes: bytes,
    source_mime: str,
    prompt: str,
    negative_prompt: str | None = None,
) -> tuple[bytes, str]:
    return await get_nanobanana_client().process(
        image_bytes=image_bytes,
        source_mime=source_mime,
        prompt=prompt,
        negative_prompt=negative_prompt,
    )
