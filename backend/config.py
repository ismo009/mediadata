"""Application settings, read once from the environment / .env file."""
import logging
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

log = logging.getLogger("mediadata")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _app_secret() -> str:
    secret = os.getenv("APP_SECRET", "")
    if secret and secret != "replace-with-a-long-random-value":
        return secret
    log.warning(
        "APP_SECRET absent : clé de session aléatoire générée (les sessions seront "
        "perdues au redémarrage). Définissez APP_SECRET dans .env."
    )
    return secrets.token_urlsafe(48)


@dataclass(frozen=True)
class Settings:
    app_secret: str = field(default_factory=_app_secret)
    app_base_url: str = os.getenv("APP_BASE_URL", "http://localhost:8000")
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "")
    shotgrid_url: str = os.getenv("SHOTGRID_SERVER_URL", "").rstrip("/")
    shotgrid_login: str = os.getenv("SHOTGRID_LOGIN", "")
    shotgrid_passphrase: str = os.getenv("SHOTGRID_PASSPHRASE", "")
    shotgrid_script_name: str = os.getenv("SHOTGRID_SCRIPT_NAME", "")
    shotgrid_script_key: str = os.getenv("SHOTGRID_SCRIPT_KEY", "")
    database_path: str = os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "dashboard.sqlite3"))
    # "auto" = every non-system ShotGrid entity type that has records,
    # otherwise a comma-separated list such as "Project,Shot,Task".
    sync_entities: str = os.getenv("SYNC_ENTITIES", "auto")
    # Background incremental sync every N minutes (0 disables the scheduler).
    sync_interval_minutes: int = _int_env("SYNC_INTERVAL_MINUTES", 30)
    # A full sync (re-checks every record) runs when the last one is older than this.
    full_sync_every_hours: int = _int_env("FULL_SYNC_EVERY_HOURS", 24)


settings = Settings()
