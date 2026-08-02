from __future__ import annotations

import html
from pathlib import Path
from urllib.parse import quote

from app.core.config import settings

_BRAND_BLUE = "#4076FF"
_BRAND_BLUE_LIGHT = "#E8EFFF"
_TEXT_PRIMARY = "#111827"
_TEXT_MUTED = "#6B7280"
_BORDER = "#E5E7EB"
_FONT = "Arial, Helvetica, sans-serif"

_LOGO_SVG = (Path(__file__).resolve().parent / "assets" / "logo.svg").read_text(
    encoding="utf-8"
)


def _svg_data_uri(svg: str) -> str:
    return f"data:image/svg+xml,{quote(svg.strip())}"


_LOGO_DATA_URI = _svg_data_uri(_LOGO_SVG)

_ICON_SHIELD = _svg_data_uri(
    """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20" fill="none">
<path d="M10 1.667L3.333 4.167v5.833c0 3.958 2.875 7.667 6.667 8.333 3.792-.667 6.667-4.375 6.667-8.333V4.167L10 1.667z"
stroke="#4076FF" stroke-width="1.4" stroke-linejoin="round"/>
<path d="M7.5 10l1.667 1.667L12.5 8.333" stroke="#4076FF" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""
)

_ICON_WARNING = _svg_data_uri(
    """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20" fill="none">
<path d="M10 2.5L17.5 16.667H2.5L10 2.5z" stroke="#4076FF" stroke-width="1.4" stroke-linejoin="round"/>
<path d="M10 8.333V11.667" stroke="#4076FF" stroke-width="1.4" stroke-linecap="round"/>
<circle cx="10" cy="14.167" r="0.833" fill="#4076FF"/>
</svg>"""
)

_ICON_COPY = _svg_data_uri(
    """<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 18 18" fill="none">
<rect x="5.5" y="5.5" width="9" height="9" rx="1.5" stroke="#4076FF" stroke-width="1.4"/>
<path d="M4 12.5V3.5A1.5 1.5 0 015.5 2h9" stroke="#4076FF" stroke-width="1.4" stroke-linecap="round"/>
</svg>"""
)


def resolve_email_assets_base_url(*, request_base_url: str = "") -> str:
    pub = settings.public_base_url.strip().rstrip("/")
    if pub:
        return f"{pub}/email-assets"
    base = request_base_url.strip().rstrip("/")
    if base:
        return f"{base}/email-assets"
    return ""


def _logo_src(*, assets_base_url: str) -> str:
    if assets_base_url:
        return f"{assets_base_url.rstrip('/')}/logo.svg"
    return _LOGO_DATA_URI


def _minutes_label(minutes: int) -> str:
    mod10 = minutes % 10
    mod100 = minutes % 100
    if mod10 == 1 and mod100 != 11:
        return f"{minutes} минуту"
    if mod10 in {2, 3, 4} and mod100 not in {12, 13, 14}:
        return f"{minutes} минуты"
    return f"{minutes} минут"


def _info_row(*, icon_src: str, text: str) -> str:
    esc_text = html.escape(text)
    return (
        "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" "
        "style=\"margin:0 0 10px;\">"
        "<tr>"
        "<td width=\"28\" valign=\"top\" style=\"padding:0 8px 0 0;\">"
        f"<img src=\"{icon_src}\" width=\"20\" height=\"20\" alt=\"\" "
        "style=\"display:block;border:0;outline:none;\"/>"
        "</td>"
        f"<td valign=\"top\" style=\"font-size:14px;line-height:1.5;color:{_TEXT_MUTED};\">"
        f"{esc_text}</td>"
        "</tr></table>"
    )


def _build_transactional_email_html(
    *,
    greeting: str,
    title: str,
    intro: str,
    action_text: str,
    action_url: str,
    footer_text: str,
    ttl_minutes: int,
    assets_base_url: str = "",
    warning_text: str | None = None,
) -> str:
    esc_greeting = html.escape(greeting)
    esc_title = html.escape(title)
    esc_intro = html.escape(intro)
    esc_action_text = html.escape(action_text)
    esc_action_url = html.escape(action_url)
    esc_footer = html.escape(footer_text)
    logo_src = html.escape(_logo_src(assets_base_url=assets_base_url), quote=True)

    info_rows = _info_row(
        icon_src=_ICON_SHIELD,
        text=f"Время работоспособности ссылки — {_minutes_label(ttl_minutes)}.",
    )
    if warning_text:
        info_rows += _info_row(icon_src=_ICON_WARNING, text=warning_text)

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
        f"<img src=\"{logo_src}\" width=\"130\" height=\"29\" alt=\"Plashki\" "
        "style=\"display:block;border:0;outline:none;max-width:130px;height:auto;\"/>"
        "</td>"
        f"<td align=\"right\" valign=\"middle\" style=\"font-size:15px;line-height:1.4;color:{_TEXT_PRIMARY};\">"
        f"{esc_greeting}</td>"
        "</tr></table>"
        "</td></tr>"
        f"<tr><td style=\"border-top:1px solid {_BORDER};font-size:0;line-height:0;\">&nbsp;</td></tr>"
        "<tr><td style=\"padding:28px 24px 8px;\">"
        f"<h1 style=\"margin:0 0 16px;font-size:24px;line-height:1.3;font-weight:700;color:{_TEXT_PRIMARY};\">"
        f"{esc_title}</h1>"
        f"<p style=\"margin:0 0 24px;font-size:15px;line-height:1.65;color:{_TEXT_MUTED};\">"
        f"{esc_intro}</p>"
        "<table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\" style=\"margin:0 0 24px;\">"
        "<tr>"
        "<td style=\"padding:0 8px 0 0;\">"
        f"<a href=\"{esc_action_url}\" "
        f"style=\"display:inline-block;background:{_BRAND_BLUE};color:#ffffff;text-decoration:none;"
        "padding:14px 28px;border-radius:10px;font-size:15px;font-weight:600;line-height:1;\">"
        f"{esc_action_text}</a></td>"
        "<td>"
        f"<a href=\"{esc_action_url}\" "
        f"style=\"display:inline-block;background:{_BRAND_BLUE_LIGHT};text-decoration:none;"
        "width:46px;height:46px;border-radius:10px;line-height:46px;text-align:center;\">"
        f"<img src=\"{_ICON_COPY}\" width=\"18\" height=\"18\" alt=\"Скопировать ссылку\" "
        "style=\"display:inline-block;vertical-align:middle;border:0;outline:none;\"/>"
        "</a></td>"
        "</tr></table>"
        f"{info_rows}"
        f"<p style=\"margin:16px 0 0;font-size:13px;line-height:1.5;color:{_TEXT_MUTED};word-break:break-all;\">"
        f"{esc_action_url}</p>"
        "</td></tr>"
        f"<tr><td style=\"border-top:1px solid {_BORDER};font-size:0;line-height:0;\">&nbsp;</td></tr>"
        f"<tr><td align=\"center\" style=\"padding:24px;font-size:15px;line-height:1.5;color:{_TEXT_MUTED};\">"
        f"{esc_footer}</td></tr>"
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
    greeting = f"Добро пожаловать, {username.strip()}! 😎"
    return _build_transactional_email_html(
        greeting=greeting,
        title="Подтверждение регистрации",
        intro=(
            "Мы получили твой запрос на регистрацию в Plashki. "
            "Подтверди аккаунт сейчас, чтобы начать играть!"
        ),
        action_text="Подтвердить",
        action_url=action_url,
        footer_text="Спасибо, что присоединился к нам! 💙",
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
    greeting = f"Привет, {username.strip()}! 😎"
    return _build_transactional_email_html(
        greeting=greeting,
        title="Сброс пароля",
        intro=(
            "Мы получили твой запрос на восстановление пароля от аккаунта в Plashki. "
            "Нажми на кнопку ниже или перейди по ссылке, чтобы сбросить пароль."
        ),
        action_text="Сбросить пароль",
        action_url=action_url,
        footer_text="Больше не теряй пароль от аккаунта 💙",
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
        "Подтверждение регистрации в Plashki.\n\n"
        "Мы получили твой запрос на регистрацию. Подтверди аккаунт по ссылке:\n"
        f"{action_url}\n\n"
        f"Ссылка действует {_minutes_label(ttl_minutes)}.\n\n"
        "Спасибо, что присоединился к нам!"
    )


def build_password_reset_email_plain(
    *,
    username: str,
    action_url: str,
    ttl_minutes: int,
) -> str:
    return (
        f"Привет, {username.strip()}!\n\n"
        "Сброс пароля в Plashki.\n\n"
        "Мы получили твой запрос на восстановление пароля. Перейди по ссылке:\n"
        f"{action_url}\n\n"
        f"Ссылка действует {_minutes_label(ttl_minutes)}.\n\n"
        "Если ты не запрашивал смену пароля, проигнорируй это письмо.\n\n"
        "Больше не теряй пароль от аккаунта."
    )
