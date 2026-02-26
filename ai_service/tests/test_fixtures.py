"""Verify that all webhook payload fixtures produce valid WebhookPayload instances."""

import pytest

from app.models.schemas import WebhookPayload
from tests.fixtures.webhook_payloads import ALL_FIXTURES


@pytest.mark.parametrize("key", list(ALL_FIXTURES.keys()))
def test_fixture_produces_valid_payload(key):
    data = ALL_FIXTURES[key]()
    payload = WebhookPayload(**data)
    assert payload.event_type in ("create", "write", "unlink")
    assert payload.record_id > 0
    assert "." in payload.model
