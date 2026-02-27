"""
Unified notification service — routes messages to the right channel.

Usage:
    from app.notifications.service import get_notification_service
    svc = get_notification_service()
    svc.send("email", "user@example.com", "Subject", "Body text")
    svc.send("slack", "#alerts", "Alert", "Something happened")
"""

from typing import Any

import structlog

from app.notifications.base import NotificationChannel
from app.notifications.email import EmailChannel
from app.notifications.slack import SlackChannel

logger = structlog.get_logger()


class NotificationService:
    def __init__(self):
        self._channels: dict[str, NotificationChannel] = {}
        self._register_defaults()

    def _register_defaults(self):
        for cls in (EmailChannel, SlackChannel):
            channel = cls()
            self._channels[channel.channel_name] = channel

    def register(self, channel: NotificationChannel):
        """Register a custom notification channel."""
        self._channels[channel.channel_name] = channel

    def available_channels(self) -> list[str]:
        """Return names of channels that have valid configuration."""
        return [
            name
            for name, ch in self._channels.items()
            if ch.is_configured()
        ]

    def send(
        self,
        channel: str,
        recipient: str,
        subject: str,
        body: str,
        **kwargs: Any,
    ) -> bool:
        """
        Send a notification through the named channel.
        Returns True on success, False if the channel is unavailable or delivery fails.
        """
        ch = self._channels.get(channel)
        if ch is None:
            logger.warning("unknown_notification_channel", channel=channel)
            return False

        if not ch.is_configured():
            logger.info(
                "notification_channel_not_configured",
                channel=channel,
                recipient=recipient,
            )
            return False

        return ch.send(recipient, subject, body, **kwargs)

    def broadcast(
        self,
        recipient_map: dict[str, str],
        subject: str,
        body: str,
        **kwargs: Any,
    ) -> dict[str, bool]:
        """
        Send the same message across multiple channels.
        recipient_map: {"email": "user@x.com", "slack": "#channel"}
        Returns: {"email": True, "slack": True}
        """
        results = {}
        for channel, recipient in recipient_map.items():
            results[channel] = self.send(channel, recipient, subject, body, **kwargs)
        return results


_service: NotificationService | None = None


def get_notification_service() -> NotificationService:
    global _service
    if _service is None:
        _service = NotificationService()
    return _service
