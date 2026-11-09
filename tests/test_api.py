"""HTTP API used by the UI."""
import pytest
from fastapi.testclient import TestClient

from backend import main, sync


@pytest.fixture
def http(fake):
    sync.sync_shotgrid(mode="full")
    with TestClient(main.app) as client:
        yield client


def test_dashboard(http):
    data = http.get("/api/dashboard").json()
    assert data["projects_active"] == 1 and data["projects_total"] == 2
    p1 = next(p for p in data["projects"] if p["id"] == 1)
    assert p1["tasks"] == {"done": 1, "review": 1, "in_progress": 1, "waiting": 1, "other": 0}
    assert p1["tasks_late"] == 1
    assert data["tasks_late"] == 1


def test_project_details(http):
    data = http.get("/api/projects/1").json()
    assert data["project"]["status_label"] == "Actif"
    assert {s["step"]: s["done"] for s in data["steps"]} == {"Compositing": 1, "Animation": 0}
    assert data["sequences"] == [{"id": 10, "name": "SQ010",
                                  "shots": {"done": 1, "review": 0, "in_progress": 1, "waiting": 0, "other": 0}}]
    assert [t["id"] for t in data["late_tasks"]] == [100]
    assert [t["id"] for t in data["blocked_tasks"]] == [100]
    assert data["people"] == [{"id": 40, "name": "Marie Curie", "tasks": 2, "open": 1}]
    assert http.get("/api/projects/999").status_code == 404


@pytest.mark.parametrize("params, expected", [
    ({"project_id": 1}, {100, 101, 102, 103}),
    ({"step_id": 30}, {100, 102}),
    ({"person_id": 40, "bucket": "done"}, {102}),
    ({"late": True}, {100}),
    ({"sequence_id": 10, "bucket": "waiting"}, {101}),
    ({"search": "lighting"}, {104}),
])
def test_records_filters(http, params, expected):
    data = http.get("/api/records/Task", params=params).json()
    assert {r["id"] for r in data["records"]} == expected
    assert data["total"] == len(expected)


def test_records_pagination_and_sort(http):
    data = http.get("/api/records/Task", params={"limit": 2, "page": 2, "sort": "recent"}).json()
    assert data["pages"] == 3 and [r["id"] for r in data["records"]] == [102, 101]


def test_people(http):
    marie = next(p for p in http.get("/api/people").json()["people"] if p["id"] == 40)
    assert (marie["tasks"], marie["open"], marie["late"]) == (2, 1, 1)
    person = http.get("/api/people/40").json()
    assert [t["id"] for t in person["tasks"]] == [100, 102]  # open first


def test_search(http):
    results = http.get("/api/search", params={"q": "flou"}).json()["results"]
    assert [(r["entity_type"], r["entity_id"], r["project_name"]) for r in results] == [
        ("Note", 50, "Les Cocottes en Papier")]


def test_thumbnails_are_fetched_fresh_and_cached(http, fake):
    fake.data["Shot"][0]["image"] = "https://media.test/sh020.jpg"
    first = http.get("/api/thumbnails", params={"entity_type": "Shot", "ids": "20,21"}).json()
    assert first == {"20": "https://media.test/sh020.jpg", "21": None}
    calls = len(fake.find_calls)
    http.get("/api/thumbnails", params={"entity_type": "Shot", "ids": "20,21"})
    assert len(fake.find_calls) == calls


def test_sync_endpoints(http):
    assert http.get("/api/sync/status").json()["last_sync"]["status"] == "completed"
    assert len(http.get("/api/sync/runs").json()["runs"]) == 1
    types = {t["entity_type"] for t in http.get("/api/entity-types").json()["entity_types"]}
    assert "Task" in types


def test_legacy_query_endpoint_removed(http):
    assert http.post("/api/query", json={"question": "x"}).status_code in (404, 405)


def test_me_is_anonymous_without_login(http):
    assert http.get("/api/me").json() == {"authenticated": False}


def test_project_root_is_never_served(http):
    assert http.get("/.env").status_code == 404
    assert http.get("/dashboard.sqlite3").status_code == 404
