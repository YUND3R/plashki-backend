from functools import lru_cache

from app.core.config import settings
from app.notifications.adapters import HttpTelegramNotifier, SmtpEmailSender
from app.notifications.application import NotificationFacade


@lru_cache
def get_notification_facade() -> NotificationFacade:
    return NotificationFacade(
        SmtpEmailSender(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            from_email=settings.smtp_from_email,
            use_tls=settings.smtp_use_tls,
            use_ssl=settings.smtp_use_ssl,
        ),
        HttpTelegramNotifier(
            token=settings.telegram_bot_token,
            chat_id=settings.telegram_alert_chat_id,
        ),
        settings.alert_email_list,
    )
