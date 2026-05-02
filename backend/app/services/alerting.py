from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


class AlertService:
    def send_warning(self, title: str, details: str = "") -> None:
        if details:
            logger.warning("%s | %s", title, details)
        else:
            logger.warning("%s", title)

    def send_info(self, title: str, details: str = "") -> None:
        if details:
            logger.info("%s | %s", title, details)
        else:
            logger.info("%s", title)

    def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        body: str,
        html_body: str | None = None,
    ) -> bool:
        if not settings.smtp_host.strip() or not settings.smtp_from_email.strip():
            logger.warning(
                "Письмо не отправлено: в .env не заданы SMTP_HOST и/или SMTP_FROM_EMAIL "
                "(контейнер api читает backend/.env при docker compose)."
            )
            return False
        try:
            self._send_email(
                to_emails=[to_email],
                subject=subject,
                body=body,
                html_body=html_body,
            )
            return True
        except Exception as e:
            logger.error(
                "SMTP send failed to %s: %s",
                to_email,
                e,
                exc_info=True,
            )
            return False

    def _send_email(
        self,
        *,
        to_emails: list[str],
        subject: str,
        body: str,
        html_body: str | None = None,
    ) -> None:
        if html_body:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))
        else:
            msg = MIMEText(body, "plain", "utf-8")

        msg["Subject"] = subject
        msg["From"] = settings.smtp_from_email.strip()
        msg["To"] = ", ".join(to_emails)

        host = settings.smtp_host.strip()
        port = settings.smtp_port
        smtp_user = settings.smtp_user.strip()
        smtp_password = settings.smtp_password

        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=30) as client:
                if smtp_user:
                    client.login(smtp_user, smtp_password)
                client.sendmail(settings.smtp_from_email.strip(), to_emails, msg.as_string())
            return

        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=30) as client:
                if smtp_user:
                    client.login(smtp_user, smtp_password)
                client.sendmail(settings.smtp_from_email.strip(), to_emails, msg.as_string())
            return

        with smtplib.SMTP(host, port, timeout=30) as client:
            if settings.smtp_use_tls:
                client.starttls()
            if smtp_user:
                client.login(smtp_user, smtp_password)
            client.sendmail(settings.smtp_from_email.strip(), to_emails, msg.as_string())


alert_service = AlertService()