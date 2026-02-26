"""Email notification channel via SMTP."""

from typing import Any

import structlog

from app.config import get_settings
from app.notifications.base import NotificationChannel

logger = structlog.get_logger()


class EmailChannel(NotificationChannel):
    channel_name = "email"

    def is_configured(self) -> bool:
        return get_settings().smtp_enabled

    def send(
        self,
        recipient: str,
        subject: str,
        body: str,
        **kwargs: Any,
    ) -> bool:
        settings = get_settings()
        if not self.is_configured():
            logger.warning("email_not_configured")
            return False

        try:
            import asyncio
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            import aiosmtplib

            msg = MIMEMultipart("alternative")
            msg["From"] = settings.smtp_from_address or settings.smtp_user
            msg["To"] = recipient
            msg["Subject"] = subject

            html_part = kwargs.get("html")
            if html_part:
                msg.attach(MIMEText(body, "plain"))
                msg.attach(MIMEText(html_part, "html"))
            else:
                msg.attach(MIMEText(body, "plain"))

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    aiosmtplib.send(
                        msg,
                        hostname=settings.smtp_host,
                        port=settings.smtp_port,
                        username=settings.smtp_user,
                        password=settings.smtp_password,
                        use_tls=settings.smtp_use_tls,
                    )
                )
            finally:
                loop.close()

            logger.info("email_sent", to=recipient, subject=subject)
            return True

        except Exception as exc:
            logger.error("email_send_failed", to=recipient, error=str(exc))
            return False
