from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from pathlib import Path
import os
import secrets
import logging
from typing import List

logger = logging.getLogger("CONFIG")

_BASE_DIR = Path(__file__).resolve().parent.parent

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
    BASE_DIR: Path = _BASE_DIR
    BOOKS_DIR: Path = _BASE_DIR / "E-Books"
    BOOKS_INFO_DIR: Path = _BASE_DIR / "data" / "books"
    MODEL_DIR: Path = _BASE_DIR / "models"
    MODEL_FILENAME: str = "Llama-3.2-3B-Instruct-Q8_0.gguf"
    
    GPU_LAYERS: int = 20  # Use -1 for full GPU usage
    CONTEXT_WINDOW: int = 8192
    CHROMA_PATH: Path = _BASE_DIR / "data" / "chroma_db"
    VERBOSE: bool = True
    
    # --- AI PROVIDER CONFIGURATION ---
    AI_PROVIDER: str = "local"  # "local", "ollama", "openai"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2:latest"
    OPENAI_API_BASE: str = "https://api.openai.com/v1"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    @model_validator(mode="after")
    def validate_secrets(self) -> "Settings":
        # Ensure secret keys are populated and not hardcoded defaults
        if not self.SECRET_KEY or self.SECRET_KEY == "libre_library_secure_key_2025":
            self.SECRET_KEY = _get_or_create_secure_secret(self.BASE_DIR)
        if not self.JWT_SECRET or self.JWT_SECRET == "libre_library_secure_key_2025":
            self.JWT_SECRET = self.SECRET_KEY
        return self

    def get_cors_origins(self) -> List[str]:
        """Returns list of allowed CORS origins."""
        if not self.CORS_ALLOWED_ORIGINS:
            return ["http://localhost:8080", "http://127.0.0.1:8080"]
        return [o.strip() for o in self.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]
    
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        extra="ignore"
    )

settings = Settings()