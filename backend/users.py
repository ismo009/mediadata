"""Signed-in users: who they are in ShotGrid and which productions they may see."""
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend import config
from backend.config import role_set
from backend.db import database


@dataclass(frozen=True)
class User:
    id: int
    login: str
    name: str
    email: str
    role: str
    sees_all: bool
    is_admin: bool
    # Productions the user is a member of (used for "mes productions" even when sees_all).
    member_projects: frozenset[int]

    @property
    def visible_projects(self) -> Optional[frozenset[int]]:
        """None = every production; otherwise the only productions this user may see."""
        return None if self.sees_all else self.member_projects

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "email": self.email, "login": self.login,
                "role": self.role, "is_admin": self.is_admin, "sees_all": self.sees_all}


class LoginError(Exception):
    """Raised with a message that can be shown on the sign-in page."""


def _human_users(connection) -> list[dict]:
    return [json.loads(r[0]) for r in connection.execute(
        "SELECT data_json FROM main.shotgrid_records WHERE entity_type='HumanUser'"
    )]


def find_shotgrid_user(identity: str) -> dict:
    """The active ShotGrid HumanUser behind an Autodesk e-mail (or a login).

    Several ShotGrid accounts can share an e-mail: an active one wins, an exact login match
    breaks ties, and anything still ambiguous is refused rather than guessed.
    """
    key = (identity or "").strip().casefold()
    if not key:
        raise LoginError("Votre compte Autodesk ne fournit pas d'adresse e-mail.")
    connection = database()
    try:
        people = _human_users(connection)
    finally:
        connection.close()
    matches = [p for p in people
               if (p.get("email") or "").casefold() == key or (p.get("login") or "").casefold() == key]
    active = [p for p in matches if p.get("sg_status_list") != "dis"]
    if not active:
        if matches:
            raise LoginError("Votre compte ShotGrid est désactivé. Contactez un administrateur ShotGrid.")
        raise LoginError(f"Aucun utilisateur ShotGrid ne correspond à {identity}. "
                         "Vérifiez que vous utilisez le même compte que pour ShotGrid.")
    if len(active) > 1:
        by_login = [p for p in active if (p.get("login") or "").casefold() == key]
        if len(by_login) != 1:
            raise LoginError(f"Plusieurs utilisateurs ShotGrid actifs utilisent {identity}. "
                             "Un administrateur ShotGrid doit corriger les doublons.")
        active = by_login
    return active[0]


def load_user(user_id: int) -> Optional[User]:
    """Build the User from the local copy of ShotGrid (role and memberships stay current)."""
    connection = database()
    try:
        row = connection.execute(
            "SELECT data_json FROM main.shotgrid_records WHERE entity_type='HumanUser' AND entity_id=?",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        data = json.loads(row[0])
        if data.get("sg_status_list") == "dis":
            return None
        projects = {r[0] for r in connection.execute(
            """
            SELECT src_id FROM shotgrid_links
            WHERE src_type='Project' AND field='users' AND dst_type='HumanUser' AND dst_id=?
            UNION
            SELECT dst_id FROM shotgrid_links
            WHERE src_type='HumanUser' AND src_id=? AND field='projects' AND dst_type='Project'
            """,
            (user_id, user_id),
        )}
    finally:
        connection.close()
    role = (data.get("permission_rule_set") or {}).get("name") or ""
    s = config.settings
    return User(
        id=user_id,
        login=data.get("login") or "",
        name=data.get("name") or data.get("login") or f"Utilisateur {user_id}",
        email=data.get("email") or "",
        role=role,
        sees_all=role.casefold() in role_set(s.roles_see_all),
        is_admin=role.casefold() in role_set(s.admin_roles),
        member_projects=frozenset(projects),
    )


# ------------------------------------------------------------------------- sessions

def create_session(user_id: int) -> str:
    key = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    connection = database()
    try:
        with connection:
            connection.execute("DELETE FROM user_sessions WHERE expires_at < ?", (now.isoformat(),))
            connection.execute(
                "INSERT INTO user_sessions (session_key, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (key, user_id, now.isoformat(),
                 (now + timedelta(days=config.settings.session_days)).isoformat()),
            )
    finally:
        connection.close()
    return key


def session_user_id(key: Optional[str]) -> Optional[int]:
    if not key:
        return None
    connection = database()
    try:
        row = connection.execute(
            "SELECT user_id FROM user_sessions WHERE session_key=? AND expires_at > ?",
            (key, datetime.now(timezone.utc).isoformat()),
        ).fetchone()
    finally:
        connection.close()
    return row[0] if row else None


def end_session(key: Optional[str]) -> None:
    if not key:
        return
    connection = database()
    try:
        with connection:
            connection.execute("DELETE FROM user_sessions WHERE session_key=?", (key,))
            connection.execute("DELETE FROM user_tokens WHERE session_key=?", (key,))
    finally:
        connection.close()
