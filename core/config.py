from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from pathlib import Path
import os
import secrets
import logging
from typing import List

logger = logging.getLogger("CONFIG")

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "models"

# Model Fallback Priority List
PREFERRED_MODELS = [
    "qwen2.5-3b-instruct-q4_k_m.gguf",
    "qwen2.5-7b-instruct-q4_k_m.gguf",
    "Llama-3.2-3B-Instruct-Q8_0.gguf",
]


def resolve_default_model() -> str:
    env_model = os.getenv("MODEL_FILENAME")
    if env_model and (MODEL_DIR / env_model).exists():
        return env_model
    for candidate in PREFERRED_MODELS:
        if (MODEL_DIR / candidate).exists():
            return candidate
    return PREFERRED_MODELS[0]


MODEL_FILENAME = resolve_default_model()
EMBEDDING_MODEL_PATH = str(MODEL_DIR / "all-MiniLM-L6-v2")

# Hardware & Context Limits
GPU_LAYERS = int(os.getenv("GPU_LAYERS", "-1"))
CONTEXT_WINDOW = int(os.getenv("CONTEXT_WINDOW", "4096"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "512"))

# Deterministic RAG Sampling Parameters
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.05"))
LLM_TOP_P = float(os.getenv("LLM_TOP_P", "0.90"))
LLM_REPEAT_PENALTY = float(os.getenv("LLM_REPEAT_PENALTY", "1.15"))
RAG_MAX_DISTANCE = float(os.getenv("RAG_MAX_DISTANCE", "0.90"))

# Provider Configuration ("local" or "openai")
AI_PROVIDER = os.getenv("AI_PROVIDER", "local")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "http://localhost:11434/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "ollama")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "qwen2.5:7b")


def _get_or_create_secure_secret(base_dir: Path) -> str:
    """
    Safely retrieves the secret key from environment or creates
    a persistent, cryptographically secure 256-bit random key.
    Prevents public default key vulnerabilities.
    """
    env_secret = os.getenv("SECRET_KEY", "").strip()
    if env_secret and env_secret != "libre_library_secure_key_2025":
        return env_secret

    secret_file = base_dir / "data" / ".secret_key"
    if secret_file.exists():
        try:
            stored = secret_file.read_text(encoding="utf-8").strip()
            if stored and stored != "libre_library_secure_key_2025":
                return stored
        except Exception:
            pass

    # Generate cryptographically secure random token
    new_secret = secrets.token_urlsafe(32)
    try:
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        secret_file.write_text(new_secret, encoding="utf-8")
        logger.info("Generated and stored new instance-specific encryption key.")
    except Exception as e:
        logger.warning(f"Failed to persist secret key to {secret_file}: {e}")
    return new_secret


class Settings(BaseSettings):
    # --- APP & AUTH CONFIGURATION ---
    PROJECT_NAME: str = "Libre Library"
    VERSION: str = "2.0.0"
    SECRET_KEY: str = ""
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    UI_THEME_COLOR: str = "#4f46e5"
    DEBUG: bool = False
    RELOAD: bool = False
    CORS_ALLOWED_ORIGINS: str = "http://localhost:8080,http://127.0.0.1:8080"

    # --- DATABASE CONFIGURATION ---
    MONGO_URI: str = "mongodb://localhost:27017"
    DB_NAME: str = "libre_library_db"

    # --- PATHS ---
    BASE_DIR: Path = BASE_DIR
    BOOKS_DIR: Path = BASE_DIR / "E-Books"
    BOOKS_INFO_DIR: Path = BASE_DIR / "data" / "books"
    MODEL_DIR: Path = MODEL_DIR
    MODEL_FILENAME: str = MODEL_FILENAME
    
    GPU_LAYERS: int = GPU_LAYERS
    CONTEXT_WINDOW: int = CONTEXT_WINDOW
    BATCH_SIZE: int = BATCH_SIZE
    CHROMA_PATH: Path = BASE_DIR / "data" / "chroma_db"
    VERBOSE: bool = False
    
    # --- DETERMINISTIC RAG CONSTANTS ---
    LLM_TEMPERATURE: float = LLM_TEMPERATURE
    LLM_TOP_P: float = LLM_TOP_P
    LLM_REPEAT_PENALTY: float = LLM_REPEAT_PENALTY
    RAG_MAX_DISTANCE: float = RAG_MAX_DISTANCE
    
    # --- AI PROVIDER CONFIGURATION ---
    AI_PROVIDER: str = AI_PROVIDER
    OPENAI_API_BASE: str = OPENAI_API_BASE
    OPENAI_API_KEY: str = OPENAI_API_KEY
    OPENAI_MODEL: str = OPENAI_MODEL

    @model_validator(mode="after")
    def validate_secrets(self) -> "Settings":
        if not self.SECRET_KEY or self.SECRET_KEY == "libre_library_secure_key_2025":
            self.SECRET_KEY = _get_or_create_secure_secret(self.BASE_DIR)
        if not self.JWT_SECRET or self.JWT_SECRET == "libre_library_secure_key_2025":
            self.JWT_SECRET = self.SECRET_KEY
        return self

    def get_cors_origins(self) -> List[str]:
        if not self.CORS_ALLOWED_ORIGINS:
            return ["http://localhost:8080", "http://127.0.0.1:8080"]
        return [o.strip() for o in self.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]
    
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        extra="ignore"
    )


settings = Settings()