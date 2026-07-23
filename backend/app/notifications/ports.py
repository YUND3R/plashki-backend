from typing import Protocol


class EmailSender(Protocol):
    def send(
        self,
        *,
        to_email: str,
        subject: str,
        body: str,
        html_body: str | None = None,
    ) -> bool: ...


class TelegramNotifier(Protocol):
    def notify(self, text: str) -> bool: ...
