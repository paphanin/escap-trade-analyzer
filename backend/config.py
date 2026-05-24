import os
from pathlib import Path
from pydantic_settings import BaseSettings

# All persistent data lives under DATA_DIR.
# Locally this is the current working directory; on Railway set DATA_DIR=/data
_DATA_DIR = Path(os.getenv("DATA_DIR", "."))


class Settings(BaseSettings):
    anthropic_api_key: str
    upload_dir: Path = _DATA_DIR / "uploads"
    db_url: str = f"sqlite+aiosqlite:///{_DATA_DIR}/escap.db"
    chroma_path: str = str(_DATA_DIR / "chroma_db")
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    max_pages_per_doc: int = 40
    parse_model: str = "claude-haiku-4-5-20251001"
    extract_model: str = "claude-haiku-4-5-20251001"
    vision_fallback_threshold: int = 150
    parse_concurrency: int = 2
    extract_concurrency: int = 3

    class Config:
        env_file = ".env"


settings = Settings()
