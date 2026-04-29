from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_host: str = os.getenv("APP_HOST", "127.0.0.1")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    default_mode: str = os.getenv("DEFAULT_MODE", "hybrid")
    local_llm_provider: str = os.getenv("LOCAL_LLM_PROVIDER", "ollama")
    local_llm_model: str = os.getenv("LOCAL_LLM_MODEL", "mistral:7b-instruct")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    cloud_provider: str = os.getenv("CLOUD_PROVIDER", "openai")
    cloud_model: str = os.getenv("CLOUD_MODEL", "gpt-4.1-mini")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
    enable_presidio: bool = _as_bool(os.getenv("ENABLE_PRESIDIO"), False)
    enable_web_search: bool = _as_bool(os.getenv("ENABLE_WEB_SEARCH"), False)
    session_ttl_minutes: int = int(os.getenv("SESSION_TTL_MINUTES", "60"))
    max_outbound_prompt_chars: int = int(os.getenv("MAX_OUTBOUND_PROMPT_CHARS", "16000"))
    block_cloud_on_residual_risk: bool = _as_bool(os.getenv("BLOCK_CLOUD_ON_RESIDUAL_RISK"), True)
    max_directory_files: int = int(os.getenv("MAX_DIRECTORY_FILES", "25"))
    api_auth_enabled: bool = _as_bool(os.getenv("API_AUTH_ENABLED"), False)
    api_auth_token: str = os.getenv("API_AUTH_TOKEN", "")
    api_user_token: str = os.getenv("API_USER_TOKEN", "")
    api_admin_token: str = os.getenv("API_ADMIN_TOKEN", "")
    audit_snapshots_enabled: bool = _as_bool(os.getenv("AUDIT_SNAPSHOTS_ENABLED"), False)
    audit_snapshots_dir: str = os.getenv("AUDIT_SNAPSHOTS_DIR", ".audit")
    audit_encryption_key: str = os.getenv("AUDIT_ENCRYPTION_KEY", "")
    privacy_logging_enabled: bool = _as_bool(os.getenv("PRIVACY_LOGGING_ENABLED"), True)
    privacy_log_level: str = os.getenv("PRIVACY_LOG_LEVEL", "INFO")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
