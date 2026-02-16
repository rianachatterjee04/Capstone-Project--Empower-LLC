from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl, Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    env: str = Field(default="dev", alias="ENV")
    service_name: str = Field(default="foundry-people-backend", alias="SERVICE_NAME")

    supabase_url: AnyHttpUrl = Field(..., alias="SUPABASE_URL")
    supabase_anon_key: str = Field(..., alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str | None = Field(default=None, alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_storage_bucket: str = Field(default="foundry-people", alias="SUPABASE_STORAGE_BUCKET")
    supabase_jwks_url: AnyHttpUrl | None = Field(default=None, alias="SUPABASE_JWKS_URL")
    supabase_jwt_secret: str | None = Field(default=None, alias="SUPABASE_JWT_SECRET")

    database_url: str = Field(..., alias="DATABASE_URL")
    internal_ai_shared_secret: str = Field(..., alias="INTERNAL_AI_SHARED_SECRET")

    celery_broker_url: str = Field(default="redis://localhost:6379/0", alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(default="redis://localhost:6379/1", alias="CELERY_RESULT_BACKEND")

    temporal_address: str = Field(default="localhost:7233", alias="TEMPORAL_ADDRESS")

    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")
    llm_model: str = Field(default="gpt-4.1-mini", alias="LLM_MODEL")
    embeddings_provider: str = Field(default="openai", alias="EMBEDDINGS_PROVIDER")
    embeddings_model: str = Field(default="text-embedding-3-small", alias="EMBEDDINGS_MODEL")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")

    integrations_enc_key: str | None = Field(default=None, alias="INTEGRATIONS_ENC_KEY")
    expo_push_access_token: str | None = Field(default=None, alias="EXPO_PUSH_ACCESS_TOKEN")

    lever_client_id: str | None = Field(default=None, alias="LEVER_CLIENT_ID")
    lever_client_secret: str | None = Field(default=None, alias="LEVER_CLIENT_SECRET")
    lever_redirect_uri: str | None = Field(default=None, alias="LEVER_REDIRECT_URI")
    lever_webhook_secret: str | None = Field(default=None, alias="LEVER_WEBHOOK_SECRET")
    greenhouse_webhook_secret: str | None = Field(default=None, alias="GREENHOUSE_WEBHOOK_SECRET")
    greenhouse_api_key: str | None = Field(default=None, alias="GREENHOUSE_API_KEY")


settings = Settings()
