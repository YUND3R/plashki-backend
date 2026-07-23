from app.core.config import settings
from app.nanobanana.adapters import HttpNanoBananaClient
from app.nanobanana.ports import NanoBananaClient


def get_nanobanana_client() -> NanoBananaClient:
    return HttpNanoBananaClient(
        api_key=settings.nanobanana_api_key,
        base_url=settings.nanobanana_base_url,
        path=settings.nanobanana_path,
        model=settings.nanobanana_model,
        timeout_seconds=float(settings.nanobanana_timeout_seconds),
    )
