"""Google OAuth (for Drive search). Tokens stay in the database, never in the cookie."""
import json
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from backend import config
from backend.db import database

router = APIRouter()

oauth = OAuth()
oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    client_kwargs={"scope": "openid email profile https://www.googleapis.com/auth/drive.readonly"},
)


def google_access_token(request: Request) -> Optional[str]:
    key = (request.session.get("user") or {}).get("key")
    if key:
        connection = database()
        try:
            row = connection.execute(
                "SELECT token_json FROM user_tokens WHERE session_key=?", (key,)
            ).fetchone()
        finally:
            connection.close()
        if row:
            return json.loads(row["token_json"]).get("access_token")
    return os.getenv("GOOGLE_ACCESS_TOKEN") or None


@router.get("/auth/google/login")
async def google_login(request: Request):
    if not os.getenv("GOOGLE_CLIENT_ID") or not os.getenv("GOOGLE_CLIENT_SECRET"):
        raise HTTPException(status_code=503, detail="Google OAuth n'est pas configuré")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", f"{config.settings.app_base_url}/auth/google/callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/auth/google/callback")
async def google_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Échec de l'authentification Google") from exc
    user = token.get("userinfo")
    if not user or not user.get("sub") or not user.get("email"):
        raise HTTPException(status_code=401, detail="Profil Google incomplet")
    key = secrets.token_urlsafe(32)
    connection = database()
    try:
        with connection:
            connection.execute(
                "INSERT INTO user_tokens (session_key, token_json, created_at) VALUES (?, ?, ?)",
                (key, json.dumps({"access_token": token["access_token"]}),
                 datetime.now(timezone.utc).isoformat()),
            )
    finally:
        connection.close()
    request.session["user"] = {
        "key": key, "id": user["sub"], "email": user["email"], "name": user.get("name", user["email"]),
    }
    return RedirectResponse("/")


@router.post("/auth/logout")
async def logout(request: Request) -> dict[str, bool]:
    key = (request.session.get("user") or {}).get("key")
    if key:
        connection = database()
        try:
            with connection:
                connection.execute("DELETE FROM user_tokens WHERE session_key=?", (key,))
        finally:
            connection.close()
    request.session.clear()
    return {"authenticated": False}


@router.get("/api/me")
async def me(request: Request) -> dict[str, Any]:
    user = request.session.get("user")
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, "id": user["id"], "email": user["email"], "name": user.get("name")}
