from typing import Protocol


class NanoBananaClient(Protocol):
    async def process(
        self,
        *,
        image_bytes: bytes,
        source_mime: str,
        prompt: str,
        negative_prompt: str | None = None,
    ) -> tuple[bytes, str]: ...
