import logging

from app.notifications.ports import EmailSender, TelegramNotifier

logger = logging.getLogger(__name__)


class NotificationFacade:
    def __init__(
        self,
        email_sender: EmailSender,
        telegram_notifier: TelegramNotifier,
        alert_recipients: list[str],
    ) -> None:
        self._email_sender = email_sender
        self._telegram_notifier = telegram_notifier
        self._alert_recipients = alert_recipients

    def send_warning(self, title: str, details: str = "") -> None:
        logger.warning("%s%s", title, f" | {details}" if details else "")

    def send_info(self, title: str, details: str = "") -> None:
        logger.info("%s%s", title, f" | {details}" if details else "")

    def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        inline_images: dict[str, bytes] | None = None,
    ) -> bool:
        return self._email_sender.send(
            to_email=to_email,
            subject=subject,
            body=body,
            html_body=html_body,
            inline_images=inline_images,
        )

    def send_telegram(self, text: str) -> bool:
        return self._telegram_notifier.notify(text)

    def alert_recipients(self) -> list[str]:
        return list(self._alert_recipients)
