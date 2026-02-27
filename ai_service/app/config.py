from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Odoo
    odoo_url: str = "http://odoo-web:8069"
    odoo_db: str = "odoo"
    odoo_username: str = "admin"
    odoo_password: str = "admin"
    odoo_api_key: str = ""

    # Anthropic
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Database
    ai_database_url: str = "postgresql://odoo_ai:changeme-db-password@ai-db:5432/odoo_ai"

    # Service
    ai_service_host: str = "0.0.0.0"
    ai_service_port: int = 8000
    ai_secret_key: str = "change-me"
    webhook_secret: str = "change-me-webhook-secret"

    # Thresholds
    default_confidence_threshold: float = 0.85
    auto_approve_threshold: float = 0.95

    # Logging
    log_level: str = "INFO"

    # CORS — comma-separated allowed origins (empty = dashboard + odoo defaults)
    cors_origins: str = ""

    # --- Phase 1 foundations (all optional, disabled by default) ---

    # Slack
    slack_bot_token: str = ""
    slack_signing_secret: str = ""
    slack_default_channel: str = ""

    # Email / SMTP
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_address: str = ""
    smtp_use_tls: bool = True

    # Forecasting
    forecast_horizon_days: int = 90
    forecast_cache_ttl_seconds: int = 3600

    # Document processing (IDP)
    idp_max_pages: int = 50
    idp_confidence_threshold: float = 0.90

    # --- Phase 2 foundations ---

    # Agentic AI
    agent_max_steps: int = 30
    agent_max_tokens: int = 50000
    agent_suspension_timeout_hours: int = 48
    agent_loop_threshold: int = 3

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def odoo_auth(self) -> str:
        return self.odoo_api_key or self.odoo_password

    @property
    def slack_enabled(self) -> bool:
        return bool(self.slack_bot_token)

    @property
    def smtp_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_user)

    @property
    def allowed_origins(self) -> list[str]:
        if self.cors_origins:
            return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return [
            self.odoo_url,
            "https://odoo-ai-dash-65-21-62-16.traefik.me",
            "https://odoo-ai-api-65-21-62-16.traefik.me",
            "http://localhost:3000",
            "http://localhost:8000",
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
