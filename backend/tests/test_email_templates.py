from app.notifications.email_templates import (
    build_password_reset_email_html,
    build_registration_verification_email_html,
)


def test_registration_email_contains_brand_and_escapes_username() -> None:
    html = build_registration_verification_email_html(
        username="<script>alert(1)</script>",
        action_url="https://plash-ki.ru/verify#vid=1&sig=abc",
        ttl_minutes=30,
    )
    assert "Plashki" in html
    assert "Подтверждение регистрации" in html
    assert "Добро пожаловать" in html
    assert "Подтвердить" in html
    assert "30 минут" in html
    assert "Спасибо, что присоединился к нам!" in html
    assert "<script>" not in html
    assert "word-break:break-all" not in html


def test_password_reset_email_contains_warning_and_ttl() -> None:
    html = build_password_reset_email_html(
        username="yund3r",
        action_url="https://plash-ki.ru/reset#rid=1&sig=abc",
        ttl_minutes=10,
    )
    assert "Привет, yund3r!" in html
    assert "Сброс пароля" in html
    assert "Сбросить пароль" in html
    assert "10 минут" in html
    assert "Если ты не запрашивал смену пароля" in html
    assert "Больше не теряй пароль от аккаунта" in html
    assert "display:block;box-sizing:border-box;width:100%" in html
    assert "data:image/png;base64," in html
