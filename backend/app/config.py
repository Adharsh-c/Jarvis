from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/
BASE_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    app_name: str = "JARVIS V10"
    secret_key: str = "change-this-secret-in-production"
    access_token_expire_minutes: int = 720
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'jarvis.db'}"
    workspace_path: str = str(BASE_DIR / "workspace")

    # V10 AI backend: local Ollama only.
    ai_provider: str = Field(default="ollama", validation_alias="AI_PROVIDER")
    ai_auto_order: str = Field(default="ollama", validation_alias="AI_AUTO_ORDER")
    ai_request_timeout_seconds: int = Field(default=300, validation_alias="AI_REQUEST_TIMEOUT_SECONDS")
    ollama_num_ctx: int = Field(default=8192, validation_alias="OLLAMA_NUM_CTX")
    command_timeout_seconds: int = Field(default=180, validation_alias="COMMAND_TIMEOUT_SECONDS")
    ollama_enabled: bool = Field(default=True, validation_alias="OLLAMA_ENABLED")
    ollama_model: str = Field(default="qwen2.5-coder:7b", validation_alias="OLLAMA_MODEL")
    ollama_base_url: str = Field(default="http://127.0.0.1:11434", validation_alias="OLLAMA_BASE_URL")

    cors_origins: str = Field(default="http://127.0.0.1:8000,http://localhost:8000", validation_alias="CORS_ORIGINS")
    agent_pairing_token: str = Field(default="", validation_alias="AGENT_PAIRING_TOKEN")
    agent_id: str = Field(default="local-laptop", validation_alias="AGENT_ID")
    voice_api_token: str = Field(default="", validation_alias="VOICE_API_TOKEN")
    voice_user_email: str = Field(default="", validation_alias="VOICE_USER_EMAIL")
    orchestration_max_workers: int = Field(default=6, validation_alias="ORCHESTRATION_MAX_WORKERS")
    desktop_control_enabled: bool = Field(default=True, validation_alias="DESKTOP_CONTROL_ENABLED")
    desktop_action_timeout_seconds: int = Field(default=30, validation_alias="DESKTOP_ACTION_TIMEOUT_SECONDS")
    environment: str = Field(default="development", validation_alias="JARVIS_ENV")
    enable_docs: bool = Field(default=True, validation_alias="ENABLE_DOCS")
    trusted_hosts: str = Field(default="127.0.0.1,localhost", validation_alias="TRUSTED_HOSTS")

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
Path(settings.workspace_path).resolve().mkdir(parents=True, exist_ok=True)
(BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
