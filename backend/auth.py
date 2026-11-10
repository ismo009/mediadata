"""Sign-in with Autodesk (same account as ShotGrid), sessions, and access dependencies.

Flow: /auth/autodesk/login → Autodesk sign-in page → /auth/autodesk/callback. The Autodesk
e-mail is matched to an active ShotGrid HumanUser; that user's permission group decides what
they see (backend/users.py). The cookie only carries a random session key; sessions live in
the database so signing out really ends them.

Google OAuth is kept only to let a signed-in user connect Google Drive for Lia.
"""
import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from backend import config
from backend.config import log
from backend.db import database
from backend.users import LoginError, User, create_session, end_session, find_shotgrid_user, load_user, session_user_id

router = APIRouter()

AUTODESK_DISCOVERY = "https://developer.api.autodesk.com/.well-known/openid-configuration"

oauth = OAuth()
oauth.register(
    name="autodesk",
    server_metadata_url=AUTODESK_DISCOVERY,
    client_id=config.settings.aps_client_id or None,
    client_secret=config.settings.aps_client_secret or None,
    client_kwargs={
        "scope": "openid user-profile:read",
        "code_challenge_method": "S256",
        "token_endpoint_auth_method": "client_secret_basic",
    },
)
oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    client_kwargs={"scope": "openid email profile https://www.googleapis.com/auth/drive.readonly"},
)


# --------------------------------------------------------------------- dependencies

def current_user(request: Request) -> Optional[User]:
    user_id = session_user_id(request.session.get("sid"))
    return load_user(user_id) if user_id else None


def require_user(request: Request) -> User:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Connexion requise")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs")
    return user


def _sign_in(request: Request, user_id: int) -> None:
    end_session(request.session.get("sid"))
    request.session.clear()
    request.session["sid"] = create_session(user_id)


def _fail(request: Request, message: str) -> RedirectResponse:
    # The message is shown on the sign-in page (kept in the session, not in the URL).
    request.session["login_error"] = message
    return RedirectResponse("/#/login", status_code=303)


# ------------------------------------------------------------------ Autodesk sign-in

def _callback_url() -> str:
    return config.settings.aps_callback_url or f"{config.settings.app_base_url}/auth/autodesk/callback"


@router.get("/auth/autodesk/login")
async def autodesk_login(request: Request):
    if not config.settings.autodesk_login_enabled:
        raise HTTPException(status_code=503, detail="La connexion Autodesk n'est pas configurée (APS_CLIENT_ID).")
    return await oauth.autodesk.authorize_redirect(request, _callback_url())


@router.get("/auth/autodesk/callback")
async def autodesk_callback(request: Request):
    if request.query_params.get("error"):
        return _fail(request, "Connexion Autodesk annulée.")
    try:
        token = await oauth.autodesk.authorize_access_token(request)
        profile = await oauth.autodesk.userinfo(token=token)
    except Exception as exc:
        log.warning("Échec de la connexion Autodesk : %s", exc)
        return _fail(request, "La connexion Autodesk a échoué. Réessayez.")
    email = profile.get("email") or profile.get("preferred_username") or ""
    try:
        person = find_shotgrid_user(email)
    except LoginError as exc:
        return _fail(request, str(exc))
    _sign_in(request, person["id"])
    return RedirectResponse("/", status_code=303)


@router.get("/auth/dev-login")
async def dev_login(request: Request):
    """Local development without Autodesk: signs in as DEV_LOGIN_AS (localhost only)."""
    if not config.settings.dev_login_enabled:
        raise HTTPException(status_code=404)
    try:
        person = find_shotgrid_user(config.settings.dev_login_as)
    except LoginError as exc:
        return _fail(request, str(exc))
    _sign_in(request, person["id"])
    return RedirectResponse("/", status_code=303)


@router.post("/auth/logout")
async def logout(request: Request) -> dict[str, bool]:
    end_session(request.session.get("sid"))
    request.session.clear()
    return {"authenticated": False}


@router.get("/api/me")
async def me(request: Request) -> dict[str, Any]:
    user = current_user(request)
    if not user:
        return {
            "authenticated": False,
            "login_error": request.session.pop("login_error", None),
            "autodesk": config.settings.autodesk_login_enabled,
            "dev_login": config.settings.dev_login_enabled,
        }
    return {"authenticated": True, **user.public(), "projects": sorted(user.member_projects),
            "drive_connected": bool(google_access_token(request))}


# ------------------------------------------------------- Google Drive (for Lia only)

def google_access_token(request: Request) -> Optional[str]:
    key = request.session.get("sid")
    if key:
        connection = database()
        try:
            row = connection.execute("SELECT token_json FROM user_tokens WHERE session_key=?", (key,)).fetchone()
        finally:
            connection.close()
        if row:
            return json.loads(row["token_json"]).get("access_token")
    # No shared GOOGLE_ACCESS_TOKEN fallback: with several users it would show one person's
    # Drive to everyone.
    return None


@router.get("/auth/google/login")
async def google_login(request: Request, _user: User = Depends(require_user)):
    if not os.getenv("GOOGLE_CLIENT_ID") or not os.getenv("GOOGLE_CLIENT_SECRET"):
        raise HTTPException(status_code=503, detail="Google OAuth n'est pas configuré")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", f"{config.settings.app_base_url}/auth/google/callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/auth/google/callback")
async def google_callback(request: Request, _user: User = Depends(require_user)):
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Échec de l'authentification Google") from exc
    connection = database()
    try:
        with connection:
            connection.execute(
                "INSERT OR REPLACE INTO user_tokens (session_key, token_json, created_at) VALUES (?, ?, ?)",
                (request.session["sid"], json.dumps({"access_token": token["access_token"]}),
                 datetime.now(timezone.utc).isoformat()),
            )
    finally:
        connection.close()
    return RedirectResponse("/", status_code=303)
