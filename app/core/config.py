from pydantic import model_validator
from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    environment: str = "development"
    debug: bool = True

    database_url: str = "sqlite+aiosqlite:///./agrilend_dev.db"
    database_sync_url: str = "sqlite:///./agrilend_dev.db"

    jwt_secret_key: str = "change-me-to-a-long-random-string"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    cors_origins: str = '["http://localhost:5173","http://localhost:3000"]'

    eyosiyas_service_url: str = "http://geospatial-service:8001"
    amanuel_service_url: str = "https://agri-lend-agricultural-credit-calculator.onrender.com"

    rate_limit_per_minute: int = 30
    rate_limit_auth_per_minute: int = 10
    credit_score_expiry_hours: int = 24

    log_level: str = "INFO"
    audit_log_enabled: bool = True

    @model_validator(mode="after")
    def _normalize_database_url(self):
        """Render/heroku style URLs (postgres:// or postgresql://) must be rewritten for asyncpg."""
        url = self.database_url
        if url.startswith("postgres://"):
            self.database_url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            self.database_url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self

    @property
    def cors_origin_list(self) -> List[str]:
        return json.loads(self.cors_origins)

    @property
    def is_postgres(self) -> bool:
        return "postgresql" in self.database_url

    model_config = {"env_file": ".env", "case_sensitive": False}


settings = Settings()
