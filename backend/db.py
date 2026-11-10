"""SQLite connection and schema management (versioned with PRAGMA user_version)."""
import json
import sqlite3
from typing import Any, Iterable, Optional

from backend import config
from backend.records import fts_content, iter_links

SCHEMA_VERSION = 2
_initialized: set[str] = set()


def database(visible_projects: Optional[Iterable[int]] = None) -> sqlite3.Connection:
    """Open a connection, creating/migrating the schema the first time a path is used.

    With `visible_projects`, the connection is restricted to what one user may see: a
    TEMP view named `shotgrid_records` shadows the real table for every query made on
    this connection (joins, full-text search and the assistant included). Records of
    other productions simply do not exist for it, and writes through it are refused.
    `None` means unrestricted (sync, admin tasks, users who see everything).
    """
    path = config.settings.database_path
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode = WAL;")
    connection.execute("PRAGMA foreign_keys = OFF;")
    if path not in _initialized:
        ensure_schema(connection)
        _initialized.add(path)
    if visible_projects is not None:
        ids = ",".join(str(int(p)) for p in sorted(set(visible_projects))) or "NULL"
        connection.execute(
            "CREATE TEMP VIEW shotgrid_records AS SELECT rowid AS rowid, * FROM main.shotgrid_records "
            f"WHERE project_id IS NULL OR project_id IN ({ids})"
        )
    return connection


def _create_base_tables(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS shotgrid_records (
            entity_type TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            name TEXT,
            project_id INTEGER,
            status TEXT,
            data_json TEXT NOT NULL,
            synced_at TEXT NOT NULL,
            PRIMARY KEY (entity_type, entity_id)
        );
        CREATE INDEX IF NOT EXISTS idx_records_type_project ON shotgrid_records(entity_type, project_id);
        CREATE INDEX IF NOT EXISTS idx_records_type_name ON shotgrid_records(entity_type, name COLLATE NOCASE);
        CREATE INDEX IF NOT EXISTS idx_records_project ON shotgrid_records(project_id);
        CREATE INDEX IF NOT EXISTS idx_records_status ON shotgrid_records(status);

        CREATE TABLE IF NOT EXISTS sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            records_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            error TEXT
        );

        -- Every entity link found in a record (task -> step, shot -> sequence, ...).
        CREATE TABLE IF NOT EXISTS shotgrid_links (
            src_type TEXT NOT NULL,
            src_id INTEGER NOT NULL,
            field TEXT NOT NULL,
            dst_type TEXT NOT NULL,
            dst_id INTEGER NOT NULL,
            PRIMARY KEY (src_type, src_id, field, dst_type, dst_id)
        ) WITHOUT ROWID;
        CREATE INDEX IF NOT EXISTS idx_links_dst ON shotgrid_links(dst_type, dst_id, field, src_type);

        -- Which entity types are synced, their display name and sync watermarks.
        CREATE TABLE IF NOT EXISTS entity_types (
            entity_type TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            record_count INTEGER NOT NULL DEFAULT 0,
            last_synced_at TEXT,
            last_full_sync_at TEXT
        );

        -- Signed-in sessions (the cookie only holds the random key).
        CREATE TABLE IF NOT EXISTS user_sessions (
            session_key TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );

        -- Google OAuth tokens kept server-side; the session cookie only holds a random key.
        CREATE TABLE IF NOT EXISTS user_tokens (
            session_key TEXT PRIMARY KEY,
            token_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    columns = {row[1] for row in connection.execute("PRAGMA table_info(sync_runs)")}
    if "mode" not in columns:
        connection.execute("ALTER TABLE sync_runs ADD COLUMN mode TEXT NOT NULL DEFAULT 'full'")


def _create_fts(connection: sqlite3.Connection) -> None:
    # rowid of each FTS row == rowid of its shotgrid_records row, so updates and
    # deletes are O(1) instead of a table scan.
    connection.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS shotgrid_fts USING fts5(
            entity_type UNINDEXED,
            name,
            content,
            tokenize='unicode61 remove_diacritics 2'
        )
        """
    )


def rebuild_derived(connection: sqlite3.Connection, entity_types: Iterable[str] | None = None) -> None:
    """Recompute FTS rows and links from shotgrid_records (all types, or the given ones)."""
    if entity_types is None:
        connection.execute("DELETE FROM shotgrid_fts")
        connection.execute("DELETE FROM shotgrid_links")
        rows = connection.execute(
            "SELECT rowid, entity_type, entity_id, name, data_json FROM shotgrid_records"
        )
    else:
        types = list(entity_types)
        marks = ",".join("?" * len(types))
        connection.execute(f"DELETE FROM shotgrid_fts WHERE entity_type IN ({marks})", types)
        connection.execute(f"DELETE FROM shotgrid_links WHERE src_type IN ({marks})", types)
        rows = connection.execute(
            f"SELECT rowid, entity_type, entity_id, name, data_json FROM shotgrid_records "
            f"WHERE entity_type IN ({marks})",
            types,
        )
    fts_rows: list[tuple] = []
    link_rows: list[tuple] = []
    for row in rows.fetchall():
        record: dict[str, Any] = json.loads(row["data_json"])
        fts_rows.append((row["rowid"], row["entity_type"], row["name"] or "", fts_content(record)))
        link_rows.extend(
            (row["entity_type"], row["entity_id"], f, t, i) for f, t, i in iter_links(record)
        )
    connection.executemany(
        "INSERT INTO shotgrid_fts (rowid, entity_type, name, content) VALUES (?, ?, ?, ?)", fts_rows
    )
    connection.executemany("INSERT OR IGNORE INTO shotgrid_links VALUES (?, ?, ?, ?, ?)", link_rows)


def ensure_schema(connection: sqlite3.Connection) -> None:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    with connection:
        _create_base_tables(connection)
        if version < 2:
            # v1 FTS had no rowid mapping and could hold duplicates: rebuild it.
            connection.execute("DROP TABLE IF EXISTS shotgrid_fts")
            _create_fts(connection)
            rebuild_derived(connection)
            connection.execute(
                """
                INSERT OR IGNORE INTO entity_types (entity_type, display_name, record_count)
                SELECT entity_type, entity_type, COUNT(*) FROM shotgrid_records GROUP BY entity_type
                """
            )
        else:
            _create_fts(connection)
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
