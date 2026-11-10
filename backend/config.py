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
    # Context window requested from Ollama (prompt + data + history + answer).
    ollama_num_ctx: int = _int_env("OLLAMA_NUM_CTX", 16384)
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

    # --- Sign-in with Autodesk (APS OAuth / OpenID Connect) ---
    aps_client_id: str = os.getenv("APS_CLIENT_ID", "")
    aps_client_secret: str = os.getenv("APS_CLIENT_SECRET", "")
    aps_callback_url: str = os.getenv("APS_CALLBACK_URL", "")
    session_days: int = _int_env("SESSION_DAYS", 7)
    # ShotGrid permission groups (HumanUser.permission_rule_set) that see every production.
    # Everyone else sees only the productions they are a member of. "Audit - Conseil" is
    # included because the sync account has that role and ShotGrid lets it read every project.
    roles_see_all: str = os.getenv("ROLES_SEE_ALL", "Admin,Admin Copy,Manager,Supervisor,Audit - Conseil")
    # Groups allowed to run syncs and see the sync page.
    admin_roles: str = os.getenv("ADMIN_ROLES", "Admin,Admin Copy")
    # Local development only: sign in as this ShotGrid login/e-mail without Autodesk.
    # Ignored unless APP_BASE_URL points to localhost.
    dev_login_as: str = os.getenv("DEV_LOGIN_AS", "")

    @property
    def autodesk_login_enabled(self) -> bool:
        return bool(self.aps_client_id and self.aps_client_secret)

    @property
    def dev_login_enabled(self) -> bool:
        host = self.app_base_url.split("//")[-1].split("/")[0].split(":")[0]
        return bool(self.dev_login_as) and host in ("localhost", "127.0.0.1")


def role_set(value: str) -> set[str]:
    return {r.strip().casefold() for r in value.split(",") if r.strip()}


settings = Settings()
