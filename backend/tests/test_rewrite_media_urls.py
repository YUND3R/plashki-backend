from app.db.rewrite_media_urls import rewrite_stored_media_urls


def test_rewrite_stored_media_urls_skips_without_public_base_url(monkeypatch) -> None:
    monkeypatch.setattr("app.db.rewrite_media_urls.settings.public_base_url", "")
    assert rewrite_stored_media_urls() == {}


def test_rewrite_stored_media_urls_required_raises_without_public_base_url(monkeypatch) -> None:
    monkeypatch.setattr("app.db.rewrite_media_urls.settings.public_base_url", "")
    try:
        rewrite_stored_media_urls(required=True)
        raised = False
    except RuntimeError:
        raised = True
    assert raised
