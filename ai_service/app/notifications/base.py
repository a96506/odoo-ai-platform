"""Abstract base for notification channels."""

from abc import ABC, abstractmethod
from typing import Any


class NotificationChannel(ABC):
    """
    Interface that every notification channel implements.
    Channels are registered with the NotificationService and selected by name.
    """

    channel_name: str = ""

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if this channel has the credentials it needs."""
        ...

    @abstractmethod
    def send(
        self,
        recipient: str,
        subject: str,
        body: str,
        **kwargs: Any,
    ) -> bool:
        """
        Send a message.
        Returns True on success, False on failure.
        """
        ...
