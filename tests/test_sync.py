"""Sync: full & incremental, entity discovery, links, safety nets, run bookkeeping, migration."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from backend import db, sync
from backend.records import project_state
from tests.conftest import later, task


def counts(entity_type):
    conn = db.database()
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


def synced_types():
    conn = db.database()
    try:
        return {r[0]: r[1] for r in conn.execute("SELECT entity_type, display_name FROM entity_types")}
    finally:
        conn.close()


def test_full_sync_fetches_all_pages(fake):
    result = sync.sync_shotgrid(mode="full")
    assert result["status"] == "completed" and result["mode"] == "full"
    assert counts("Task") == (5, 5)


def test_auto_discovery_skips_system_connection_and_empty_types(fake):
    sync.sync_shotgrid(mode="full")
    types = synced_types()
    assert {"Project", "Sequence", "Shot", "Step", "HumanUser", "Task", "Note"} <= set(types)
    assert "AssetShotConnection" not in types
    assert "EventLogEntry" not in types
    assert "Playlist" not in types
    assert types["Sequence"] == "Sequence label"


def test_explicit_entity_list(fake, monkeypatch):
    import dataclasses
    from backend import config
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, sync_entities="Project,Task"))
    sync.sync_shotgrid(mode="full")
    assert set(synced_types()) == {"Project", "Task"}


def test_links_are_extracted(fake):
    sync.sync_shotgrid(mode="full")
    conn = db.database()
    links = {tuple(r) for r in conn.execute(
        "SELECT field, dst_type, dst_id FROM shotgrid_links WHERE src_type='Task' AND src_id=100"
    )}
    conn.close()
    assert ("step", "Step", 30) in links
    assert ("entity", "Shot", 20) in links
    assert ("task_assignees", "HumanUser", 40) in links
    assert ("upstream_tasks", "Task", 101) in links


def test_repeated_sync_does_not_duplicate_search_index(fake):
    for _ in range(3):
        sync.sync_shotgrid(mode="full")
    assert counts("Task") == (5, 5)


def test_records_deleted_in_shotgrid_are_removed_by_full_sync(fake):
    sync.sync_shotgrid(mode="full")
    fake.data["Task"] = [t for t in fake.data["Task"] if t["id"] != 103]
    result = sync.sync_shotgrid(mode="full")
    assert result["deleted_count"] == 1
    assert counts("Task") == (4, 4)


def test_empty_answer_does_not_wipe_local_copy(fake, monkeypatch):
    import dataclasses
    from backend import config
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, sync_entities="Project,Task"))
    sync.sync_shotgrid(mode="full")
    fake.data["Task"] = []
    sync.sync_shotgrid(mode="full")
    assert counts("Task") == (5, 5)


def test_incremental_sync_applies_changes_and_retirements(fake):
    sync.sync_shotgrid(mode="full")
    calls_before = len(fake.find_calls)
    changed = next(t for t in fake.data["Task"] if t["id"] == 101)
    changed.update(content="anim sh020 v2", sg_status_list="ip", updated_at=later())
    fake.data["Task"].append({**task(105, "new task"), "updated_at": later()})
    fake.data["Task"] = [t for t in fake.data["Task"] if t["id"] != 103]
    fake.data["EventLogEntry"] = [{
        "id": 1, "type": "EventLogEntry", "event_type": "Shotgun_Task_Retirement", "created_at": later(),
        "meta": {"entity_type": "Task", "entity_id": 103, "type": "entity_retirement"},
    }]

    result = sync.sync_shotgrid(mode="incremental")
    assert result["mode"] == "incremental"
    assert result["records_count"] == 2  # only the two changed tasks were fetched
    assert counts("Task") == (5, 5)

    conn = db.database()
    row = conn.execute("SELECT name, status FROM shotgrid_records WHERE entity_type='Task' AND entity_id=101").fetchone()
    hit = conn.execute(
        "SELECT r.entity_id FROM shotgrid_fts f JOIN shotgrid_records r ON r.rowid=f.rowid "
        "WHERE shotgrid_fts MATCH 'v2'"
    ).fetchall()
    gone = conn.execute("SELECT COUNT(*) FROM shotgrid_records WHERE entity_type='Task' AND entity_id=103").fetchone()[0]
    conn.close()
    assert tuple(row) == ("anim sh020 v2", "ip")
    assert [h[0] for h in hit] == [101]
    assert gone == 0
    # Incremental queries are filtered on updated_at, not full scans.
    task_calls = [f for et, f in fake.find_calls[calls_before:] if et == "Task"]
    assert task_calls and all(f and f[0][0] == "updated_at" for f in task_calls)


def test_auto_mode_picks_full_then_incremental(fake):
    assert sync.sync_shotgrid(mode="auto")["mode"] == "full"
    assert sync.sync_shotgrid(mode="auto")["mode"] == "incremental"


def test_failed_sync_is_recorded_and_does_not_block(fake):
    fake.fail_on = "Task"
    with pytest.raises(RuntimeError):
        sync.sync_shotgrid(mode="full")
    conn = db.database()
    status = conn.execute("SELECT status FROM sync_runs ORDER BY id DESC").fetchone()[0]
    conn.close()
    assert status == "failed"
    fake.fail_on = None
    assert sync.sync_shotgrid(mode="full")["status"] == "completed"


def test_stale_running_sync_is_unblocked(fake):
    conn = db.database()
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    with conn:
        conn.execute("INSERT INTO sync_runs (started_at, status) VALUES (?, 'running')", (old,))
    assert sync.start_sync_run(conn) is not None
    conn.close()


def test_recent_running_sync_blocks_a_second_one(fake):
    conn = db.database()
    assert sync.start_sync_run(conn) is not None
    assert sync.start_sync_run(conn) is None
    conn.close()


def test_audit_reports_gaps(fake):
    sync.sync_shotgrid(mode="full")
    fake.data["Task"].append(task(99, "missing"))
    audit = sync.audit_shotgrid(include_unsynced=True)
    tasks = next(e for e in audit["entities"] if e["entity_type"] == "Task")
    assert tasks["missing_locally"] == 1 and tasks["missing_ids_sample"] == [99]
    assert audit["in_sync"] is False
    assert audit["search_index"]["healthy"] is True
    assert audit["unsynced_entity_types"] == []


def test_v1_database_is_migrated(fake, tmp_path):
    """An old database (duplicated FTS rows, no links) is upgraded on first connection."""
    from backend import config
    path = config.settings.database_path
    old = sqlite3.connect(path)
    old.executescript(
        """
        CREATE TABLE shotgrid_records (entity_type TEXT NOT NULL, entity_id INTEGER NOT NULL, name TEXT,
            project_id INTEGER, status TEXT, data_json TEXT NOT NULL, synced_at TEXT NOT NULL,
            PRIMARY KEY (entity_type, entity_id));
        CREATE TABLE sync_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL,
            finished_at TEXT, records_count INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL, error TEXT);
        CREATE VIRTUAL TABLE shotgrid_fts USING fts5(entity_type, entity_id UNINDEXED, project_id UNINDEXED,
            name, content);
        """
    )
    record = {"id": 7, "type": "Task", "content": "roto", "step": {"type": "Step", "id": 30, "name": "Roto"}}
    old.execute("INSERT INTO shotgrid_records VALUES ('Task', 7, 'roto', 1, 'ip', ?, 'x')", (json.dumps(record),))
    old.executemany("INSERT INTO shotgrid_fts VALUES ('Task', 7, 1, 'roto', '')", [(), ()])
    old.commit()
    old.close()
    db._initialized.discard(path)

    conn = db.database()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    assert conn.execute("SELECT COUNT(*) FROM shotgrid_fts").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM shotgrid_links WHERE src_id=7").fetchone()[0] == 1
    assert "mode" in {r[1] for r in conn.execute("PRAGMA table_info(sync_runs)")}
    conn.close()


@pytest.mark.parametrize(
    "record, expected",
    [
        ({"sg_status": None}, ("Actif", True)),
        ({"sg_status": "Active"}, ("Actif", True)),
        ({"sg_status": "Done"}, ("Terminé", False)),
        ({"archived": True, "sg_status": "Active"}, ("Archivé", False)),
        ({"is_template": True}, ("Template", False)),
    ],
)
def test_project_state(record, expected):
    assert project_state(record) == expected
