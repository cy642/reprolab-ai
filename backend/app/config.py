"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _env(*names: str) -> str:
    """Return the first non-empty environment value among aliases."""
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return ""


@dataclass(frozen=True)
class Settings:
    storage_dir: Path
    database_path: Path
    uploads_dir: Path
    datasets_dir: Path
    max_upload_bytes: int
    dataset_max_bytes: int
    dataset_max_rows: int
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_timeout: float

    @property
    def llm_configured(self) -> bool:
        """AI parsing requires all three settings; the key never leaves the backend."""
        return bool(self.llm_base_url and self.llm_api_key and self.llm_model)


def get_settings() -> Settings:
    """Read settings on each call so tests can override environment variables."""
    storage_dir = Path(
        os.getenv("REPROLAB_STORAGE_DIR") or str(BACKEND_DIR / "storage")
    ).resolve()
    max_mb = int(os.getenv("REPROLAB_MAX_UPLOAD_MB", "20"))
    dataset_max_mb = int(os.getenv("REPROLAB_DATASET_MAX_UPLOAD_MB", "10"))
    dataset_max_bytes = int(
        os.getenv("REPROLAB_DATASET_MAX_BYTES", str(dataset_max_mb * 1024 * 1024))
    )
    llm_enabled = os.getenv("REPROLAB_DISABLE_LLM") != "1"
    return Settings(
        storage_dir=storage_dir,
        database_path=storage_dir / "reprolab.sqlite3",
        uploads_dir=storage_dir / "uploads",
        datasets_dir=storage_dir / "datasets",
        max_upload_bytes=max_mb * 1024 * 1024,
        dataset_max_bytes=dataset_max_bytes,
        dataset_max_rows=int(os.getenv("REPROLAB_DATASET_MAX_ROWS", "50000")),
        llm_base_url=_env("LLM_BASE_URL", "OPENAI_BASE_URL") if llm_enabled else "",
        llm_api_key=_env("LLM_API_KEY", "OPENAI_API_KEY") if llm_enabled else "",
        llm_model=_env("LLM_MODEL", "OPENAI_MODEL") if llm_enabled else "",
        llm_timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "90")),
    )


def public_ai_info() -> dict[str, object]:
    """Expose configuration state without ever returning the API key."""
    settings = get_settings()
    return {
        "configured": settings.llm_configured,
        "model": settings.llm_model or None,
        "base_url": settings.llm_base_url or None,
    }
