"""ShotGrid -> SQLite synchronisation: full and incremental syncs, scheduler and audit."""
import asyncio
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException

from backend import config, shotgrid
from backend.config import log
from backend.db import database, rebuild_derived
from backend.records import fts_content, iter_links, record_row

SYNC_PAGE_SIZE = 500
# A run still marked "running" after this long is considered dead (server crash/restart).
SYNC_STALE_AFTER = timedelta(minutes=30)
# Margin applied to the incremental watermark to absorb clock skew with ShotGrid.
WATERMARK_MARGIN = timedelta(minutes=5)

# ShotGrid bookkeeping types with no production value (or huge and useless here).
SYSTEM_ENTITY_TYPES = {
    "EventLogEntry", "PageHit", "PageSetting", "Page", "Icon", "PermissionRuleSet", "ApiUser", "WorkDayRule", "Banner", "AppWelcome", "FilesystemLocation",
    "PipelineConfiguration", "ApiUserProjectConnection", "PageSettingConnection",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_syncable_type(entity_type: str, info: dict[str, Any]) -> bool:
    return (
        entity_type not in SYSTEM_ENTITY_TYPES
        and not entity_type.endswith("Connection")
        and info.get("visible", {}).get("value", True)
    )


def count_live(client, entity_type: str) -> Optional[int]:
    try:
        return client.summarize(entity_type, [], [{"field": "id", "type": "count"}])["summaries"]["id"]
    except Exception:
        return None


def discover_entity_types(client) -> dict[str, str]:
    """Entity types to sync -> display name. Driven by the SYNC_ENTITIES setting."""
    schema = client.schema_entity_read()
    wanted = config.settings.sync_entities.strip()
    if wanted and wanted.casefold() != "auto":
        names = [n.strip() for n in wanted.split(",") if n.strip()]
        return {n: schema.get(n, {}).get("name", {}).get("value", n) for n in names}
    found = {}
    for entity_type, info in schema.items():
        if is_syncable_type(entity_type, info) and count_live(client, entity_type):
            found[entity_type] = info.get("name", {}).get("value", entity_type)
    # Projects first so their rows exist before anything links to them.
    return dict(sorted(found.items(), key=lambda kv: (kv[0] != "Project", kv[0])))


def fetch_records(client, entity_type: str, fields: list[str], filters: list | None = None) -> list[dict]:
    """Fetch every matching record, paging in a stable id order so none is skipped."""
    records: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = client.find(
            entity_type,
            filters or [],
            fields,
            order=[{"field_name": "id", "direction": "asc"}],
            limit=SYNC_PAGE_SIZE,
            page=page,
        )
        records.extend(batch)
        if len(batch) < SYNC_PAGE_SIZE:
            return records
        page += 1


UPSERT_SQL = """
    INSERT INTO shotgrid_records
        (entity_type, entity_id, name, project_id, status, data_json, synced_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(entity_type, entity_id) DO UPDATE SET
        name=excluded.name,
        project_id=excluded.project_id,
        status=excluded.status,
        data_json=excluded.data_json,
        synced_at=excluded.synced_at
"""


def _delete_records(connection: sqlite3.Connection, entity_type: str, ids: list[int]) -> None:
    for entity_id in ids:
        row = connection.execute(
            "SELECT rowid FROM shotgrid_records WHERE entity_type=? AND entity_id=?",
            (entity_type, entity_id),
        ).fetchone()
        if not row:
            continue
        connection.execute("DELETE FROM shotgrid_fts WHERE rowid=?", (row[0],))
        connection.execute(
            "DELETE FROM shotgrid_links WHERE src_type=? AND src_id=?", (entity_type, entity_id)
        )
        connection.execute("DELETE FROM shotgrid_records WHERE rowid=?", (row[0],))


def _update_entity_type(
    connection: sqlite3.Connection, entity_type: str, display: str, synced_at: str, full: bool
) -> None:
    count = connection.execute(
        "SELECT COUNT(*) FROM shotgrid_records WHERE entity_type=?", (entity_type,)
    ).fetchone()[0]
    connection.execute(
        """
        INSERT INTO entity_types (entity_type, display_name, record_count, last_synced_at, last_full_sync_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(entity_type) DO UPDATE SET
            display_name=excluded.display_name,
            record_count=excluded.record_count,
            last_synced_at=excluded.last_synced_at,
            last_full_sync_at=COALESCE(excluded.last_full_sync_at, entity_types.last_full_sync_at)
        """,
        (entity_type, display, count, synced_at, synced_at if full else None),
    )


def store_full(
    connection: sqlite3.Connection,
    entity_type: str,
    records: list[dict[str, Any]],
    display: str = "",
    started_at: Optional[str] = None,
) -> dict[str, int]:
    """Replace the local copy of one entity type with `records`, in a single transaction."""
    now = utc_now()
    live_ids = {r["id"] for r in records}
    local_ids = {
        row[0]
        for row in connection.execute(
            "SELECT entity_id FROM shotgrid_records WHERE entity_type=?", (entity_type,)
        )
    }
    # Safety net: an empty answer while we hold data is far more likely a permission or
    # API problem than a real mass deletion, so keep the local copy in that case.
    stale_ids = sorted(local_ids - live_ids) if live_ids else []
    with connection:
        _delete_records(connection, entity_type, stale_ids)
        connection.executemany(UPSERT_SQL, [record_row(entity_type, r, now) for r in records])
        if live_ids:
            rebuild_derived(connection, [entity_type])
        _update_entity_type(connection, entity_type, display or entity_type, started_at or now, True)
    return {"upserted": len(records), "deleted": len(stale_ids)}


def store_incremental(
    connection: sqlite3.Connection,
    entity_type: str,
    changed: list[dict[str, Any]],
    retired_ids: list[int],
    display: str = "",
    started_at: Optional[str] = None,
) -> dict[str, int]:
    """Apply changed and retired records of one type, updating FTS rows and links in place."""
    now = utc_now()
    with connection:
        _delete_records(connection, entity_type, retired_ids)
        connection.executemany(UPSERT_SQL, [record_row(entity_type, r, now) for r in changed])
        for record in changed:
            rowid = connection.execute(
                "SELECT rowid FROM shotgrid_records WHERE entity_type=? AND entity_id=?",
                (entity_type, record["id"]),
            ).fetchone()[0]
            connection.execute("DELETE FROM shotgrid_fts WHERE rowid=?", (rowid,))
            connection.execute(
                "INSERT INTO shotgrid_fts (rowid, entity_type, name, content) VALUES (?, ?, ?, ?)",
                (rowid, entity_type, record_row(entity_type, record, now)[2] or "", fts_content(record)),
            )
            connection.execute(
                "DELETE FROM shotgrid_links WHERE src_type=? AND src_id=?", (entity_type, record["id"])
            )
            connection.executemany(
                "INSERT OR IGNORE INTO shotgrid_links VALUES (?, ?, ?, ?, ?)",
                [(entity_type, record["id"], f, t, i) for f, t, i in iter_links(record)],
            )
        _update_entity_type(connection, entity_type, display or entity_type, started_at or now, False)
    return {"upserted": len(changed), "deleted": len(retired_ids)}


def retired_since(client, since: datetime) -> dict[str, list[int]]:
    """Records retired (deleted) in ShotGrid since `since`, read from the event log."""
    retired: dict[str, list[int]] = {}
    try:
        events = client.find(
            "EventLogEntry",
            [["event_type", "ends_with", "_Retirement"], ["created_at", "greater_than", since]],
            ["meta"],
        )
    except Exception as exc:  # no permission on the event log: the next full sync catches up
        log.warning("Lecture du journal ShotGrid impossible : %s", exc)
        return retired
    for event in events:
        meta = event.get("meta") or {}
        if meta.get("entity_type") and isinstance(meta.get("entity_id"), int):
            retired.setdefault(meta["entity_type"], []).append(meta["entity_id"])
    return retired


def fail_stale_sync_runs(connection: sqlite3.Connection, older_than: Optional[timedelta]) -> int:
    """Mark leftover 'running' sync runs as failed so they stop blocking new syncs.

    `older_than=None` fails every running run (used at startup, when none can be alive).
    """
    params: list[Any] = [utc_now(), "Synchronisation interrompue (serveur arrêté ou bloqué)"]
    where = "status='running'"
    if older_than is not None:
        where += " AND started_at < ?"
        params.append((datetime.now(timezone.utc) - older_than).isoformat())
    with connection:
        cursor = connection.execute(
            f"UPDATE sync_runs SET status='failed', finished_at=?, error=? WHERE {where}", params
        )
    return cursor.rowcount


def start_sync_run(connection: sqlite3.Connection, mode: str = "full") -> Optional[int]:
    """Create a 'running' sync run, or return None if another one is genuinely in progress."""
    fail_stale_sync_runs(connection, SYNC_STALE_AFTER)
    with connection:
        if connection.execute("SELECT 1 FROM sync_runs WHERE status='running' LIMIT 1").fetchone():
            return None
        return connection.execute(
            "INSERT INTO sync_runs (started_at, status, mode) VALUES (?, 'running', ?)",
            (utc_now(), mode),
        ).lastrowid


def resolve_mode(connection: sqlite3.Connection, mode: str) -> str:
    """'auto' -> 'full' when no recent full sync exists, else 'incremental'."""
    if mode != "auto":
        return mode
    row = connection.execute(
        "SELECT MIN(last_full_sync_at), MIN(last_synced_at), COUNT(*) FROM entity_types"
    ).fetchone()
    if not row[2] or not row[0] or not row[1]:
        return "full"
    last_full = datetime.fromisoformat(row[0])
    if datetime.now(timezone.utc) - last_full > timedelta(hours=config.settings.full_sync_every_hours):
        return "full"
    return "incremental"


def sync_shotgrid(run_id: Optional[int] = None, mode: str = "full") -> dict[str, Any]:
    connection = database()
    if run_id is None:
        run_id = start_sync_run(connection, mode)
        if run_id is None:
            connection.close()
            raise RuntimeError("Une synchronisation est déjà en cours")
    started_at = connection.execute(
        "SELECT started_at FROM sync_runs WHERE id=?", (run_id,)
    ).fetchone()[0]
    total = deleted = 0
    try:
        mode = resolve_mode(connection, mode)
        with connection:
            connection.execute("UPDATE sync_runs SET mode=? WHERE id=?", (mode, run_id))
        client = shotgrid.shotgrid_client()

        if mode == "full":
            types = discover_entity_types(client)
        else:
            types = {
                row["entity_type"]: row["display_name"]
                for row in connection.execute("SELECT entity_type, display_name FROM entity_types")
            }
            watermark_row = connection.execute("SELECT MIN(last_synced_at) FROM entity_types").fetchone()
            since = datetime.fromisoformat(watermark_row[0]) - WATERMARK_MARGIN
            retired = retired_since(client, since)

        for entity_type, display in types.items():
            schema_fields = client.schema_field_read(entity_type)
            fields = list(schema_fields)
            if "id" not in fields:
                fields.insert(0, "id")
            if mode == "full" or "updated_at" not in schema_fields:
                records = fetch_records(client, entity_type, fields)
                stats = store_full(connection, entity_type, records, display, started_at)
            else:
                type_since = connection.execute(
                    "SELECT last_synced_at FROM entity_types WHERE entity_type=?", (entity_type,)
                ).fetchone()[0]
                since_dt = datetime.fromisoformat(type_since) - WATERMARK_MARGIN
                changed = fetch_records(
                    client, entity_type, fields, [["updated_at", "greater_than", since_dt]]
                )
                stats = store_incremental(
                    connection, entity_type, changed, retired.get(entity_type, []), display, started_at
                )
            total += stats["upserted"]
            deleted += stats["deleted"]
            with connection:
                connection.execute("UPDATE sync_runs SET records_count=? WHERE id=?", (total, run_id))

        if mode == "full":
            # Types no longer synced (removed from SYNC_ENTITIES or emptied) are dropped.
            gone = [
                row[0] for row in connection.execute("SELECT entity_type FROM entity_types")
                if row[0] not in types
            ]
            with connection:
                for entity_type in gone:
                    ids = [r[0] for r in connection.execute(
                        "SELECT entity_id FROM shotgrid_records WHERE entity_type=?", (entity_type,)
                    )]
                    _delete_records(connection, entity_type, ids)
                    connection.execute("DELETE FROM entity_types WHERE entity_type=?", (entity_type,))

        finished = utc_now()
        with connection:
            connection.execute(
                "UPDATE sync_runs SET finished_at=?, records_count=?, status='completed' WHERE id=?",
                (finished, total, run_id),
            )
        return {
            "status": "completed",
            "mode": mode,
            "records_count": total,
            "deleted_count": deleted,
            "finished_at": finished,
        }
    except Exception as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        with connection:
            connection.execute(
                "UPDATE sync_runs SET finished_at=?, records_count=?, status='failed', error=? WHERE id=?",
                (utc_now(), total, detail, run_id),
            )
        raise
    finally:
        connection.close()


async def scheduler_loop() -> None:
    """Run an 'auto' sync every SYNC_INTERVAL_MINUTES (first one shortly after startup)."""
    interval = config.settings.sync_interval_minutes
    if interval <= 0:
        return
    await asyncio.sleep(15)
    while True:
        try:
            connection = database()
            try:
                run_id = start_sync_run(connection, "auto")
            finally:
                connection.close()
            if run_id is not None:
                result = await asyncio.to_thread(sync_shotgrid, run_id, "auto")
                log.info("Synchronisation planifiée : %s", result)
        except Exception as exc:
            log.warning("Synchronisation planifiée échouée : %s", exc)
        await asyncio.sleep(interval * 60)


def audit_shotgrid(include_unsynced: bool = False) -> dict[str, Any]:
    """Compare live ShotGrid with the local cache (read-only on both sides)."""
    client = shotgrid.shotgrid_client()
    connection = database()
    try:
        synced = {
            row["entity_type"]: row["display_name"]
            for row in connection.execute("SELECT entity_type, display_name FROM entity_types ORDER BY entity_type")
        }
        entities = []
        for entity_type, display in synced.items():
            live_ids = {r["id"] for r in client.find(entity_type, [], ["id"])}
            local_ids = {
                row[0]
                for row in connection.execute(
                    "SELECT entity_id FROM shotgrid_records WHERE entity_type=?", (entity_type,)
                )
            }
            sample = connection.execute(
                "SELECT data_json FROM shotgrid_records WHERE entity_type=? LIMIT 1", (entity_type,)
            ).fetchone()
            stored_fields = set(json.loads(sample["data_json"])) if sample else set()
            schema_fields = set(client.schema_field_read(entity_type))
            missing = sorted(live_ids - local_ids)
            deleted = sorted(local_ids - live_ids)
            entities.append({
                "entity_type": entity_type,
                "display_name": display,
                "live": len(live_ids),
                "local": len(local_ids),
                "missing_locally": len(missing),
                "deleted_in_shotgrid": len(deleted),
                "missing_ids_sample": missing[:20],
                "deleted_ids_sample": deleted[:20],
                "fields_not_stored": sorted(schema_fields - stored_fields) if sample else [],
                "in_sync": not missing and not deleted,
            })

        records_count = connection.execute("SELECT COUNT(*) FROM shotgrid_records").fetchone()[0]
        fts_count = connection.execute("SELECT COUNT(*) FROM shotgrid_fts").fetchone()[0]

        unsynced = None
        if include_unsynced:
            unsynced = []
            for entity_type, info in client.schema_entity_read().items():
                if entity_type in synced or not is_syncable_type(entity_type, info):
                    continue
                count = count_live(client, entity_type)
                if count:
                    unsynced.append({
                        "entity_type": entity_type,
                        "display_name": info.get("name", {}).get("value", entity_type),
                        "live": count,
                    })
            unsynced.sort(key=lambda e: -e["live"])

        return {
            "in_sync": all(e["in_sync"] for e in entities) and fts_count == records_count,
            "entities": entities,
            "search_index": {"records": records_count, "fts_rows": fts_count,
                             "healthy": fts_count == records_count},
            "unsynced_entity_types": unsynced,
        }
    finally:
        connection.close()
