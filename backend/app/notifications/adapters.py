import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

logger = logging.getLogger(__name__)


class SmtpEmailSender:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        from_email: str,
        use_tls: bool,
        use_ssl: bool,
    ) -> None:
        self.host = host.strip()
        self.port = port
        self.username = username.strip()
        self.password = password
        self.from_email = from_email.strip()
        self.use_tls = use_tls
        self.use_ssl = use_ssl

    def send(self, *, to_email: str, subject: str, body: str, html_body: str | None = None) -> bool:
        if not self.host or not self.from_email:
            logger.warning("Письмо не отправлено: SMTP_HOST и/или SMTP_FROM_EMAIL не заданы.")
            return False
        if html_body:
            message = MIMEMultipart("alternative")
            message.attach(MIMEText(body, "plain", "utf-8"))
            message.attach(MIMEText(html_body, "html", "utf-8"))
        else:
            message = MIMEText(body, "plain", "utf-8")
        message["Subject"] = subject
        message["From"] = self.from_email
        message["To"] = to_email
        try:
            smtp_class = smtplib.SMTP_SSL if self.use_ssl or self.port == 465 else smtplib.SMTP
            with smtp_class(self.host, self.port, timeout=30) as client:
                if self.use_tls and smtp_class is smtplib.SMTP:
                    client.starttls()
                if self.username:
                    client.login(self.username, self.password)
                client.sendmail(self.from_email, [to_email], message.as_string())
            return True
        except Exception as exc:
            logger.error("SMTP send failed to %s: %s", to_email, exc, exc_info=True)
            return False


class HttpTelegramNotifier:
    def __init__(
        self,
        *,
        token: str,
        chat_id: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.token = token.strip()
        self.chat_id = chat_id.strip()
        self.transport = transport

    def notify(self, text: str) -> bool:
        if not self.token or not self.chat_id:
            return False
        try:
            with httpx.Client(timeout=15.0, transport=self.transport) as client:
                response = client.post(
                    f"https://api.telegram.org/bot{self.token}/sendMessage",
                    json={"chat_id": self.chat_id, "text": text[:4000]},
                )
            if response.status_code >= 400:
                logger.error("Telegram send failed: HTTP %s %s", response.status_code, response.text[:300])
                return False
            return True
        except Exception as exc:
            logger.error("Telegram send failed: %s", exc, exc_info=True)
            return False
