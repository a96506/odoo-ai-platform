"""
HTTP endpoints the AI Service calls back to perform actions on Odoo.
Authenticated via API key in the Authorization header.
"""

import json
import logging

from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class AiCallbackController(http.Controller):

    def _check_auth(self):
        auth_header = request.httprequest.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return False
        token = auth_header[7:]
        config = request.env["ai.config"].sudo().get_config()
        return token == config.webhook_secret

    @http.route("/ai/callback/read", type="json", auth="none", methods=["POST"], csrf=False)
    def read_record(self, **kwargs):
        if not self._check_auth():
            return {"error": "Unauthorized"}

        data = json.loads(request.httprequest.data)
        model = data.get("model")
        record_id = data.get("record_id")
        fields = data.get("fields", [])

        try:
            record = request.env[model].sudo().browse(record_id)
            if not record.exists():
                return {"error": "Record not found"}
            result = record.read(fields)[0] if fields else record.read()[0]
            return {"success": True, "data": self._serialize(result)}
        except Exception as e:
            _logger.error("AI callback read failed: %s", str(e))
            return {"error": str(e)}

    @http.route("/ai/callback/search", type="json", auth="none", methods=["POST"], csrf=False)
    def search_records(self, **kwargs):
        if not self._check_auth():
            return {"error": "Unauthorized"}

        data = json.loads(request.httprequest.data)
        model = data.get("model")
        domain = data.get("domain", [])
        fields = data.get("fields", [])
        limit = data.get("limit", 50)
        order = data.get("order", "")

        try:
            records = request.env[model].sudo().search_read(
                domain, fields=fields, limit=limit, order=order
            )
            return {"success": True, "data": [self._serialize(r) for r in records]}
        except Exception as e:
            _logger.error("AI callback search failed: %s", str(e))
            return {"error": str(e)}

    @http.route("/ai/callback/write", type="json", auth="none", methods=["POST"], csrf=False)
    def write_record(self, **kwargs):
        if not self._check_auth():
            return {"error": "Unauthorized"}

        data = json.loads(request.httprequest.data)
        model = data.get("model")
        record_id = data.get("record_id")
        values = data.get("values", {})

        try:
            record = request.env[model].sudo().browse(record_id)
            if not record.exists():
                return {"error": "Record not found"}
            record.write(values)
            _logger.info("AI callback: updated %s(%s)", model, record_id)
            return {"success": True}
        except Exception as e:
            _logger.error("AI callback write failed: %s", str(e))
            return {"error": str(e)}

    @http.route("/ai/callback/create", type="json", auth="none", methods=["POST"], csrf=False)
    def create_record(self, **kwargs):
        if not self._check_auth():
            return {"error": "Unauthorized"}

        data = json.loads(request.httprequest.data)
        model = data.get("model")
        values = data.get("values", {})

        try:
            record = request.env[model].sudo().create(values)
            _logger.info("AI callback: created %s(%s)", model, record.id)
            return {"success": True, "record_id": record.id}
        except Exception as e:
            _logger.error("AI callback create failed: %s", str(e))
            return {"error": str(e)}

    @http.route("/ai/callback/action", type="json", auth="none", methods=["POST"], csrf=False)
    def execute_action(self, **kwargs):
        """Execute an arbitrary method on a record (e.g. action_confirm on sale.order)."""
        if not self._check_auth():
            return {"error": "Unauthorized"}

        data = json.loads(request.httprequest.data)
        model = data.get("model")
        record_id = data.get("record_id")
        method = data.get("method")
        args = data.get("args", [])

        try:
            record = request.env[model].sudo().browse(record_id)
            if not record.exists():
                return {"error": "Record not found"}
            result = getattr(record, method)(*args)
            _logger.info("AI callback: %s.%s(%s)", model, method, record_id)
            return {"success": True, "result": self._serialize(result)}
        except Exception as e:
            _logger.error("AI callback action failed: %s", str(e))
            return {"error": str(e)}

    def _serialize(self, value):
        if isinstance(value, (list, tuple)):
            return [self._serialize(v) for v in value]
        if isinstance(value, dict):
            return {k: self._serialize(v) for k, v in value.items()}
        try:
            json.dumps(value)
            return value
        except (TypeError, ValueError):
            return str(value)
