from app.media.application import store_generated_image
from app.media.ports import FileStorage
from app.nanobanana.ports import NanoBananaClient


async def process_and_store_image(
    client: NanoBananaClient,
    storage: FileStorage,
    *,
    image_bytes: bytes,
    source_mime: str,
    prompt: str,
    negative_prompt: str | None,
    request_base_url: str,
) -> tuple[str, str, int]:
    output, output_mime = await client.process(
        image_bytes=image_bytes,
        source_mime=source_mime,
        prompt=prompt,
        negative_prompt=negative_prompt,
    )
    url = store_generated_image(
        storage,
        body=output,
        mime=output_mime,
        request_base_url=request_base_url,
    )
    return url, output_mime, len(output)
