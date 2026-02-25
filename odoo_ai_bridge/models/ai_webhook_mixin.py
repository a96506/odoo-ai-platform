"""
Mixin that adds webhook dispatch to any Odoo model on create/write/unlink.
Sends structured payloads to the AI Service for processing.
"""

import json
import hashlib
import hmac
import logging
from datetime import datetime

from odoo import models, api

_logger = logging.getLogger(__name__)

try:
    import requests as req_lib
except ImportError:
    req_lib = None


class AiWebhookMixin(models.AbstractModel):
    _name = "ai.webhook.mixin"
    _description = "AI Webhook Dispatch Mixin"

    # Subclasses override these
    _ai_webhook_fields = []  # Fields to include in webhook payload
    _ai_module_toggle = ""   # Config field name e.g. "enable_crm"

    def _get_ai_config(self):
        return self.env["ai.config"].sudo().get_config()

    def _should_send_webhook(self):
        config = self._get_ai_config()
        if not config.enabled:
            return False
        if self._ai_module_toggle and not getattr(config, self._ai_module_toggle, True):
            return False
        return True

    def _build_payload(self, event_type, record, values=None, old_values=None):
        payload_values = {}
        if values:
            payload_values = {
                k: self._serialize_value(v)
                for k, v in values.items()
                if not k.startswith("_")
            }

        if self._ai_webhook_fields and event_type != "unlink":
            for field in self._ai_webhook_fields:
                if field not in payload_values:
                    val = getattr(record, field, None)
                    payload_values[field] = self._serialize_value(val)

        return {
            "event_type": event_type,
            "model": self._name,
            "record_id": record.id if hasattr(record, "id") else 0,
            "values": payload_values,
            "old_values": old_values or {},
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": self.env.uid,
        }

    def _serialize_value(self, value):
        if isinstance(value, models.BaseModel):
            return value.ids if len(value) > 1 else (value.id if value else False)
        if isinstance(value, (datetime,)):
            return value.isoformat()
        if isinstance(value, bytes):
            return None
        return value

    def _send_webhook(self, payload):
        if req_lib is None:
            _logger.warning("requests library not available, skipping webhook")
            return

        config = self._get_ai_config()
        url = f"{config.ai_service_url}/webhooks/odoo"

        headers = {"Content-Type": "application/json"}
        body = json.dumps(payload, default=str)

        if config.webhook_secret:
            sig = hmac.new(
                config.webhook_secret.encode(),
                body.encode(),
                hashlib.sha256,
            ).hexdigest()
            headers["X-Webhook-Signature"] = sig

        try:
            resp = req_lib.post(url, data=body, headers=headers, timeout=5)
            if config.log_webhooks:
                _logger.info(
                    "AI webhook sent: %s %s record=%s status=%s",
                    payload.get("event_type"),
                    payload.get("model"),
                    payload.get("record_id"),
                    resp.status_code,
                )
        except Exception as e:
            _logger.error("AI webhook failed: %s", str(e))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self._should_send_webhook():
            for record, vals in zip(records, vals_list):
                payload = self._build_payload("create", record, values=vals)
                self._send_webhook(payload)
        return records

    def write(self, vals):
        old_values = {}
        if self._should_send_webhook() and self._ai_webhook_fields:
            for field in self._ai_webhook_fields:
                if field in vals:
                    old_values[field] = self._serialize_value(
                        getattr(self, field, None)
                    )

        result = super().write(vals)

        if self._should_send_webhook() and vals:
            for record in self:
                payload = self._build_payload(
                    "write", record, values=vals, old_values=old_values
                )
                self._send_webhook(payload)

        return result

    def unlink(self):
        if self._should_send_webhook():
            for record in self:
                payload = self._build_payload("unlink", record)
                self._send_webhook(payload)
        return super().unlink()
