"""Phase 1 sync tests, using a fake in-memory ShotGrid client and a temporary SQLite DB."""
import dataclasses
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend import main


class FakeShotGrid:
    """Minimal stand-in for shotgun_api3.Shotgun: find (paged, ordered), schema reads, summarize."""

    def __init__(self, data):
        self.data = data  # {entity_type: [records]}
        self.fail_on = None

    def schema_field_read(self, entity_type):
        fields = {"id"}
        for record in self.data.get(entity_type, []):
            fields |= set(record)
        return {f: {} for f in fields}

    def schema_entity_read(self):
        return {et: {"name": {"value": et}, "visible": {"value": True}} for et in self.data}

    def summarize(self, entity_type, filters, summary_fields):
        return {"summaries": {"id": len(self.data.get(entity_type, []))}}

    def find(self, entity_type, filters, fields, order=None, limit=0, page=1):
        if entity_type == self.fail_on:
            raise RuntimeError("boom")
        records = sorted(self.data.get(entity_type, []), key=lambda r: r["id"])
        if limit:
            records = records[(page - 1) * limit : page * limit]
        return [{k: v for k, v in r.items() if k in fields} for r in records]


def project(pid, **extra):
    return {"id": pid, "type": "Project", "name": f"Projet {pid}", "sg_status": None,
            "archived": False, "is_template": False, **extra}


def task(tid, pid=1, content="compo"):
    return {"id": tid, "type": "Task", "content": content,
            "project": {"type": "Project", "id": pid, "name": f"Projet {pid}"}}


@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.setattr(
        main, "settings",
        dataclasses.replace(main.settings, database_path=str(tmp_path / "test.sqlite3"),
                            shotgrid_url="https://example.shotgrid.test"),
    )
    monkeypatch.setattr(main, "SYNC_ENTITIES", {"Project": "projects", "Task": "tasks"})
    monkeypatch.setattr(main, "SYNC_PAGE_SIZE", 2)  # force multi-page fetches
    client = FakeShotGrid({"Project": [project(1)], "Task": [task(i) for i in range(1, 6)]})
    monkeypatch.setattr(main, "shotgrid_client", lambda: client)
    return client


def counts(entity_type):
    conn = main.database()
    try:
        records = conn.execute(
            "SELECT COUNT(*) FROM shotgrid_records WHERE entity_type=?", (entity_type,)
        ).fetchone()[0]
        fts = conn.execute(
            "SELECT COUNT(*) FROM shotgrid_fts WHERE entity_type=?", (entity_type,)
        ).fetchone()[0]
        return records, fts
    finally:
        conn.close()


def test_sync_fetches_all_pages(fake):
    result = main.sync_shotgrid()
    assert result["status"] == "completed"
    assert counts("Task") == (5, 5)


def test_repeated_sync_does_not_duplicate_search_index(fake):
    for _ in range(3):
        main.sync_shotgrid()
    assert counts("Task") == (5, 5)
    assert counts("Project") == (1, 1)


def test_records_deleted_in_shotgrid_are_removed(fake):
    main.sync_shotgrid()
    fake.data["Task"] = [t for t in fake.data["Task"] if t["id"] != 3]
    result = main.sync_shotgrid()
    assert result["deleted_count"] == 1
    assert counts("Task") == (4, 4)


def test_empty_answer_does_not_wipe_local_copy(fake):
    main.sync_shotgrid()
    fake.data["Task"] = []
    main.sync_shotgrid()
    assert counts("Task") == (5, 5)


def test_failed_sync_is_recorded_and_does_not_block(fake):
    fake.fail_on = "Task"
    with pytest.raises(RuntimeError):
        main.sync_shotgrid()
    conn = main.database()
    status = conn.execute("SELECT status FROM sync_runs ORDER BY id DESC").fetchone()[0]
    conn.close()
    assert status == "failed"
    fake.fail_on = None
    assert main.sync_shotgrid()["status"] == "completed"


def test_stale_running_sync_is_unblocked(fake):
    conn = main.database()
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    with conn:
        conn.execute("INSERT INTO sync_runs (started_at, status) VALUES (?, 'running')", (old,))
    assert main.start_sync_run(conn) is not None
    conn.close()


def test_recent_running_sync_blocks_a_second_one(fake):
    conn = main.database()
    assert main.start_sync_run(conn) is not None
    assert main.start_sync_run(conn) is None
    conn.close()


@pytest.mark.parametrize(
    "record, expected",
    [
        (project(1), ("Actif", True)),
        (project(1, sg_status="Active"), ("Actif", True)),
        (project(1, sg_status="Done"), ("Terminé", False)),
        (project(1, archived=True, sg_status="Active"), ("Archivé", False)),
        (project(1, is_template=True), ("Template", False)),
    ],
)
def test_project_state(record, expected):
    assert main.project_state(record) == expected


def test_dashboard_and_assistant_agree_on_active_projects(fake):
    fake.data["Project"] = [project(1), project(2, archived=True), project(3, is_template=True)]
    main.sync_shotgrid()
    with TestClient(main.app) as http:
        dashboard = http.get("/api/dashboard").json()
    assert dashboard["projects_active"] == 1
    llm_active = [
        p for p in (main.compact_record_for_llm(r, "Project") for r in dashboard["projects"])
        if p["is_active"]
    ]
    assert len(llm_active) == 1


def test_audit_reports_gaps(fake):
    main.sync_shotgrid()
    fake.data["Task"].append(task(99))
    with TestClient(main.app) as http:
        audit = http.get("/api/sync/audit", params={"include_unsynced": True}).json()
    tasks = next(e for e in audit["entities"] if e["entity_type"] == "Task")
    assert tasks["missing_locally"] == 1 and tasks["missing_ids_sample"] == [99]
    assert audit["in_sync"] is False
    assert audit["search_index"]["healthy"] is True


def test_project_root_is_never_served(fake):
    with TestClient(main.app) as http:
        assert http.get("/.env").status_code == 404
        assert http.get("/dashboard.sqlite3").status_code == 404
