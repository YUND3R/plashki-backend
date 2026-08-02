from app.media.public_urls import (
    build_public_file_url,
    extract_public_file_path,
    public_file_url_in_list,
    public_file_urls_equal,
    rewrite_public_file_url,
)


def test_rewrite_public_file_url_uses_public_base_url(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.media.public_urls.settings.public_base_url",
        "https://api.plash-ki.ru",
    )
    old = "http://135.106.167.24:8000/files/abc123.jpg"
    assert rewrite_public_file_url(old) == "https://api.plash-ki.ru/files/abc123.jpg"


def test_rewrite_public_file_url_keeps_unknown_urls(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.media.public_urls.settings.public_base_url",
        "https://api.plash-ki.ru",
    )
    external = "https://cdn.example/photo.jpg"
    assert rewrite_public_file_url(external) == external


def test_public_file_urls_equal_ignores_host() -> None:
    left = "http://135.106.167.24:8000/files/abc123.jpg"
    right = "https://api.plash-ki.ru/files/abc123.jpg"
    assert public_file_urls_equal(left, right)
    assert public_file_url_in_list(right, [left])


def test_extract_public_file_path() -> None:
    assert extract_public_file_path("https://x/files/a.jpg?q=1") == "/files/a.jpg"


def test_build_public_file_url_prefers_settings(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.media.public_urls.settings.public_base_url",
        "https://api.plash-ki.ru",
    )
    assert (
        build_public_file_url("abc.jpg", request_base_url="http://localhost:8000")
        == "https://api.plash-ki.ru/files/abc.jpg"
    )
