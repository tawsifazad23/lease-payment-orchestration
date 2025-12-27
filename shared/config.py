import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://lease_user:lease_pass@localhost:5432/lease_db"
    )

    # Redis
    redis_url: str = os.getenv(
        "REDIS_URL",
        "redis://localhost:6379/0"
    )

    # Celery
    celery_broker_url: str = os.getenv(
        "CELERY_BROKER_URL",
        "redis://localhost:6379/1"
    )
    celery_result_backend: str = os.getenv(
        "CELERY_RESULT_BACKEND",
        "redis://localhost:6379/2"
    )

    # Service
    service_name: str = os.getenv("SERVICE_NAME", "unknown")
    service_port: int = int(os.getenv("SERVICE_PORT", "8000"))
    environment: str = os.getenv("ENVIRONMENT", "development")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # API
    api_v1_prefix: str = os.getenv("API_V1_PREFIX", "/api/v1")

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
