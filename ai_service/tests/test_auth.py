"""Unit tests for API key authentication and webhook signature verification."""

import json

import pytest


class TestAPIKeyAuth:
    def test_health_no_auth_required(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_stats_requires_api_key(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 401

    def test_stats_valid_api_key(self, client, auth_headers):
        resp = client.get("/api/stats", headers=auth_headers)
        assert resp.status_code == 200

    def test_stats_invalid_api_key(self, client):
        resp = client.get("/api/stats", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401

    def test_rules_requires_api_key(self, client):
        resp = client.get("/api/rules")
        assert resp.status_code == 401

    def test_rules_valid_api_key(self, client, auth_headers):
        resp = client.get("/api/rules", headers=auth_headers)
        assert resp.status_code == 200

    def test_chat_requires_api_key(self, client):
        resp = client.post("/api/chat", json={"message": "hello"})
        assert resp.status_code == 401

    def test_insights_requires_api_key(self, client):
        resp = client.get("/api/insights")
        assert resp.status_code == 401

    def test_trigger_requires_api_key(self, client):
        resp = client.post(
            "/api/trigger/crm/score_lead",
            params={"model": "crm.lead", "record_id": 1},
        )
        assert resp.status_code == 401


class TestWebhookSignature:
    def test_webhook_missing_signature_rejected(self, client):
        payload = {
            "event_type": "create",
            "model": "crm.lead",
            "record_id": 1,
            "values": {},
        }
        resp = client.post("/webhooks/odoo", json=payload)
        assert resp.status_code == 401
        assert "Missing" in resp.json()["detail"]

    def test_webhook_invalid_signature_rejected(self, client):
        payload = {
            "event_type": "create",
            "model": "crm.lead",
            "record_id": 1,
            "values": {},
        }
        resp = client.post(
            "/webhooks/odoo",
            json=payload,
            headers={"X-Webhook-Signature": "bad-sig"},
        )
        assert resp.status_code == 401

    def test_webhook_valid_signature_accepted(self, client, signed_webhook_headers):
        payload = {
            "event_type": "create",
            "model": "crm.lead",
            "record_id": 1,
            "values": {},
        }
        headers = signed_webhook_headers(payload)
        resp = client.post("/webhooks/odoo", content=json.dumps(payload), headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"
