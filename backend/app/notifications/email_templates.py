from __future__ import annotations

import html
from pathlib import Path

from app.core.config import settings

_BRAND_BLUE = "#4076FF"
_BRAND_BLUE_LIGHT = "#E8EFFF"
_TEXT_PRIMARY = "#111827"
_TEXT_MUTED = "#6B7280"
_BORDER = "#E5E7EB"
_FONT = "Arial, Helvetica, sans-serif"
_LOGO_CID = "plashki-logo"

_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
_LOGO_PNG_BYTES = (_ASSETS_DIR / "logo.png").read_bytes()


def resolve_email_assets_base_url(*, request_base_url: str = "") -> str:
    pub = settings.public_base_url.strip().rstrip("/")
    if pub:
        return f"{pub}/email-assets"
    base = request_base_url.strip().rstrip("/")
    if base:
        return f"{base}/email-assets"
    return ""


def email_inline_images(*, assets_base_url: str = "") -> dict[str, bytes]:
    _, attachments = _logo_attachment(assets_base_url=assets_base_url)
    return attachments


def _logo_attachment(*, assets_base_url: str) -> tuple[str, dict[str, bytes]]:
    if assets_base_url:
        return f"{assets_base_url.rstrip('/')}/logo.png", {}
    return f"cid:{_LOGO_CID}", {_LOGO_CID: _LOGO_PNG_BYTES}


def _minutes_label(minutes: int) -> str:
    mod10 = minutes % 10
    mod100 = minutes % 100
    if mod10 == 1 and mod100 != 11:
        return f"{minutes} минуту"
    if mod10 in {2, 3, 4} and mod100 not in {12, 13, 14}:
        return f"{minutes} минуты"
    return f"{minutes} минут"


def _emoji_badge(emoji: str) -> str:
    return (
        f"<span style=\"display:inline-block;background:{_BRAND_BLUE_LIGHT};"
        "width:30px;height:30px;line-height:30px;text-align:center;"
        "border-radius:4px;font-size:17px;vertical-align:middle;\">"
        f"{emoji}</span>"
    )


def _info_row(*, text: str) -> str:
    esc_text = html.escape(text)
    return (
        "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" "
        "style=\"margin:0 0 10px;\">"
        "<tr>"
        f"<td valign=\"top\" style=\"border-left:3px solid {_BRAND_BLUE};padding:0 0 0 12px;"
        f"font-size:14px;line-height:1.5;color:{_TEXT_MUTED};\">"
        f"{esc_text}</td>"
        "</tr></table>"
    )


def _build_transactional_email_html(
    *,
    greeting_text: str,
    greeting_emoji: str,
    title: str,
    intro: str,
    action_text: str,
    action_url: str,
    footer_text: str,
    footer_emoji: str,
    ttl_minutes: int,
    assets_base_url: str = "",
    warning_text: str | None = None,
) -> str:
    esc_greeting_text = html.escape(greeting_text)
    esc_title = html.escape(title)
    esc_intro = html.escape(intro)
    esc_action_text = html.escape(action_text)
    esc_action_url = html.escape(action_url)
    esc_footer = html.escape(footer_text)
    logo_src, _ = _logo_attachment(assets_base_url=assets_base_url)
    esc_logo_src = html.escape(logo_src, quote=True)

    info_rows = _info_row(
        text=f"Время работоспособности ссылки - {_minutes_label(ttl_minutes)}.",
    )
    if warning_text:
        info_rows += _info_row(text=warning_text)

    return (
        "<!DOCTYPE html>"
        "<html lang=\"ru\">"
        "<head>"
        "<meta charset=\"utf-8\"/>"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>"
        f"<title>{esc_title}</title>"
        "</head>"
        f"<body style=\"margin:0;padding:0;background:#ffffff;font-family:{_FONT};color:{_TEXT_PRIMARY};\">"
        "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\">"
        "<tr><td align=\"center\" style=\"padding:24px 16px;\">"
        "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" "
        "style=\"max-width:600px;\">"
        "<tr><td style=\"padding:8px 24px 20px;\">"
        "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\">"
        "<tr>"
        "<td align=\"left\" valign=\"middle\">"
        f"<img src=\"{esc_logo_src}\" width=\"130\" alt=\"Plashki\" "
        "style=\"display:block;border:0;outline:none;max-width:130px;width:130px;height:auto;\"/>"
        "</td>"
        f"<td align=\"right\" valign=\"middle\" style=\"font-size:15px;line-height:1.4;color:{_TEXT_PRIMARY};\">"
        f"{esc_greeting_text} {_emoji_badge(greeting_emoji)}</td>"
        "</tr></table>"
        "</td></tr>"
        f"<tr><td style=\"border-top:1px solid {_BORDER};font-size:0;line-height:0;\">&nbsp;</td></tr>"
        "<tr><td style=\"padding:28px 24px 8px;\">"
        f"<h1 style=\"margin:0 0 16px;font-size:24px;line-height:1.3;font-weight:700;color:{_TEXT_PRIMARY};\">"
        f"{esc_title}</h1>"
        f"<p style=\"margin:0 0 24px;font-size:15px;line-height:1.65;color:{_TEXT_MUTED};\">"
        f"{esc_intro}</p>"
        "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" "
        "style=\"margin:0 0 24px;\">"
        "<tr>"
        "<td>"
        f"<a href=\"{esc_action_url}\" "
        f"style=\"display:block;box-sizing:border-box;width:100%;background:{_BRAND_BLUE};"
        "color:#ffffff;text-decoration:none;padding:19px 28px;border-radius:10px;"
        "font-size:15px;font-weight:600;line-height:1;text-align:center;\">"
        f"{esc_action_text}</a></td>"
        "</tr></table>"
        f"{info_rows}"
        "</td></tr>"
        f"<tr><td style=\"border-top:1px solid {_BORDER};font-size:0;line-height:0;\">&nbsp;</td></tr>"
        f"<tr><td align=\"center\" style=\"padding:24px;font-size:15px;line-height:1.5;color:{_TEXT_MUTED};\">"
        f"{esc_footer} {_emoji_badge(footer_emoji)}</td></tr>"
        "</table>"
        "</td></tr></table>"
        "</body></html>"
    )


def build_registration_verification_email_html(
    *,
    username: str,
    action_url: str,
    ttl_minutes: int,
    assets_base_url: str = "",
) -> str:
    greeting = f"Добро пожаловать, {username.strip()}!"
    return _build_transactional_email_html(
        greeting_text=greeting,
        greeting_emoji="😎",
        title="Подтверждение регистрации",
        intro=(
            "Мы получили твой запрос на регистрацию в Plashki. "
            "Подтверди аккаунт сейчас, чтобы начать играть!"
        ),
        action_text="Подтвердить",
        action_url=action_url,
        footer_text="Спасибо, что присоединился к нам!",
        footer_emoji="💙",
        ttl_minutes=ttl_minutes,
        assets_base_url=assets_base_url,
    )


def build_password_reset_email_html(
    *,
    username: str,
    action_url: str,
    ttl_minutes: int,
    assets_base_url: str = "",
) -> str:
    greeting = f"Привет, {username.strip()}!"
    return _build_transactional_email_html(
        greeting_text=greeting,
        greeting_emoji="😎",
        title="Сброс пароля",
        intro=(
            "Мы получили твой запрос на восстановление пароля от аккаунта в Plashki. "
            "Нажми на кнопку ниже, чтобы сбросить пароль."
        ),
        action_text="Сбросить пароль",
        action_url=action_url,
        footer_text="Больше не теряй пароль от аккаунта",
        footer_emoji="💙",
        ttl_minutes=ttl_minutes,
        assets_base_url=assets_base_url,
        warning_text=(
            "Если ты не запрашивал смену пароля, проигнорируй и удали это сообщение из почты."
        ),
    )


def build_registration_verification_email_plain(
    *,
    username: str,
    action_url: str,
    ttl_minutes: int,
) -> str:
    return (
        f"Добро пожаловать, {username.strip()}!\n\n"
        "Подтверждение регистрации в Plashki\n"
        "================================\n\n"
        "Мы получили твой запрос на регистрацию. Подтверди аккаунт по ссылке:\n"
        f"{action_url}\n\n"
        f"Ссылка действует {_minutes_label(ttl_minutes)}.\n\n"
        "Спасибо, что присоединился к нам!\n"
        "— Plashki"
    )


def build_password_reset_email_plain(
    *,
    username: str,
    action_url: str,
    ttl_minutes: int,
) -> str:
    return (
        f"Привет, {username.strip()}!\n\n"
        "Сброс пароля в Plashki\n"
        "=====================\n\n"
        "Мы получили твой запрос на восстановление пароля от аккаунта в Plashki.\n"
        "Нажми на ссылку ниже, чтобы сбросить пароль:\n"
        f"{action_url}\n\n"
        f"Ссылка действует {_minutes_label(ttl_minutes)}.\n\n"
        "Если ты не запрашивал смену пароля, проигнорируй это письмо.\n\n"
        "Больше не теряй пароль от аккаунта.\n"
        "— Plashki"
    )
