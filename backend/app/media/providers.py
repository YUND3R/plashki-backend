from functools import lru_cache

from app.core.config import settings
from app.media.adapters import LocalFileStorage
from app.media.ports import FileStorage


@lru_cache
def get_file_storage() -> FileStorage:
    return LocalFileStorage(settings.upload_dir, settings.public_base_url)
