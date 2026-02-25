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

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def odoo_auth(self) -> str:
        return self.odoo_api_key or self.odoo_password


@lru_cache
def get_settings() -> Settings:
    return Settings()
