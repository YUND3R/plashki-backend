import httpx
import pytest

from app.media.application import delete_public_file, upload_image
from app.nanobanana.adapters import HttpNanoBananaClient
from app.nanobanana.application import process_and_store_image
from app.notifications.adapters import HttpTelegramNotifier
from app.sessions.adapters.gomafia import parse_gomafia_html


class FakeStorage:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def save(self, filename: str, body: bytes) -> None:
        self.files[filename] = body

    def delete(self, filename: str) -> None:
        self.deleted.append(filename)

    def public_url(self, filename: str, request_base_url: str = "") -> str:
        return f"{request_base_url}/files/{filename}"


def test_media_use_cases_work_through_file_storage_port() -> None:
    storage = FakeStorage()
    url = upload_image(
        storage,
        original_filename="avatar.png",
        content_type="image/png",
        body=b"png",
        max_mb=1,
        request_base_url="https://api.example",
    )
    filename = url.rsplit("/", 1)[-1]
    assert storage.files[filename] == b"png"

    delete_public_file(storage, url)
    assert storage.deleted == [filename]


class FakeNanoBanana:
    async def process(self, **_kwargs) -> tuple[bytes, str]:
        return b"\x89PNG\r\n\x1a\nresult", "image/png"


@pytest.mark.asyncio
async def test_nanobanana_application_uses_client_and_storage_ports() -> None:
    storage = FakeStorage()
    url, mime, size = await process_and_store_image(
        FakeNanoBanana(),
        storage,
        image_bytes=b"source",
        source_mime="image/png",
        prompt="improve",
        negative_prompt=None,
        request_base_url="https://api.example",
    )
    assert url.startswith("https://api.example/files/")
    assert mime == "image/png"
    assert size == len(next(iter(storage.files.values())))


@pytest.mark.asyncio
async def test_nanobanana_http_adapter_accepts_mock_transport() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret"
        return httpx.Response(200, headers={"content-type": "image/png"}, content=b"result")

    client = HttpNanoBananaClient(
        api_key="secret",
        base_url="https://nano.example",
        path="/edit",
        model="model",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )
    assert await client.process(
        image_bytes=b"source",
        source_mime="image/png",
        prompt="edit",
    ) == (b"result", "image/png")


def test_gomafia_parser_is_testable_without_network() -> None:
    seats = "".join(f"<tr><td>{n}</td><td>Player {n}</td></tr>" for n in range(1, 6))
    tournament = parse_gomafia_html(
        "https://gomafia.pro/tournament/42",
        f"<html><h1>Fixture Cup</h1><h2>Тур 1</h2>"
        f"<table><tr><th>Место</th><th>Стол 1</th></tr>{seats}</table></html>",
    )
    assert tournament.title == "Fixture Cup"
    assert tournament.tables[0].tour_no == 1
    assert [seat.nickname for seat in tournament.tables[0].seats] == [
        f"Player {n}" for n in range(1, 6)
    ]


def test_telegram_adapter_accepts_mock_transport() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.telegram.org"
        return httpx.Response(200, json={"ok": True})

    notifier = HttpTelegramNotifier(
        token="token",
        chat_id="chat",
        transport=httpx.MockTransport(handler),
    )
    assert notifier.notify("hello") is True
