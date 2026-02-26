"""Slack notification channel."""

from typing import Any

import structlog

from app.config import get_settings
from app.notifications.base import NotificationChannel

logger = structlog.get_logger()


class SlackChannel(NotificationChannel):
    channel_name = "slack"

    def is_configured(self) -> bool:
        return get_settings().slack_enabled

    def send(
        self,
        recipient: str,
        subject: str,
        body: str,
        **kwargs: Any,
    ) -> bool:
        settings = get_settings()
        if not self.is_configured():
            logger.warning("slack_not_configured")
            return False

        try:
            from slack_sdk import WebClient

            client = WebClient(token=settings.slack_bot_token)
            channel = recipient or settings.slack_default_channel

            text = f"*{subject}*\n{body}" if subject else body

            client.chat_postMessage(channel=channel, text=text)
            logger.info("slack_message_sent", channel=channel)
            return True

        except Exception as exc:
            logger.error("slack_send_failed", channel=recipient, error=str(exc))
            return False
