from app.notifications.email_templates import (
    build_password_reset_email_html,
    build_registration_verification_email_html,
)


def test_registration_email_contains_brand_and_escapes_username() -> None:
    html = build_registration_verification_email_html(
        username="<script>alert(1)</script>",
        action_url="https://plash-ki.ru/verify#vid=1&sig=abc",
        ttl_minutes=30,
        assets_base_url="https://api.plash-ki.ru/email-assets",
    )
    assert "Plashki" in html
    assert "Подтверждение регистрации" in html
    assert "Добро пожаловать" in html
    assert "Подтвердить" in html
    assert "30 минут" in html
    assert "Спасибо, что присоединился к нам!" in html
    assert "<script>" not in html
    assert "word-break:break-all" not in html
    assert "https://api.plash-ki.ru/email-assets/logo.png" in html
    assert "https://api.plash-ki.ru/email-assets/icon-guard.png" in html
    assert "fonts.googleapis.com/css2?family=Inter" in html
    assert "data:image/" not in html


def test_password_reset_email_contains_warning_and_ttl() -> None:
    html = build_password_reset_email_html(
        username="yund3r",
        action_url="https://plash-ki.ru/reset#rid=1&sig=abc",
        ttl_minutes=10,
        assets_base_url="https://api.plash-ki.ru/email-assets",
    )
    assert "Привет, yund3r!" in html
    assert "Сброс пароля" in html
    assert "Сбросить пароль" in html
    assert "10 минут" in html
    assert "Если ты не запрашивал смену пароля" in html
    assert "Больше не теряй пароль от аккаунта" in html
    assert "display:block;box-sizing:border-box;width:100%" in html
    assert "padding:19px 28px" in html
    assert "Время работоспособности ссылки - 10 минут" in html
    assert "&#8599;" not in html
    assert "https://api.plash-ki.ru/email-assets/logo.png" in html
    assert "https://api.plash-ki.ru/email-assets/icon-guard.png" in html
    assert "https://api.plash-ki.ru/email-assets/icon-warning.png" in html
    assert "fonts.googleapis.com/css2?family=Inter" in html
    assert "data:image/" not in html


def test_logo_uses_cid_without_public_assets_base() -> None:
    html = build_password_reset_email_html(
        username="local",
        action_url="https://example.com/reset",
        ttl_minutes=5,
        assets_base_url="",
    )
    assert "cid:plashki-logo" in html
    assert "cid:plashki-icon-guard" in html
    assert "cid:plashki-icon-warning" in html
