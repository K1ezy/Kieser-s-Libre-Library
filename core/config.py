from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    # --- APP & AUTH CONFIGURATION ---
    PROJECT_NAME: str = "Libre Library"
    VERSION: str = "2.0.0"
    SECRET_KEY: str = "libre_library_secure_key_2025" 
    JWT_SECRET: str = "libre_library_secure_key_2025"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    UI_THEME_COLOR: str = "#5c6ac4"

    # --- DATABASE CONFIGURATION ---
    MONGO_URI: str = "mongodb://localhost:27017"
    DB_NAME: str = "libre_library_db"

    # --- PATHS ---
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    
    # FIX: Pointing to your E-Books folder
    # We use "E-Books" relative to the project root.
    BOOKS_DIR: Path = BASE_DIR / "E-Books" 

    BOOKS_INFO_DIR: Path = BASE_DIR / "data" / "books"
    

    MODEL_DIR: Path = BASE_DIR / "models"
    MODEL_FILENAME: str = "Llama-3.2-3B-Instruct-Q8_0.gguf" 
    
    GPU_LAYERS: int = 20  # Use -1 for full GPU usage
    CONTEXT_WINDOW: int = 8192
    CHROMA_PATH: Path = BASE_DIR / "data" / "chroma_db"
    VERBOSE: bool = True
    
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        extra="ignore"
    )

settings = Settings()