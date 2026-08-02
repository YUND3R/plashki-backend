from __future__ import annotations

from app.core.config import settings

PUBLIC_FILES_MARKER = "/files/"


def extract_public_file_path(url: str) -> str | None:
    value = url.strip()
    if not value:
        return None
    index = value.rfind(PUBLIC_FILES_MARKER)
    if index < 0:
        return None
    path = value[index:].split("?", 1)[0].strip()
    if not path.startswith(PUBLIC_FILES_MARKER):
        return None
    filename = path[len(PUBLIC_FILES_MARKER) :]
    if not filename:
        return None
    return path


def resolve_public_base_url(*, request_base_url: str = "") -> str:
    pub = settings.public_base_url.strip().rstrip("/")
    if pub:
        return pub
    return request_base_url.strip().rstrip("/")


def build_public_file_url(
    filename: str,
    *,
    request_base_url: str = "",
) -> str:
    base = resolve_public_base_url(request_base_url=request_base_url)
    path = f"{PUBLIC_FILES_MARKER}{filename.lstrip('/')}"
    return f"{base}{path}" if base else path


def rewrite_public_file_url(url: str | None) -> str | None:
    if url is None:
        return None
    path = extract_public_file_path(url)
    if path is None:
        return url.strip() or None
    base = settings.public_base_url.strip().rstrip("/")
    if not base:
        return url.strip()
    return f"{base}{path}"


def rewrite_public_file_urls(urls: list[str]) -> list[str]:
    return [rewrite_public_file_url(item) or item for item in urls]


def public_file_urls_equal(left: str, right: str) -> bool:
    left_path = extract_public_file_path(left.strip())
    right_path = extract_public_file_path(right.strip())
    if left_path is not None and right_path is not None:
        return left_path == right_path
    return left.strip() == right.strip()


def public_file_url_in_list(url: str, urls: list[str]) -> bool:
    return any(public_file_urls_equal(url, item) for item in urls)
