"""Check that sign-in with Autodesk is ready (configuration, Autodesk service, ShotGrid accounts).

    python scripts/check_login_setup.py

Read-only: it changes nothing. Exit code 1 if something blocks sign-in.
"""
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode, urlparse

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import config  # noqa: E402
from backend.auth import AUTODESK_DISCOVERY  # noqa: E402
from backend.config import role_set  # noqa: E402

OK, WARN, FAIL = "OK      ", "ATTENTION", "BLOQUANT"
problems = 0


def report(level: str, message: str) -> None:
    global problems
    problems += level == FAIL
    print(f"[{level}] {message}")


def check_settings() -> None:
    s = config.settings
    print("\n== Configuration (.env) ==")
    if s.aps_client_id and s.aps_client_secret:
        report(OK, "APS_CLIENT_ID et APS_CLIENT_SECRET sont renseignés.")
    else:
        report(FAIL, "APS_CLIENT_ID et/ou APS_CLIENT_SECRET manquent : le bouton « Se connecter avec Autodesk » n'apparaîtra pas.")

    import os
    secret = os.getenv("APP_SECRET", "")
    if not secret or secret == "replace-with-a-long-random-value":
        report(FAIL, "APP_SECRET n'est pas défini : tout le monde sera déconnecté à chaque redémarrage.")
    elif len(secret) < 32:
        report(WARN, "APP_SECRET est court (moins de 32 caractères) : générez-en un plus long.")
    else:
        report(OK, "APP_SECRET est défini.")

    url = urlparse(s.app_base_url)
    local = url.hostname in ("localhost", "127.0.0.1")
    if url.scheme == "https":
        report(OK, f"APP_BASE_URL est en HTTPS ({s.app_base_url}).")
    elif local:
        report(WARN, f"APP_BASE_URL est local ({s.app_base_url}) : la connexion ne marchera que sur cette machine.")
    else:
        report(FAIL, f"APP_BASE_URL ({s.app_base_url}) n'est pas en HTTPS : obligatoire hors localhost.")

    callback = s.aps_callback_url or f"{s.app_base_url}/auth/autodesk/callback"
    report(OK, f"URL de rappel à déclarer chez Autodesk : {callback}")

    if s.dev_login_as and s.dev_login_enabled:
        report(WARN, "DEV_LOGIN_AS est actif (localhost) : n'importe qui sur cette machine peut se connecter sans Autodesk.")
    elif s.dev_login_as:
        report(OK, "DEV_LOGIN_AS est ignoré (APP_BASE_URL n'est pas localhost).")


def check_autodesk() -> None:
    print("\n== Service de connexion Autodesk ==")
    try:
        meta = httpx.get(AUTODESK_DISCOVERY, timeout=15).json()
        report(OK, f"Joignable ({meta.get('authorization_endpoint')}).")
    except Exception as exc:  # network, proxy, DNS…
        report(FAIL, f"Injoignable depuis ce serveur : {exc}")


def _follow_autodesk(url: str) -> httpx.URL:
    """Follow redirects while they stay on Autodesk; return the first non-Autodesk (or last) URL."""
    with httpx.Client(follow_redirects=False, timeout=20, headers={"User-Agent": "Mozilla/5.0"}) as client:
        for _ in range(8):
            current = httpx.URL(url)
            if not current.host.endswith("autodesk.com"):
                return current
            location = client.get(url).headers.get("location")
            if not location:
                return current
            url = str(current.join(location))
    return httpx.URL(url)


def check_callback() -> None:
    """Ask Autodesk whether our callback URL is registered for this application.

    Autodesk sends an unregistered redirect_uri to a generic "request-error" page. Without any
    redirect_uri, it falls back to the application's registered callback, which tells us what
    is actually declared.
    """
    s = config.settings
    if not (s.aps_client_id and s.aps_client_secret):
        return
    print("\n== Application Autodesk ==")
    expected = s.aps_callback_url or f"{s.app_base_url}/auth/autodesk/callback"
    base = "https://developer.api.autodesk.com/authentication/v2/authorize"
    params = {"response_type": "code", "client_id": s.aps_client_id, "scope": "openid user-profile:read"}
    try:
        ours = _follow_autodesk(f"{base}?{urlencode({**params, 'redirect_uri': expected})}")
        declared = _follow_autodesk(f"{base}?{urlencode(params)}")
    except Exception as exc:
        report(WARN, f"Vérification impossible : {exc}")
        return
    if ours.host.endswith("autodesk.com") and "error" not in ours.path:
        report(OK, f"Autodesk accepte l'URL de rappel {expected}.")
        return
    registered = "" if declared.host.endswith("autodesk.com") else f"{declared.scheme}://{declared.netloc.decode()}{declared.path}"
    report(FAIL, f"Autodesk refuse l'URL de rappel {expected} : elle n'est pas déclarée dans l'application."
                 + (f" URL actuellement déclarée : {registered}" if registered else "")
                 + "\n           Ajoutez-la dans aps.autodesk.com > My applications > votre application > Callback URL.")


def check_shotgrid_users() -> None:
    print("\n== Comptes ShotGrid (copie locale) ==")
    db_path = Path(config.settings.database_path)
    if not db_path.exists():
        report(FAIL, f"Base introuvable ({db_path}) : lancez le serveur et une synchronisation d'abord.")
        return
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    people = [json.loads(r[0]) for r in db.execute(
        "SELECT data_json FROM shotgrid_records WHERE entity_type='HumanUser'")]
    active = [p for p in people if p.get("sg_status_list") != "dis"]
    if not active:
        report(FAIL, "Aucun utilisateur ShotGrid actif dans la copie locale : lancez une synchronisation.")
        return
    report(OK, f"{len(active)} utilisateurs ShotGrid actifs.")

    no_email = [p for p in active if "@" not in (p.get("email") or "") or (p.get("email") or "").upper().endswith("TBD")]
    if no_email:
        report(WARN, f"{len(no_email)} comptes actifs sans adresse e-mail valide ne pourront pas se connecter : "
                     + ", ".join(sorted(p.get("login") or str(p["id"]) for p in no_email)))

    emails = Counter((p.get("email") or "").casefold() for p in active if p.get("email"))
    ambiguous = []
    for email, n in emails.items():
        if n < 2:
            continue
        same = [p for p in active if (p.get("email") or "").casefold() == email]
        if sum(1 for p in same if (p.get("login") or "").casefold() == email) != 1:
            ambiguous.append(f"{email} ({n} comptes : {', '.join(p.get('login') or '?' for p in same)})")
    if ambiguous:
        report(WARN, f"{len(ambiguous)} adresses partagées par plusieurs comptes actifs : connexion refusée pour "
                     "elles tant que les doublons ne sont pas corrigés dans ShotGrid :\n           - "
                     + "\n           - ".join(sorted(ambiguous)))
    else:
        report(OK, "Aucune adresse e-mail ambiguë.")

    see_all, admins = role_set(config.settings.roles_see_all), role_set(config.settings.admin_roles)
    roles = Counter((p.get("permission_rule_set") or {}).get("name") or "(aucun)" for p in active)
    print("\n== Ce que verra chaque groupe ==")
    for role, n in roles.most_common():
        scope = "toutes les productions" if role.casefold() in see_all else "ses productions seulement"
        admin = ", gère la synchronisation" if role.casefold() in admins else ""
        print(f"   {role:<28} {n:>3} personnes : {scope}{admin}")


if __name__ == "__main__":
    check_settings()
    check_autodesk()
    check_callback()
    check_shotgrid_users()
    print()
    if problems:
        print(f"{problems} point(s) bloquant(s) à corriger.")
        sys.exit(1)
    print("Tout est prêt pour la connexion Autodesk.")
