import secrets
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerSettings(BaseSettings):
    ATENA_ENV: Literal["development", "production", "testing"] = "development"
    ATENA_HOST: str = "0.0.0.0"
    ATENA_CORS_ORIGINS: str = ""
    ATENA_PORT: int = 8443
    ATENA_WEB_PORT: int = 80
    ATENA_SECRET_KEY: str = (
        "0000000000000000000000000000000000000000000000000000000000000000"
    )
    DATA_DIR: str = "./data"
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    LLM_PROVIDER: str = "ollama"
    SYSTEM1_MODEL: str = "qwen2.5:0.5b"
    BABBLING_MODEL: str = "llama3.2"
    SYSTEM2_MODEL: str = "qwen2.5:7b"
    SEMANTIC_CACHE_THRESHOLD: float = 0.90
    SEMANTIC_CACHE_ENABLED: bool = True
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    ATENA_LLM_MODEL: str = ""
    ATENA_CLAUDE_MODEL: str = "claude-sonnet-5-5"
    ATENA_OPENAI_MODEL: str = "gpt-4.1-mini"
    ATENA_GEMINI_MODEL: str = "gemini-2.5-flash"
    ATENA_LLM_FAST_MODEL: str = ""
    ATENA_LLM_CHAT_ORDER: str = ""
    ATENA_LLM_DEEP_ORDER: str = ""
    ATENA_LLM_RICERCATORE_ORDER: str = ""
    ATENA_LLM_DOMOTICO_ORDER: str = ""
    ATENA_LLM_STUDIO_ORDER: str = ""
    ATENA_LLM_CODER_ORDER: str = ""
    ATENA_LLM_3D_ORDER: str = ""
    ATENA_EMBED_MODEL: str = "nomic-embed-text"
    ATENA_ASSISTANT_NAME: str = ""
    ATENA_USER_NAME: str = ""
    HOME_ASSISTANT_URL: str = "http://127.0.0.1:8123"
    HOME_ASSISTANT_TOKEN: str = ""
    FRIGATE_URL: str = "http://127.0.0.1:5000"
    CODE_SANDBOX_TIMEOUT_SECONDS: int = 30
    SANDBOX_SOCKET_PATH: str = "/run/atena/sandbox/broker.sock"
    SKILL_SANDBOX_MIN_STRENGTH: Literal["container", "userspace_kernel", "microvm"] = "microvm"
    SKILL_SANDBOX_EGRESS_MIN_STRENGTH: Literal["container", "userspace_kernel", "microvm"] = "userspace_kernel"
    SKILL_SYNTHESIS_PER_HOUR: int = 6
    CONSENSUS_CRITICAL_MIN_MODELS: int = 2
    CONSENSUS_CRITICAL_TIMEOUT_SECONDS: float = 45.0
    BRAIN_ROUTES_PATH: str = "/run/atena/brain/routes.json"
    ATENA_SUPERVISOR_URL: str = "http://127.0.0.1:8080"
    
    # Proxmox Configuration
    PROXMOX_HOST: str = ""
    PROXMOX_USER: str = ""
    PROXMOX_PASSWORD: str = ""
    PROXMOX_TOKEN_ID: str = ""
    PROXMOX_TOKEN_SECRET: str = ""
    PROXMOX_VERIFY_SSL: bool = False

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = ServerSettings()
if not settings.ATENA_SECRET_KEY.strip("0"):
    settings.ATENA_SECRET_KEY = secrets.token_hex(32)
