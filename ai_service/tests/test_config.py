"""Unit tests for Settings / config."""

import os
from unittest.mock import patch

from app.config import get_settings, Settings


class TestSettings:
    def test_default_thresholds(self, settings):
        assert settings.default_confidence_threshold == 0.85
        assert settings.auto_approve_threshold == 0.95

    def test_odoo_auth_prefers_api_key(self):
        s = Settings(odoo_api_key="my-key", odoo_password="fallback")
        assert s.odoo_auth == "my-key"

    def test_odoo_auth_falls_back_to_password(self):
        s = Settings(odoo_api_key="", odoo_password="pw")
        assert s.odoo_auth == "pw"

    def test_slack_disabled_by_default(self, settings):
        assert settings.slack_enabled is False

    def test_slack_enabled(self):
        s = Settings(slack_bot_token="xoxb-test")
        assert s.slack_enabled is True

    def test_smtp_disabled_by_default(self, settings):
        assert settings.smtp_enabled is False

    def test_smtp_enabled(self):
        s = Settings(smtp_host="smtp.example.com", smtp_user="user")
        assert s.smtp_enabled is True

    def test_allowed_origins_defaults(self, settings):
        origins = settings.allowed_origins
        assert "http://localhost:3000" in origins
        assert "http://localhost:8000" in origins

    def test_allowed_origins_custom(self):
        s = Settings(cors_origins="https://app.example.com, https://admin.example.com")
        origins = s.allowed_origins
        assert origins == ["https://app.example.com", "https://admin.example.com"]

    def test_forecast_defaults(self, settings):
        assert settings.forecast_horizon_days == 90
        assert settings.forecast_cache_ttl_seconds == 3600

    def test_idp_defaults(self, settings):
        assert settings.idp_max_pages == 50
        assert settings.idp_confidence_threshold == 0.90
