from app.services.nanobanana import (
    _as_full_url,
    _extract_base64_field,
    _extract_image_url,
    _guess_mime_from_bytes,
)


def test_as_full_url_normalizes_slashes() -> None:
    assert _as_full_url("https://api.example.com/", "/v1/edit") == "https://api.example.com/v1/edit"
    assert _as_full_url("https://api.example.com", "v1/edit") == "https://api.example.com/v1/edit"


def test_guess_mime_from_bytes_detects_common_formats() -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"rest"
    jpeg = b"\xff\xd8\xff" + b"rest"
    webp = b"RIFF" + b"1234" + b"WEBP" + b"rest"
    unknown = b"abc"

    assert _guess_mime_from_bytes(png) == "image/png"
    assert _guess_mime_from_bytes(jpeg) == "image/jpeg"
    assert _guess_mime_from_bytes(webp) == "image/webp"
    assert _guess_mime_from_bytes(unknown) == "application/octet-stream"


def test_extract_base64_field_prefers_top_level() -> None:
    data = {
        "image_base64": "  AAAA  ",
        "data": [{"b64_json": "BBBB"}],
    }
    assert _extract_base64_field(data) == "AAAA"


def test_extract_base64_field_reads_nested_data() -> None:
    data = {"data": [{"b64_json": "BBBB"}]}
    assert _extract_base64_field(data) == "BBBB"


def test_extract_image_url_reads_top_level_and_nested() -> None:
    assert _extract_image_url({"image_url": " https://x/y.png "}) == "https://x/y.png"
    assert _extract_image_url({"data": [{"url": "https://x/z.png"}]}) == "https://x/z.png"
    assert _extract_image_url({"data": []}) is None
