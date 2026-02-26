"""WhatsApp Business API notification channel."""

from typing import Any

import structlog
import httpx

from app.config import get_settings
from app.notifications.base import NotificationChannel

logger = structlog.get_logger()


class WhatsAppChannel(NotificationChannel):
    channel_name = "whatsapp"

    def is_configured(self) -> bool:
        return get_settings().whatsapp_enabled

    def send(
        self,
        recipient: str,
        subject: str,
        body: str,
        **kwargs: Any,
    ) -> bool:
        settings = get_settings()
        if not self.is_configured():
            logger.warning("whatsapp_not_configured")
            return False

        try:
            template = kwargs.get("template")
            if template:
                payload = {
                    "messaging_product": "whatsapp",
                    "to": recipient,
                    "type": "template",
                    "template": template,
                }
            else:
                message = f"*{subject}*\n\n{body}" if subject else body
                payload = {
                    "messaging_product": "whatsapp",
                    "to": recipient,
                    "type": "text",
                    "text": {"body": message},
                }

            url = (
                f"{settings.whatsapp_api_url}/"
                f"{settings.whatsapp_phone_number_id}/messages"
            )

            response = httpx.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.whatsapp_api_token}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            response.raise_for_status()
            logger.info("whatsapp_message_sent", to=recipient)
            return True

        except Exception as exc:
            logger.error("whatsapp_send_failed", to=recipient, error=str(exc))
            return False
