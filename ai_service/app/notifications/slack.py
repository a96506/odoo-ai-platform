"""
Slack notification channel with Block Kit rich messaging and interactive buttons.

Supports:
- Plain text messages
- Block Kit rich messages (sections, fields, dividers, context)
- Interactive messages with approve/reject buttons
- Thread replies
- Message templates for common automation events
"""

from typing import Any

import structlog

from app.config import get_settings
from app.notifications.base import NotificationChannel

logger = structlog.get_logger()


class SlackChannel(NotificationChannel):
    channel_name = "slack"

    def is_configured(self) -> bool:
        return get_settings().slack_enabled

    def _get_client(self):
        from slack_sdk import WebClient

        return WebClient(token=get_settings().slack_bot_token)

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
            client = self._get_client()
            channel = recipient or settings.slack_default_channel

            blocks = kwargs.get("blocks")
            thread_ts = kwargs.get("thread_ts")

            if blocks:
                response = client.chat_postMessage(
                    channel=channel,
                    text=subject or body,
                    blocks=blocks,
                    thread_ts=thread_ts,
                )
            else:
                text = f"*{subject}*\n{body}" if subject else body
                response = client.chat_postMessage(
                    channel=channel,
                    text=text,
                    thread_ts=thread_ts,
                )

            logger.info(
                "slack_message_sent",
                channel=channel,
                ts=response.get("ts"),
            )
            return True

        except Exception as exc:
            logger.error("slack_send_failed", channel=recipient, error=str(exc))
            return False

    def send_approval_request(
        self,
        channel: str,
        audit_log_id: int,
        automation_type: str,
        action_name: str,
        model: str,
        record_id: int,
        confidence: float,
        reasoning: str,
    ) -> bool:
        """Send an interactive approval request with Approve/Reject buttons."""
        blocks = build_approval_blocks(
            audit_log_id=audit_log_id,
            automation_type=automation_type,
            action_name=action_name,
            model=model,
            record_id=record_id,
            confidence=confidence,
            reasoning=reasoning,
        )
        return self.send(
            recipient=channel,
            subject=f"Approval needed: {action_name} on {model} #{record_id}",
            body=reasoning,
            blocks=blocks,
        )

    def send_alert(
        self,
        channel: str,
        title: str,
        message: str,
        severity: str = "medium",
        source: str = "",
    ) -> bool:
        """Send a color-coded alert notification."""
        blocks = build_alert_blocks(
            title=title,
            message=message,
            severity=severity,
            source=source,
        )
        return self.send(
            recipient=channel,
            subject=f"[{severity.upper()}] {title}",
            body=message,
            blocks=blocks,
        )

    def send_automation_result(
        self,
        channel: str,
        automation_type: str,
        action_name: str,
        model: str,
        record_id: int,
        success: bool,
        reasoning: str,
    ) -> bool:
        """Send an automation result summary."""
        blocks = build_result_blocks(
            automation_type=automation_type,
            action_name=action_name,
            model=model,
            record_id=record_id,
            success=success,
            reasoning=reasoning,
        )
        status = "completed" if success else "failed"
        return self.send(
            recipient=channel,
            subject=f"Automation {status}: {action_name}",
            body=reasoning,
            blocks=blocks,
        )

    def send_digest(
        self,
        channel: str,
        role: str,
        content: dict[str, Any],
    ) -> bool:
        """Send a formatted daily digest as a rich Block Kit message."""
        blocks = build_digest_blocks(role=role, content=content)
        headline = content.get("headline", "Daily Digest")
        return self.send(
            recipient=channel,
            subject=f"Daily Digest — {headline}",
            body=content.get("summary", ""),
            blocks=blocks,
        )


# ---------------------------------------------------------------------------
# Block Kit message builders
# ---------------------------------------------------------------------------

SEVERITY_EMOJI = {
    "critical": "\U0001f534",  # red circle
    "high": "\U0001f7e0",      # orange circle
    "medium": "\U0001f7e1",    # yellow circle
    "low": "\U0001f7e2",       # green circle
}


def build_approval_blocks(
    *,
    audit_log_id: int,
    automation_type: str,
    action_name: str,
    model: str,
    record_id: int,
    confidence: float,
    reasoning: str,
) -> list[dict]:
    confidence_pct = f"{confidence * 100:.0f}%"
    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Approval Required", "emoji": True},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{action_name}* on `{model}` record *#{record_id}*",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Type:*\n{automation_type}"},
                {"type": "mrkdwn", "text": f"*Confidence:*\n{confidence_pct}"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*AI Reasoning:*\n>{reasoning[:500]}",
            },
        },
        {"type": "divider"},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Approve", "emoji": True},
                    "style": "primary",
                    "action_id": "approve_action",
                    "value": str(audit_log_id),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Reject", "emoji": True},
                    "style": "danger",
                    "action_id": "reject_action",
                    "value": str(audit_log_id),
                },
            ],
        },
    ]


def build_alert_blocks(
    *,
    title: str,
    message: str,
    severity: str = "medium",
    source: str = "",
) -> list[dict]:
    emoji = SEVERITY_EMOJI.get(severity, SEVERITY_EMOJI["medium"])
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{emoji} {title}", "emoji": True},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": message},
        },
    ]
    if source:
        blocks.append({
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"Source: *{source}* | Severity: *{severity.upper()}*"},
            ],
        })
    return blocks


def build_result_blocks(
    *,
    automation_type: str,
    action_name: str,
    model: str,
    record_id: int,
    success: bool,
    reasoning: str,
) -> list[dict]:
    icon = "\u2705" if success else "\u274c"  # check mark / cross mark
    status_text = "Completed" if success else "Failed"
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{icon} *Automation {status_text}*\n`{action_name}` on `{model}` #{record_id}",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Type:*\n{automation_type}"},
                {"type": "mrkdwn", "text": f"*Status:*\n{status_text}"},
            ],
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": reasoning[:300]},
            ],
        },
    ]


def build_digest_blocks(
    *,
    role: str,
    content: dict[str, Any],
) -> list[dict]:
    """Build a Block Kit message for a daily digest."""
    headline = content.get("headline", "Daily Digest")
    summary = content.get("summary", "")

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": headline, "emoji": True},
        },
    ]

    if summary:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": summary},
        })

    metrics = content.get("key_metrics", [])
    if metrics:
        blocks.append({"type": "divider"})
        fields = []
        for m in metrics[:10]:
            change_str = f" ({m.get('change_label', '')})" if m.get("change_label") else ""
            fields.append({
                "type": "mrkdwn",
                "text": f"*{m['name']}*\n{m['value']}{change_str}",
            })
        for i in range(0, len(fields), 10):
            blocks.append({"type": "section", "fields": fields[i : i + 10]})

    attention_items = content.get("attention_items", [])
    if attention_items:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Needs Your Attention*"},
        })
        for item in attention_items[:8]:
            priority = item.get("priority", "medium")
            emoji = SEVERITY_EMOJI.get(priority, SEVERITY_EMOJI["medium"])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{emoji} *{item['title']}*\n{item.get('description', '')}",
                },
            })

    anomalies = content.get("anomalies", [])
    if anomalies:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Anomalies Detected*"},
        })
        for a in anomalies[:5]:
            sev = a.get("severity", "medium")
            emoji = SEVERITY_EMOJI.get(sev, SEVERITY_EMOJI["medium"])
            blocks.append({
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"{emoji} {a['description']}"},
                ],
            })

    blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": f"_Smart Odoo AI Platform — {role} digest_"},
        ],
    })

    return blocks
