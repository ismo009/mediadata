"""Sign-in with Autodesk, sessions, and per-user visibility (UI, API and assistant)."""
import dataclasses
import sqlite3

import pytest

from backend import auth, config, db
from backend.retrieval import retrieve
from backend.users import LoginError, find_shotgrid_user, load_user
from tests.conftest import sign_in


def ids(records, entity_type=None):
    if isinstance(records, dict):  # a retrieve() result
        records = records["records"]
    return {r["id"] for r in records if entity_type is None or r.get("entity_type", r.get("type")) == entity_type}


# ------------------------------------------------------------------ anonymous access

def test_everything_requires_sign_in(http):
    http.post("/auth/logout")
    for method, url in [("get", "/api/dashboard"), ("get", "/api/projects/1"), ("get", "/api/records/Task"),
                        ("get", "/api/people"), ("get", "/api/search?q=flou"), ("get", "/api/models"),
                        ("get", "/api/thumbnails?entity_type=Shot&ids=20"), ("post", "/api/sync")]:
        assert getattr(http, method)(url).status_code == 401, url
    assert http.post("/api/query/stream", json={"question": "x"}).status_code == 401
    me = http.get("/api/me").json()
    assert me["authenticated"] is False and me["autodesk"] is False
    assert me["dev_login"] is True  # the fixture signed in through the localhost dev login


def test_logout_ends_the_session(http):
    assert http.get("/api/dashboard").status_code == 200
    http.post("/auth/logout")
    assert http.get("/api/dashboard").status_code == 401


def test_dev_login_only_on_localhost(http, monkeypatch):
    monkeypatch.setattr(config, "settings", dataclasses.replace(
        config.settings, app_base_url="https://mediadata.example.com", dev_login_as="marie@studio.test"))
    assert http.get("/auth/dev-login", follow_redirects=False).status_code == 404


# -------------------------------------------------------------- identity matching

def test_autodesk_email_maps_to_the_shotgrid_user(fake):
    from backend import sync
    sync.sync_shotgrid(mode="full")
    assert find_shotgrid_user("MARIE@studio.test")["id"] == 40
    with pytest.raises(LoginError, match="désactivé"):
        find_shotgrid_user("ancien@studio.test")
    with pytest.raises(LoginError, match="Aucun utilisateur"):
        find_shotgrid_user("inconnu@ailleurs.test")
    # Two active accounts share the e-mail: the one whose login is the e-mail wins...
    assert find_shotgrid_user("double@studio.test")["id"] == 44
    # ...and when nothing breaks the tie, sign-in is refused rather than guessed.
    with pytest.raises(LoginError, match="Plusieurs"):
        find_shotgrid_user("triple@studio.test")


def test_roles_decide_what_users_see(fake):
    from backend import sync
    sync.sync_shotgrid(mode="full")
    marie, paul = load_user(40), load_user(41)
    assert marie.is_admin and marie.sees_all and marie.visible_projects is None
    assert not paul.is_admin and not paul.sees_all and paul.visible_projects == {2}
    assert load_user(42) is None  # disabled in ShotGrid


# ------------------------------------------------------------- Autodesk callback

@pytest.fixture
def autodesk(monkeypatch):
    monkeypatch.setattr(config, "settings", dataclasses.replace(
        config.settings, aps_client_id="client", aps_client_secret="secret"))
    profile = {"sub": "abc", "email": "paul@studio.test"}

    async def authorize_access_token(request):
        return {"access_token": "t", "id_token": "i"}

    async def userinfo(token):
        return profile

    monkeypatch.setattr(auth.oauth.autodesk, "authorize_access_token", authorize_access_token)
    monkeypatch.setattr(auth.oauth.autodesk, "userinfo", userinfo)
    return profile


def test_autodesk_callback_signs_the_user_in(http, autodesk):
    http.post("/auth/logout")
    response = http.get("/auth/autodesk/callback?code=c&state=s", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/"
    me = http.get("/api/me").json()
    assert me["authenticated"] and me["name"] == "Paul Martin" and me["role"] == "Artist"
    assert me["is_admin"] is False


def test_autodesk_callback_with_unknown_account_explains_why(http, autodesk):
    http.post("/auth/logout")
    autodesk["email"] = "inconnu@ailleurs.test"
    response = http.get("/auth/autodesk/callback?code=c&state=s", follow_redirects=False)
    assert response.headers["location"] == "/#/login"
    me = http.get("/api/me").json()
    assert me["authenticated"] is False and "Aucun utilisateur ShotGrid" in me["login_error"]
    assert "login_error" not in http.get("/api/me").json() or http.get("/api/me").json()["login_error"] is None


# ------------------------------------------------- an Artist only sees their production

@pytest.fixture
def as_paul(http, monkeypatch):
    sign_in(http, monkeypatch, "paul@studio.test")
    return http


def test_artist_dashboard_and_project_pages(as_paul):
    assert {p["id"] for p in as_paul.get("/api/dashboard").json()["projects"]} == {2}
    assert as_paul.get("/api/projects/1").status_code == 404
    assert as_paul.get("/api/projects/2").status_code == 200


def test_artist_lists_search_and_thumbnails(as_paul, fake):
    assert ids(as_paul.get("/api/records/Task").json()["records"]) == {104}
    assert as_paul.get("/api/records/Note").json()["total"] == 0
    assert as_paul.get("/api/search", params={"q": "flou"}).json()["results"] == []
    fake.data["Shot"][0]["image"] = "https://media.test/sh020.jpg"
    assert as_paul.get("/api/thumbnails", params={"entity_type": "Shot", "ids": "20"}).json() == {}


def test_artist_people_counts_exclude_hidden_tasks(as_paul):
    marie = next(p for p in as_paul.get("/api/people").json()["people"] if p["id"] == 40)
    assert marie["tasks"] == 0  # Marie's tasks are all in production 1
    assert [t["id"] for t in as_paul.get("/api/people/40").json()["tasks"]] == []


def test_artist_cannot_run_or_inspect_syncs(as_paul):
    assert as_paul.post("/api/sync").status_code == 403
    assert as_paul.get("/api/sync/runs").status_code == 403
    assert as_paul.get("/api/sync/audit").status_code == 403
    assert as_paul.get("/api/entity-types").status_code == 403
    assert as_paul.get("/api/sync/status").status_code == 200


def test_assistant_only_sees_what_the_user_sees(http):
    paul = load_user(41)
    assert ids(retrieve("tâches en retard", user=paul), "Task") == set()
    assert ids(retrieve("Quelles tâches sont ouvertes ?", user=paul), "Task") == {104}
    # A production the user cannot see is not even recognised by name.
    hidden = retrieve("Où en est Les Cocottes en Papier ?", user=paul)
    assert "Cocottes" not in hidden["scope"]
    assert not any(r.get("name") == "Les Cocottes en Papier" for r in hidden["records"])
    assert retrieve("Quels sont les projets ?", user=paul)["stats"]["total"] == 1


def test_my_tasks_and_my_productions(http):
    marie = load_user(40)
    mine = retrieve("Quelles sont mes tâches ?", user=marie)
    assert ids(mine, "Task") == {100, 102} and "Marie Curie" in mine["scope"]
    assert ids(retrieve("mes tâches en retard", user=marie), "Task") == {100}
    assert ids(retrieve("Quelles sont mes productions ?", user=marie), "Project") == {1}
    # Without "mes", the question is not narrowed to the user.
    assert ids(retrieve("Quelles tâches sont ouvertes ?", user=marie), "Task") == {100, 101, 103, 104}


def test_restricted_connection_refuses_writes(fake):
    connection = db.database(visible_projects={2})
    with pytest.raises(sqlite3.OperationalError):
        connection.execute("DELETE FROM shotgrid_records")
    connection.close()
