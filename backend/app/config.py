from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["dev", "prod"] = "dev"
    log_level: str = "INFO"

    postgres_user: str = "sonar"
    postgres_password: str = "change_me"
    postgres_db: str = "sonar_echo"
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    database_url: str = Field(
        default="postgresql+asyncpg://sonar:change_me@postgres:5432/sonar_echo"
    )

    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "change_me_too"
    neo4j_database: str = "neo4j"

    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "chunks"

    redis_url: str = "redis://redis:6379/0"

    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "sonar"
    minio_secret_key: str = "change_me_minio"
    minio_bucket: str = "sonar-docs"
    minio_secure: bool = False

    jwt_secret_key: str = "replace_with_long_random_string"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    openai_api_key: str | None = None
    openai_model_extraction: str = "gpt-4o"
    openai_model_routing: str = "gpt-4o-mini"
    openai_model_generation: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dim: int = 1536

    mistral_api_key: str | None = None
    mistral_ocr_model: str = "mistral-ocr-latest"

    smtp_host: str = "mailhog"
    smtp_port: int = 1025
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "sonar-echo@localhost"
    smtp_tls: bool = False

    rate_limit_per_minute: int = 60
    ingestion_rate_limit_per_minute: int = 10
    public_base_url: str = "http://localhost:8000"
    frontend_origin: str = "http://localhost:3000"

    @property
    def database_url_sync(self) -> str:
        return self.database_url.replace("+asyncpg", "")

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
