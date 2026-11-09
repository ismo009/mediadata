import asyncio
import json
import os
import re
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

import httpx
from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

SYNC_ENTITIES = {
    "Project": "projects",
    "Shot": "shots",
    "Task": "tasks",
    "Asset": "assets",
    "Version": "versions",
    "HumanUser": "users",
    "Note": "notes",
}


class ChatMessage(BaseModel):
    role: str = "user"
    content: str = ""

    class Config:
        extra = "ignore"


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[dict[str, Any]] = Field(default_factory=list, max_length=30)
    model: Optional[str] = None


@dataclass(frozen=True)
class Settings:
    app_secret: str = os.getenv("APP_SECRET", "")
    app_base_url: str = os.getenv("APP_BASE_URL", "http://localhost:8000")
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "")
    shotgrid_url: str = os.getenv("SHOTGRID_SERVER_URL", "").rstrip("/")
    shotgrid_login: str = os.getenv("SHOTGRID_LOGIN", "")
    shotgrid_passphrase: str = os.getenv("SHOTGRID_PASSPHRASE", "")
    shotgrid_pat: str = os.getenv("SHOTGRID_PAT", "")
    shotgrid_script_name: str = os.getenv("SHOTGRID_SCRIPT_NAME", "")
    shotgrid_script_key: str = os.getenv("SHOTGRID_SCRIPT_KEY", "")
    database_path: str = os.getenv(
        "DATABASE_PATH", str(PROJECT_ROOT / "dashboard.sqlite3")
    )


settings = Settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # A sync cannot survive a server restart, so any run still "running" is dead.
    connection = database()
    try:
        fail_stale_sync_runs(connection, older_than=None)
    finally:
        connection.close()
    yield


app = FastAPI(title="MedIAData Dashboard API", lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.app_secret or "development-only-change-me",
    same_site="lax",
    https_only=settings.app_base_url.startswith("https://"),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.app_base_url,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth = OAuth()
oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    client_kwargs={"scope": "openid email profile https://www.googleapis.com/auth/drive.readonly"},
)


def database() -> sqlite3.Connection:
    connection = sqlite3.connect(settings.database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode = WAL;")

    connection.execute(
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
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            records_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            error TEXT
        )
        """
    )
    # Ensure indexes exist
    connection.execute("CREATE INDEX IF NOT EXISTS idx_records_type_project ON shotgrid_records(entity_type, project_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_records_type_name ON shotgrid_records(entity_type, name COLLATE NOCASE)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_records_project ON shotgrid_records(project_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_records_status ON shotgrid_records(status)")

    # Ensure FTS5 exists
    connection.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS shotgrid_fts USING fts5(
            entity_type,
            entity_id UNINDEXED,
            project_id UNINDEXED,
            name,
            content,
            tokenize='unicode61 remove_diacritics 2'
        )
        """
    )
    connection.commit()
    return connection


def shotgrid_client():
    if not settings.shotgrid_url:
        raise HTTPException(status_code=503, detail="ShotGrid URL non configurée")
    import shotgun_api3

    if settings.shotgrid_login and settings.shotgrid_passphrase:
        return shotgun_api3.Shotgun(
            settings.shotgrid_url,
            login=settings.shotgrid_login,
            password=settings.shotgrid_passphrase,
        )
    if settings.shotgrid_script_name and settings.shotgrid_script_key:
        return shotgun_api3.Shotgun(
            settings.shotgrid_url,
            script_name=settings.shotgrid_script_name,
            api_key=settings.shotgrid_script_key,
        )
    raise HTTPException(status_code=503, detail="Identifiants ShotGrid non configurés")


# Project sg_status values (lower-cased) that mean the project is no longer in production.
INACTIVE_PROJECT_STATUSES = {"done", "lost", "bidding"}
PROJECT_STATUS_LABELS = {
    "active": "Actif",
    "act": "Actif",
    "bidding": "Appel d'offres",
    "demo/test": "Démo / Test",
    "lost": "Perdu",
    "done": "Terminé",
}


def project_state(record: dict[str, Any]) -> tuple[str, bool]:
    """Single source of truth for a project's status label and whether it counts as active.

    Mirrors ShotGrid's own "Active Projects" notion: archived projects and templates are
    never active; otherwise the optional sg_status field decides, and an empty sg_status
    (the norm on this site) means the project is active.
    """
    if record.get("archived"):
        return "Archivé", False
    if record.get("is_template"):
        return "Template", False
    raw = (record.get("sg_status") or "").strip()
    if not raw:
        return "Actif", True
    key = raw.casefold()
    return PROJECT_STATUS_LABELS.get(key, raw), key not in INACTIVE_PROJECT_STATUSES


def with_source_url(record: dict[str, Any], entity_type=None) -> dict[str, Any]:
    result = dict(record)
    record_type = entity_type or result.get("type")
    if record_type and result.get("id") and settings.shotgrid_url:
        result["source_url"] = f"{settings.shotgrid_url}/detail/{record_type}/{result['id']}"
    if record_type == "Project":
        result["status_label"], result["is_active"] = project_state(result)
    return result


def cached_records(
    entity_type: str,
    page: int = 1,
    limit: int = 50,
    search: Optional[str] = None,
    status: Optional[str] = None,
    project_id: Optional[int] = None,
) -> dict[str, Any]:
    offset = (page - 1) * limit
    clauses = ["entity_type = ?"]
    params: list[Any] = [entity_type]

    if project_id:
        clauses.append("project_id = ?")
        params.append(project_id)

    if status:
        clauses.append("status = ?")
        params.append(status)

    if search and search.strip():
        clauses.append("(name LIKE ? OR data_json LIKE ?)")
        pattern = f"%{search.strip()}%"
        params.extend([pattern, pattern])

    where_sql = " AND ".join(clauses)

    connection = database()
    count_row = connection.execute(
        f"SELECT COUNT(*) AS total FROM shotgrid_records WHERE {where_sql}",
        params,
    ).fetchone()
    total = count_row["total"] if count_row else 0

    query_params = list(params) + [limit, offset]
    rows = connection.execute(
        f"""
        SELECT entity_type, entity_id, project_id, status, name, data_json
        FROM shotgrid_records
        WHERE {where_sql}
        ORDER BY name COLLATE NOCASE
        LIMIT ? OFFSET ?
        """,
        query_params,
    ).fetchall()
    connection.close()

    records = [with_source_url(json.loads(row["data_json"]), entity_type) for row in rows]
    return {
        "records": records,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if limit else 1,
    }


STOP_WORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "en", "au", "aux",
    "et", "ou", "qui", "que", "quoi", "dont", "est", "sont", "a", "ont", "ce", "ces", "cet",
    "cette", "quels", "quelles", "quel", "quelle", "comment", "pourquoi", "pour", "dans",
    "sur", "avec", "sans", "sous", "par", "actuel", "actuels", "actuelle", "actuellement",
    "projet", "projets", "donne", "moi", "affiche", "trouve", "faire", "tous", "toutes",
    "peux", "faire", "voir", "liste", "combien", "the", "a", "an", "and", "or", "is",
    "are", "of", "to", "in", "on", "with", "for", "about", "all"
}


def search_cached(question: str, limit: int = 75) -> list[dict[str, Any]]:
    connection = database()
    clean_q = question.strip()
    lowered = clean_q.casefold()

    # 1. Exact Note lookup: "note #1234"
    note_id = re.search(r"\bnote\s*#?\s*(\d+)\b", clean_q, re.IGNORECASE)
    if note_id:
        row = connection.execute(
            "SELECT entity_type, data_json FROM shotgrid_records WHERE entity_type='Note' AND entity_id=?",
            (int(note_id.group(1)),),
        ).fetchone()
        if row:
            connection.close()
            return [{
                "entity_type": row["entity_type"],
                **with_source_url(json.loads(row["data_json"]), row["entity_type"]),
            }]

    # 2. General Project Question: "Quels sont les projets actifs ?", "liste des projets", etc.
    # When asking about projects as a collection (and not targeting a specific single project name)
    is_general_project_query = bool(
        re.search(r"\b(projets?|projects?)\b", lowered)
        and not re.search(r"\b(projet|project)\s+[A-Za-z0-9_]{3,}", lowered)
    )

    if is_general_project_query:
        # Return ALL projects so none are omitted
        project_rows = connection.execute(
            """
            SELECT entity_type, data_json FROM shotgrid_records
            WHERE entity_type = 'Project'
            ORDER BY name COLLATE NOCASE
            """
        ).fetchall()
        connection.close()
        return [
            {
                "entity_type": "Project",
                **with_source_url(json.loads(row["data_json"]), "Project"),
            }
            for row in project_rows
        ]

    # 3. Targeted Project Name Lookup in question (e.g. "sur le projet Entre les murs", "Devant les Projecteurs")
    project_rows = connection.execute(
        "SELECT entity_id, name, data_json FROM shotgrid_records WHERE entity_type='Project' AND name IS NOT NULL ORDER BY length(name) DESC"
    ).fetchall()
    matched_project = next(
        (row for row in project_rows if row["name"] and row["name"].casefold() in lowered),
        None,
    )

    if matched_project:
        project_id = matched_project["entity_id"]
        requested_type = None
        if re.search(r"\b(tâche|taches|tasks?)\b", lowered):
            requested_type = "Task"
        elif re.search(r"\b(shot|shots|plan|plans)\b", lowered):
            requested_type = "Shot"
        elif re.search(r"\b(note|notes)\b", lowered):
            requested_type = "Note"
        elif re.search(r"\b(asset|assets)\b", lowered):
            requested_type = "Asset"
        elif re.search(r"\b(version|versions)\b", lowered):
            requested_type = "Version"

        if requested_type:
            rows = connection.execute(
                """
                SELECT entity_type, data_json FROM shotgrid_records
                WHERE project_id = ? AND entity_type = ?
                ORDER BY name COLLATE NOCASE LIMIT ?
                """,
                (project_id, requested_type, limit),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT entity_type, data_json FROM shotgrid_records
                WHERE project_id = ?
                ORDER BY entity_type, name COLLATE NOCASE LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()

        connection.close()
        results = [
            {
                "entity_type": "Project",
                **with_source_url(json.loads(matched_project["data_json"]), "Project"),
            }
        ]
        results.extend([
            {
                "entity_type": row["entity_type"],
                **with_source_url(json.loads(row["data_json"]), row["entity_type"]),
            }
            for row in rows
        ])
        return results

    # 4. Entity type focus: notes, tasks, shots
    if re.search(r"\b(note|notes|retours?)\b", lowered):
        note_rows = connection.execute(
            """
            SELECT entity_type, data_json FROM shotgrid_records
            WHERE entity_type = 'Note'
            ORDER BY entity_id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        if note_rows:
            connection.close()
            return [
                {
                    "entity_type": "Note",
                    **with_source_url(json.loads(row["data_json"]), "Note"),
                }
                for row in note_rows
            ]

    # 5. Smart FTS5 Full-Text Search (filtered keywords without stop words)
    raw_words = re.findall(r"[\wÀ-ÿ0-9_-]{3,}", lowered)
    keywords = [w for w in raw_words if w not in STOP_WORDS]
    if keywords:
        fts_query = " OR ".join(f'"{w}"*' for w in keywords[:8])
        try:
            fts_rows = connection.execute(
                """
                SELECT r.entity_type, r.data_json
                FROM shotgrid_fts f
                JOIN shotgrid_records r ON r.entity_type = f.entity_type AND r.entity_id = f.entity_id
                WHERE shotgrid_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
            if fts_rows:
                connection.close()
                return [
                    {
                        "entity_type": row["entity_type"],
                        **with_source_url(json.loads(row["data_json"]), row["entity_type"]),
                    }
                    for row in fts_rows
                ]
        except Exception:
            pass

    # 6. Fallback LIKE search
    pattern = f"%{clean_q}%"
    rows = connection.execute(
        """
        SELECT entity_type, data_json FROM shotgrid_records
        WHERE name LIKE ? OR data_json LIKE ?
        ORDER BY name COLLATE NOCASE
        LIMIT ?
        """,
        (pattern, pattern, limit),
    ).fetchall()
    connection.close()
    return [
        {
            "entity_type": row["entity_type"],
            **with_source_url(json.loads(row["data_json"]), row["entity_type"]),
        }
        for row in rows
    ]


def compact_record_for_llm(record: dict[str, Any], entity_type: str) -> dict[str, Any]:
    """Prunes noisy metadata from records to preserve LLM token context while retaining exact business clarity."""
    compact: dict[str, Any] = {
        "type": entity_type,
        "id": record.get("id"),
        "name": record.get("name") or record.get("code") or record.get("cached_display_name"),
    }

    if entity_type == "Project":
        compact["status"], compact["is_active"] = project_state(record)

        if record.get("start_date"):
            compact["start_date"] = record["start_date"]
        if record.get("end_date"):
            compact["end_date"] = record["end_date"]
    else:
        if "sg_status_list" in record:
            compact["status"] = record["sg_status_list"]
        elif "sg_status" in record:
            compact["status"] = record["sg_status"]

        if record.get("project"):
            compact["project"] = record["project"].get("name") if isinstance(record["project"], dict) else record["project"]

        if "task_assignees" in record and record["task_assignees"]:
            compact["assigned_to"] = [u.get("name") for u in record["task_assignees"] if isinstance(u, dict)]

        if record.get("content"):
            compact["content"] = str(record["content"])[:400]
        if record.get("subject"):
            compact["subject"] = record["subject"]

        if record.get("start_date"):
            compact["start_date"] = record["start_date"]
        if record.get("due_date"):
            compact["due_date"] = record["due_date"]
        elif record.get("end_date"):
            compact["end_date"] = record["end_date"]

    if record.get("source_url"):
        compact["source_url"] = record["source_url"]

    return compact


SYNC_PAGE_SIZE = 500
# A run still marked "running" after this long is considered dead (server crash/restart).
SYNC_STALE_AFTER = timedelta(minutes=30)
FTS_CONTENT_FIELDS = ("subject", "content", "sg_description", "description", "code")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_all_records(client, entity_type: str, fields: list[str]) -> list[dict[str, Any]]:
    """Fetch every record of a type, paging in a stable order so no record is skipped."""
    records: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = client.find(
            entity_type,
            [],
            fields,
            order=[{"field_name": "id", "direction": "asc"}],
            limit=SYNC_PAGE_SIZE,
            page=page,
        )
        records.extend(batch)
        if len(batch) < SYNC_PAGE_SIZE:
            return records
        page += 1


def record_rows(entity_type: str, record: dict[str, Any], now: str) -> tuple[tuple, tuple]:
    """Build the (shotgrid_records row, shotgrid_fts row) for one ShotGrid record."""
    name = record.get("name") or record.get("code") or record.get("cached_display_name")
    status = record.get("sg_status") or record.get("sg_status_list")
    if entity_type == "Project":
        project_id = record["id"]
    else:
        proj = record.get("project")
        project_id = proj["id"] if isinstance(proj, dict) and "id" in proj else None

    content = " ".join(str(record[k]) for k in FTS_CONTENT_FIELDS if record.get(k))
    return (
        (entity_type, record["id"], name, project_id, status, json.dumps(record, default=str), now),
        (entity_type, record["id"], project_id, name or "", content),
    )


def store_entity_records(
    connection: sqlite3.Connection, entity_type: str, records: list[dict[str, Any]]
) -> dict[str, int]:
    """Replace the local copy of one entity type with `records`, in a single transaction.

    Upserts every record, rebuilds that type's full-text rows (so they never duplicate),
    and removes records that no longer exist in ShotGrid.
    """
    now = utc_now()
    pairs = [record_rows(entity_type, r, now) for r in records]
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
        connection.executemany(
            """
            INSERT INTO shotgrid_records
                (entity_type, entity_id, name, project_id, status, data_json, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_type, entity_id) DO UPDATE SET
                name=excluded.name,
                project_id=excluded.project_id,
                status=excluded.status,
                data_json=excluded.data_json,
                synced_at=excluded.synced_at
            """,
            [record_row for record_row, _ in pairs],
        )
        connection.executemany(
            "DELETE FROM shotgrid_records WHERE entity_type=? AND entity_id=?",
            [(entity_type, entity_id) for entity_id in stale_ids],
        )
        if live_ids:
            connection.execute("DELETE FROM shotgrid_fts WHERE entity_type=?", (entity_type,))
            connection.executemany(
                """
                INSERT INTO shotgrid_fts (entity_type, entity_id, project_id, name, content)
                VALUES (?, ?, ?, ?, ?)
                """,
                [fts_row for _, fts_row in pairs],
            )
    return {"upserted": len(records), "deleted": len(stale_ids)}


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
            f"UPDATE sync_runs SET status='failed', finished_at=?, error=? WHERE {where}",
            params,
        )
    return cursor.rowcount


def start_sync_run(connection: sqlite3.Connection) -> Optional[int]:
    """Create a 'running' sync run, or return None if another one is genuinely in progress."""
    fail_stale_sync_runs(connection, SYNC_STALE_AFTER)
    with connection:
        if connection.execute("SELECT 1 FROM sync_runs WHERE status='running' LIMIT 1").fetchone():
            return None
        return connection.execute(
            "INSERT INTO sync_runs (started_at, status) VALUES (?, 'running')", (utc_now(),)
        ).lastrowid


def sync_shotgrid(run_id: Optional[int] = None) -> dict[str, Any]:
    connection = database()
    if run_id is None:
        run_id = start_sync_run(connection)
        if run_id is None:
            connection.close()
            raise RuntimeError("Une synchronisation est déjà en cours")
    total = 0
    deleted = 0
    try:
        client = shotgrid_client()
        for entity_type in SYNC_ENTITIES:
            fields = list(client.schema_field_read(entity_type).keys())
            if "id" not in fields:
                fields.insert(0, "id")
            stats = store_entity_records(
                connection, entity_type, fetch_all_records(client, entity_type, fields)
            )
            total += stats["upserted"]
            deleted += stats["deleted"]
            with connection:
                connection.execute(
                    "UPDATE sync_runs SET records_count=? WHERE id=?", (total, run_id)
                )

        finished = utc_now()
        with connection:
            connection.execute(
                "UPDATE sync_runs SET finished_at=?, records_count=?, status='completed' WHERE id=?",
                (finished, total, run_id),
            )
        return {
            "status": "completed",
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


SYSTEM_ENTITY_TYPES = {
    "EventLogEntry", "PageHit", "PageSetting", "Page", "BannerUserConnection",
    "AppWelcomeUserConnection", "Icon", "PermissionRuleSet", "Status", "ApiUser",
    "WorkDayRule", "Banner", "AppWelcome", "FilesystemLocation", "PipelineConfiguration",
}


def audit_shotgrid(include_unsynced: bool = False) -> dict[str, Any]:
    """Compare live ShotGrid with the local cache (read-only on both sides)."""
    client = shotgrid_client()
    connection = database()
    try:
        entities = []
        for entity_type in SYNC_ENTITIES:
            live_ids = {r["id"] for r in client.find(entity_type, [], ["id"])}
            local_ids = {
                row[0]
                for row in connection.execute(
                    "SELECT entity_id FROM shotgrid_records WHERE entity_type=?", (entity_type,)
                )
            }
            sample = connection.execute(
                "SELECT data_json FROM shotgrid_records WHERE entity_type=? LIMIT 1",
                (entity_type,),
            ).fetchone()
            stored_fields = set(json.loads(sample["data_json"])) if sample else set()
            schema_fields = set(client.schema_field_read(entity_type))
            missing = sorted(live_ids - local_ids)
            deleted = sorted(local_ids - live_ids)
            entities.append({
                "entity_type": entity_type,
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
                if entity_type in SYNC_ENTITIES or entity_type in SYSTEM_ENTITY_TYPES:
                    continue
                if not info.get("visible", {}).get("value", True):
                    continue
                try:
                    count = client.summarize(
                        entity_type, [], [{"field": "id", "type": "count"}]
                    )["summaries"]["id"]
                except Exception:
                    continue
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
            "search_index": {
                "records": records_count,
                "fts_rows": fts_count,
                "healthy": fts_count == records_count,
            },
            "unsynced_entity_types": unsynced,
        }
    finally:
        connection.close()


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/models")
async def list_models() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.ollama_url}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name") for m in data.get("models", [])]
                return {"models": models, "default": settings.ollama_model or (models[0] if models else "")}
    except Exception:
        pass
    return {"models": [], "default": settings.ollama_model}


@app.get("/api/dashboard")
async def dashboard() -> dict[str, Any]:
    connection = database()
    projects_rows = connection.execute(
        """
        SELECT entity_id, name, status, data_json
        FROM shotgrid_records
        WHERE entity_type='Project'
        ORDER BY name COLLATE NOCASE
        """
    ).fetchall()

    tasks_count = connection.execute("SELECT COUNT(*) FROM shotgrid_records WHERE entity_type='Task'").fetchone()[0]
    shots_count = connection.execute("SELECT COUNT(*) FROM shotgrid_records WHERE entity_type='Shot'").fetchone()[0]
    notes_count = connection.execute("SELECT COUNT(*) FROM shotgrid_records WHERE entity_type='Note'").fetchone()[0]

    last_sync = connection.execute(
        """
        SELECT started_at, finished_at, records_count, status, error
        FROM sync_runs ORDER BY id DESC LIMIT 1
        """
    ).fetchone()
    connection.close()

    projects = [with_source_url(json.loads(p["data_json"]), "Project") for p in projects_rows]
    active = [p for p in projects if p["is_active"]]

    return {
        "projects_active": len(active),
        "projects_total": len(projects),
        "tasks_total": tasks_count,
        "shots_total": shots_count,
        "notes_total": notes_count,
        "projects": projects,
        "last_sync": dict(last_sync) if last_sync else None,
    }


@app.get("/api/projects/{project_id}")
async def project_details(project_id: int) -> dict[str, Any]:
    connection = database()
    project_row = connection.execute(
        "SELECT data_json FROM shotgrid_records WHERE entity_type='Project' AND entity_id=?",
        (project_id,),
    ).fetchone()
    if not project_row:
        connection.close()
        raise HTTPException(status_code=404, detail="Projet introuvable")

    related: dict[str, list[Any]] = {}
    for entity_type in ("Shot", "Task", "Asset", "Version", "Note"):
        rows = connection.execute(
            """
            SELECT data_json FROM shotgrid_records
            WHERE entity_type=? AND project_id=?
            ORDER BY name COLLATE NOCASE
            LIMIT 500
            """,
            (entity_type, project_id),
        ).fetchall()
        related[entity_type] = [
            with_source_url(json.loads(row["data_json"]), entity_type)
            for row in rows
        ]

    connection.close()
    return {
        "project": with_source_url(json.loads(project_row["data_json"]), "Project"),
        "related": related,
    }


@app.post("/api/sync")
async def sync(background_tasks: BackgroundTasks) -> dict[str, Any]:
    connection = database()
    try:
        run_id = start_sync_run(connection)
    finally:
        connection.close()
    if run_id is None:
        raise HTTPException(status_code=409, detail="Une synchronisation est déjà en cours")
    background_tasks.add_task(sync_shotgrid, run_id)
    return {"status": "started", "run_id": run_id}


@app.get("/api/sync/audit")
def sync_audit(include_unsynced: bool = False) -> dict[str, Any]:
    """Live comparison ShotGrid ↔ local cache. Plain `def` so FastAPI runs it in a thread."""
    return audit_shotgrid(include_unsynced=include_unsynced)


@app.get("/api/sync/status")
async def sync_status() -> dict[str, Any]:
    connection = database()
    row = connection.execute(
        """
        SELECT started_at, finished_at, records_count, status, error
        FROM sync_runs ORDER BY id DESC LIMIT 1
        """
    ).fetchone()
    connection.close()
    return {"last_sync": dict(row) if row else None}


@app.get("/api/data/{entity}")
async def data(
    entity: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    search: Optional[str] = None,
    status: Optional[str] = None,
    project_id: Optional[int] = None,
) -> dict[str, Any]:
    entity_type = next(
        (name for name, plural in SYNC_ENTITIES.items() if plural == entity),
        None,
    )
    if not entity_type:
        raise HTTPException(status_code=404, detail="Type de données inconnu")

    result = cached_records(
        entity_type=entity_type,
        page=page,
        limit=limit,
        search=search,
        status=status,
        project_id=project_id,
    )
    return {"entity": entity, "entity_type": entity_type, **result}


@app.get("/auth/google/login")
async def google_login(request: Request):
    if not os.getenv("GOOGLE_CLIENT_ID") or not os.getenv("GOOGLE_CLIENT_SECRET"):
        raise HTTPException(status_code=503, detail="Google OAuth n'est pas configuré")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", f"{settings.app_base_url}/auth/google/callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth/google/callback")
async def google_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Échec de l'authentification Google") from exc
    user = token.get("userinfo")
    if not user or not user.get("sub") or not user.get("email"):
        raise HTTPException(status_code=401, detail="Profil Google incomplet")
    request.session["user"] = {
        "id": user["sub"],
        "email": user["email"],
        "name": user.get("name", user["email"]),
        "google_access_token": token["access_token"],
    }
    return {"authenticated": True}


@app.post("/auth/logout")
async def logout(request: Request) -> dict[str, bool]:
    request.session.clear()
    return {"authenticated": False}


@app.get("/api/me")
async def me(request: Request) -> dict[str, Any]:
    user = request.session.get("user")
    if not user:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "id": user["id"],
        "email": user["email"],
        "name": user.get("name", user["email"]),
    }


async def search_drive(user: dict[str, Any], question: str) -> list[dict[str, Any]]:
    access_token = user.get("google_access_token") or os.getenv("GOOGLE_ACCESS_TOKEN")
    if not access_token:
        return []
    clean_q = question.replace("'", "\\'").strip()
    query = f"trashed = false and name contains '{clean_q}'"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                "https://www.googleapis.com/drive/v3/files",
                params={"q": query, "pageSize": 15, "fields": "files(id,name,mimeType,webViewLink)"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if response.status_code < 400:
            return response.json().get("files", [])
    except Exception:
        pass
    return []


SYSTEM_PROMPT = """
Tu es Lia, l'assistante intelligente de MedIAData.

Tu aides une équipe de production VFX, 3D, animation et post-production à comprendre
et exploiter ses données Autodesk ShotGrid ainsi que certains documents Google Drive.

Tu es une assistante opérationnelle : fiable, concise, structurée et orientée décision.
Tu réponds en français, sauf si l'utilisateur demande une autre langue.

==================================================
MISSION
==================================================

Ton rôle est de :

- suivre l'état réel des projets ;
- identifier les tâches en attente, en cours ou en review ;
- retrouver des shots, assets, versions, notes et utilisateurs ;
- résumer les informations de production ;
- comparer des éléments lorsque les données le permettent ;
- aider à repérer les risques, retards ou points nécessitant une action ;
- fournir des réponses directement utiles à un superviseur de production.

Tu ne modifies jamais ShotGrid, Google Drive ou la base de données.
Tu es uniquement un assistant de consultation et d'analyse.

==================================================
SOURCES DISPONIBLES
==================================================

Les données sont fournies dans le message utilisateur sous cette forme :

{
  "shotgrid": [...],
  "google_drive": [...]
}

La source `shotgrid` contient des résultats issus du cache local SQLite.
La source `google_drive` contient des fichiers Google Drive trouvés par leur nom.

Chaque élément ShotGrid peut contenir :

- `type`
- `id`
- `name`
- `project`
- `status`
- `assigned_to`
- `subject`
- `content`
- `start_date`
- `due_date`
- `end_date`
- `source_url`

Les résultats fournis sont les seules données auxquelles tu peux te fier.

==================================================
RÈGLE ABSOLUE DE FIABILITÉ
==================================================

- N'invente jamais un nom, un ID, une date, un statut, une personne ou une relation.
- N'utilise jamais une connaissance générale pour compléter une information absente.
- Ne transforme jamais une supposition en affirmation.
- Si l'information n'est pas présente, dis exactement :
  « Je ne trouve pas cette information dans les données disponibles. »
- Si les résultats semblent incomplets, précise :
  « Cette réponse est basée sur les résultats disponibles, qui peuvent être partiels. »
- Ne prétends jamais avoir analysé toute la base si seuls quelques résultats sont fournis.
- Ne dis jamais qu'une action a été effectuée : tu ne peux pas modifier les données.

==================================================
PRIORITÉ DES SOURCES
==================================================

1. Pour les projets, tâches, shots, assets, versions et notes :
   utilise prioritairement `shotgrid`.

2. Pour les documents et fichiers :
   utilise `google_drive`.

3. Ne mélange pas les deux sources sans l'indiquer.

4. Si ShotGrid et Google Drive donnent des informations différentes,
   présente-les séparément et signale la différence.

==================================================
STATUTS DE PRODUCTION
==================================================

Pour les tâches, shots, assets et versions :

- `wtg` = ⏳ En attente
- `ip` = ⚙️ En cours
- `rev` = 👀 En review
- `fin` = ✅ Terminé
- `apr` = ⭐ Approuvé
- `opn` = 📝 Ouvert
- `clsd` = 🔒 Fermé
- `act` = 🟢 Actif

Pour les projets :

- `Actif` = 🟢 Actif (`is_active` = true)
- `Archivé` = ⚫ Archivé
- `Template` = 🧩 Modèle
- `Démo / Test` = 🧪 Démonstration
- `Terminé`, `Perdu`, `Appel d'offres` = projet non actif

Un projet est actif si et seulement si son champ `is_active` vaut true.

Attention :

- le statut d'un projet est différent du statut d'une tâche ;
- `ip`, `rev`, `fin`, etc. ne doivent jamais être interprétés comme des statuts de projet ;
- ne considère pas un projet comme actif uniquement parce qu'une tâche est active.

==================================================
ANALYSE DES QUESTIONS
==================================================

Avant de répondre :

1. Identifie ce que l'utilisateur demande réellement.
2. Identifie l'entité concernée : projet, shot, tâche, asset, version, note ou utilisateur.
3. Identifie le projet concerné s'il est mentionné.
4. Utilise l'historique de conversation pour comprendre les pronoms et relances.
5. Vérifie que les données fournies permettent réellement de répondre.
6. Distingue clairement les faits, les tendances et les limites des données.

Pour une question courte comme :

- « et ses tâches ? »
- « lesquels sont bloqués ? »
- « et les notes ? »

utilise le dernier projet ou élément clairement mentionné dans la conversation.

Si plusieurs projets ou éléments peuvent correspondre, demande une précision
au lieu de choisir arbitrairement.

==================================================
RÈGLES DE COMPTAGE
==================================================

Lorsque tu comptes des éléments :

- compte uniquement les éléments réellement présents dans les sources ;
- indique toujours ce qui est compté ;
- ne déduplique pas deux éléments ayant des IDs différents ;
- ne présente pas un résultat limité comme un total absolu ;
- précise si le résultat est partiel.

Exemple :

« J'ai trouvé 12 tâches dans les résultats disponibles. La recherche pouvant être
limitée aux éléments pertinents, ce nombre ne garantit pas que la base entière
ne contient pas d'autres tâches. »

==================================================
FORMAT DES RÉPONSES
==================================================

Adapte la longueur à la question.

Pour une question simple :
réponds directement en quelques phrases.

Pour une analyse :
utilise cette structure si elle est pertinente :

### Réponse

Réponse principale basée sur les données.

### Détails

- élément ;
- type ;
- ID ;
- statut ;
- projet ;
- assignation ;
- échéance.

### Points d'attention

Uniquement si un risque ou une information importante est réellement visible.

### Synthèse

Résumé très court avec le nombre d'éléments concernés.

Utilise des tableaux uniquement lorsque plusieurs éléments doivent être comparés.

==================================================
IDENTIFICATION DES ÉLÉMENTS
==================================================

Lorsque c'est utile, identifie chaque élément avec :

- son type ;
- son nom ;
- son ID ;
- son projet ;
- son statut.

Exemple :

`Tâche — Lighting final — ID 4821 — Projet : Film X — ⚙️ En cours`

Ne crée jamais d'ID lorsqu'il n'est pas fourni.

==================================================
LIENS
==================================================

Si `source_url` existe, utilise-le comme lien Markdown.

Bon exemple :

[Lighting final — ID 4821](source_url)

Mauvais exemples :

[Voir dans ShotGrid](source_url)
[ShotGrid](source_url)

Le lien doit être associé au nom réel de l'élément.
Ne fabrique jamais une URL.

Pour Google Drive, utilise `webViewLink` uniquement s'il est fourni.

==================================================
ANALYSE PRODUCTION
==================================================

Tu peux signaler un point d'attention seulement s'il est démontré par les données.

Exemples autorisés :

- une tâche dont le statut est `wtg` ;
- une version en `rev` ;
- une échéance dépassée si une date actuelle et une date d'échéance sont disponibles ;
- une note ouverte avec un contenu fourni ;
- un projet dont les données indiquent qu'il est archivé.

N'affirme jamais :

- qu'une tâche est réellement en retard sans date vérifiable ;
- qu'une personne est responsable si elle n'est pas dans `assigned_to` ;
- qu'un projet est bloqué si aucun statut ou contenu ne le démontre ;
- qu'une équipe est en sous-effectif sans données explicites.

==================================================
TON
==================================================

Sois :

- professionnelle ;
- claire ;
- calme ;
- utile ;
- directe ;
- sans jargon inutile.

Ne commence pas systématiquement par une formule de politesse.
Ne répète pas la question de l'utilisateur.
Ne termine pas chaque réponse par une phrase artificielle.
Ne surcharge pas les réponses avec des emojis : utilise-les seulement pour les statuts.

Si les données ne permettent pas de répondre, sois honnête et propose éventuellement
la précision nécessaire pour continuer."""


@app.post("/api/query/stream")
async def query_stream(request: Request, payload: QueryRequest):
    user = request.session.get("user", {})
    drive = await search_drive(user, payload.question)

    # Use question primarily for retrieval to avoid topic drift from history
    search_q = payload.question.strip()
    if len(search_q.split()) <= 3 and payload.history:
        # If very short follow-up question (e.g. "et ses tâches ?"), append last user question
        last_user_msg = next(
            (m.get("content", "") for m in reversed(payload.history) if m.get("role") == "user"),
            ""
        )
        if last_user_msg:
            search_q = f"{last_user_msg} {search_q}".strip()

    # Search with higher limit (up to 75 sources)
    shotgrid_raw = search_cached(search_q, limit=75)

    # Compact sources to protect token window while keeping business semantics
    shotgrid = [
        compact_record_for_llm(r, r.get("entity_type", "Unknown"))
        for r in shotgrid_raw
    ]
    sources = {"shotgrid": shotgrid, "google_drive": drive}

    model = payload.model or settings.ollama_model
    if not model:
        # Try fetching first available model
        models_resp = await list_models()
        if models_resp["models"]:
            model = models_resp["models"][0]
        else:
            raise HTTPException(status_code=503, detail="Aucun modèle Ollama disponible.")

    prompt = (
        f"SOURCES DONNÉES (JSON COMPACT):\n{json.dumps(sources, ensure_ascii=False, default=str)}\n\n"
        f"QUESTION UTILISATEUR:\n{payload.question}"
    )

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in payload.history[-6:]:
        messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    messages.append({"role": "user", "content": prompt})

    async def event_generator() -> AsyncGenerator[str, None]:
        # First send sources metadata
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources}, ensure_ascii=False)}\n\n"

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST",
                    f"{settings.ollama_url}/api/chat",
                    json={
                        "model": model,
                        "messages": messages,
                        "stream": True,
                    },
                ) as response:
                    if response.status_code >= 400:
                        err_text = await response.aread()
                        yield f"data: {json.dumps({'type': 'error', 'error': f'Erreur Ollama: {err_text.decode()}'})}\n\n"
                        return

                    async for line in response.aiter_lines():
                        if not line or not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                            token = chunk.get("message", {}).get("content", "")
                            if token:
                                yield f"data: {json.dumps({'type': 'token', 'token': token}, ensure_ascii=False)}\n\n"
                            if chunk.get("done"):
                                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                                break
                        except Exception:
                            continue
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/query")
async def query_legacy(request: Request, payload: QueryRequest) -> dict[str, Any]:
    # Backward compatibility endpoint
    user = request.session.get("user", {})
    drive = await search_drive(user, payload.question)
    shotgrid_raw = search_cached(payload.question, limit=75)
    shotgrid = [compact_record_for_llm(r, r.get("entity_type", "Unknown")) for r in shotgrid_raw]
    sources = {"shotgrid": shotgrid, "google_drive": drive}

    model = payload.model or settings.ollama_model
    prompt = (
        f"SOURCES DONNÉES:\n{json.dumps(sources, ensure_ascii=False, default=str)}\n\n"
        f"QUESTION:\n{payload.question}"
    )
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{settings.ollama_url}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
            },
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail="Ollama indisponible")
    return {
        "answer": resp.json().get("message", {}).get("content", ""),
        "sources": sources,
    }


# Static frontend: only ever serve the Vite build output. Never fall back to the
# project root, which holds .env (credentials) and the SQLite database.
DIST_DIR = PROJECT_ROOT / "frontend" / "dist"
if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="frontend")
else:
    @app.get("/")
    async def frontend_missing() -> dict[str, str]:
        raise HTTPException(
            status_code=503,
            detail="Frontend non compilé : lancez `npm run build` dans frontend/.",
        )
