import asyncio
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
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


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=20)
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
app = FastAPI(title="Studio Ops Dashboard API")

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


def with_source_url(record: dict[str, Any], entity_type=None) -> dict[str, Any]:
    result = dict(record)
    record_type = entity_type or result.get("type")
    if record_type and result.get("id") and settings.shotgrid_url:
        result["source_url"] = f"{settings.shotgrid_url}/detail/{record_type}/{result['id']}"
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


def search_cached(question: str, limit: int = 30) -> list[dict[str, Any]]:
    connection = database()
    clean_q = question.strip()

    # 1. Exact Note ID lookup: "note #1234"
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

    # 2. Project name match in question
    project_rows = connection.execute(
        "SELECT entity_id, name, data_json FROM shotgrid_records WHERE entity_type='Project' AND name IS NOT NULL ORDER BY length(name) DESC"
    ).fetchall()
    lowered = clean_q.casefold()
    matched_project = next(
        (row for row in project_rows if row["name"].casefold() in lowered),
        None,
    )

    if matched_project:
        project_id = matched_project["entity_id"]
        # Detect sub-entity
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
                "entity_type": matched_project["name"],
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

    # 3. FTS5 Full-Text Search
    clean_words = re.findall(r"[\wÀ-ÿ0-9_-]{3,}", clean_q)
    if clean_words:
        fts_query = " OR ".join(f'"{w}"*' for w in clean_words[:6])
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

    # 4. Fallback LIKE search
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
    """Prunes noisy metadata from records to preserve LLM token context."""
    compact: dict[str, Any] = {
        "type": entity_type,
        "id": record.get("id"),
        "name": record.get("name") or record.get("code") or record.get("cached_display_name"),
    }
    if "sg_status_list" in record:
        compact["status"] = record["sg_status_list"]
    elif "sg_status" in record:
        compact["status"] = record["sg_status"]

    if record.get("project"):
        compact["project"] = record["project"].get("name") if isinstance(record["project"], dict) else record["project"]

    if "task_assignees" in record and record["task_assignees"]:
        compact["assigned_to"] = [u.get("name") for u in record["task_assignees"] if isinstance(u, dict)]

    if record.get("content"):
        compact["content"] = str(record["content"])[:500]
    if record.get("subject"):
        compact["subject"] = record["subject"]

    if record.get("start_date"):
        compact["start_date"] = record["start_date"]
    if record.get("end_date"):
        compact["end_date"] = record["end_date"]

    if record.get("source_url"):
        compact["source_url"] = record["source_url"]

    return compact


def sync_shotgrid() -> dict[str, Any]:
    client = shotgrid_client()
    started = datetime.now(timezone.utc).isoformat()
    connection = database()
    run = connection.execute(
        "INSERT INTO sync_runs (started_at, status) VALUES (?, ?)",
        (started, "running"),
    )
    run_id = run.lastrowid
    total = 0
    try:
        for entity_type in SYNC_ENTITIES:
            fields = list(client.schema_field_read(entity_type).keys())
            if "id" not in fields:
                fields.insert(0, "id")
            page = 1
            while True:
                records = client.find(entity_type, [], fields, limit=500, page=page)
                if not records:
                    break
                now = datetime.now(timezone.utc).isoformat()
                rows_to_insert = []
                fts_rows = []

                for record in records:
                    name = record.get("name") or record.get("code") or record.get("cached_display_name")
                    status = record.get("sg_status") or record.get("sg_status_list")
                    project_id = None
                    if entity_type == "Project":
                        project_id = record["id"]
                    else:
                        proj = record.get("project")
                        if isinstance(proj, dict) and "id" in proj:
                            project_id = proj["id"]

                    rows_to_insert.append((
                        entity_type,
                        record["id"],
                        name,
                        project_id,
                        status,
                        json.dumps(record, default=str),
                        now,
                    ))

                    content_parts = []
                    for k in ("subject", "content", "sg_description", "description", "code"):
                        if record.get(k):
                            content_parts.append(str(record[k]))

                    fts_rows.append((
                        entity_type,
                        record["id"],
                        project_id,
                        name or "",
                        " ".join(content_parts),
                    ))

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
                    rows_to_insert,
                )

                connection.executemany(
                    """
                    INSERT INTO shotgrid_fts (entity_type, entity_id, project_id, name, content)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    fts_rows,
                )

                total += len(records)
                connection.execute(
                    "UPDATE sync_runs SET records_count=? WHERE id=?",
                    (total, run_id),
                )
                connection.commit()
                if len(records) < 500:
                    break
                page += 1

        finished = datetime.now(timezone.utc).isoformat()
        connection.execute(
            "UPDATE sync_runs SET finished_at=?, records_count=?, status=? WHERE id=?",
            (finished, total, "completed", run_id),
        )
        connection.commit()
        return {"status": "completed", "records_count": total, "finished_at": finished}
    except Exception as exc:
        connection.execute(
            "UPDATE sync_runs SET finished_at=?, records_count=?, status=?, error=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), total, "failed", str(exc), run_id),
        )
        connection.commit()
        raise HTTPException(status_code=502, detail=f"Synchronisation ShotGrid échouée: {exc}") from exc
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
    active = [p for p in projects if p.get("sg_status") in ("Active", "Actif", "active", "act")]

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
    running = connection.execute(
        "SELECT 1 FROM sync_runs WHERE status='running' LIMIT 1"
    ).fetchone()
    connection.close()
    if running:
        raise HTTPException(status_code=409, detail="Une synchronisation est déjà en cours")
    background_tasks.add_task(sync_shotgrid)
    return {"status": "started"}


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
Tu es l'assistant de production expert du dashboard Studio Ops (ShotGrid & Google Drive).
Tu réponds en français clair, précis et professionnel.

Règles impératives :
1. Utilise uniquement les données présentes dans les SOURCES fournies.
2. Analyse toutes les sources avant de répondre.
3. Identifie les entités par leur type et identifiant (Project, Shot, Task, Asset, Version, Note, HumanUser).
4. Pour une question sur les statuts ou retards, sois précis sur les assignations et échéances.
5. Quand une source contient `source_url`, insère le lien Markdown cliquable : [Voir dans ShotGrid](source_url).
6. Si aucune information ne répond à la question, dis-le clairement sans inventer.
7. Termine par une brève mention des sources utilisées.
"""


@app.post("/api/query/stream")
async def query_stream(request: Request, payload: QueryRequest):
    user = request.session.get("user", {})
    drive = await search_drive(user, payload.question)

    context_questions = " ".join(
        message.get("content", "")
        for message in payload.history[-6:]
        if message.get("role") == "user"
    )
    search_q = f"{context_questions} {payload.question}".strip()
    shotgrid_raw = search_cached(search_q, limit=25)

    # Compact sources to protect token window
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
    shotgrid_raw = search_cached(payload.question, limit=20)
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


# Static frontend mounting (Vite React dist priority, fallback to root index.html)
DIST_DIR = PROJECT_ROOT / "frontend" / "dist"
if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="frontend")
else:
    app.mount("/", StaticFiles(directory=str(PROJECT_ROOT), html=True), name="legacy_frontend")
