"""Read API used by the dashboard UI (all reads come from the local SQLite cache)."""
import json
import threading
import time
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from backend import shotgrid, sync
from backend.auth import require_admin, require_user
from backend.db import database
from backend.users import User
from backend.records import REVIEW_STATUSES, present, status_bucket
from backend.retrieval import DONE_SQL, Scope, _filters

router = APIRouter()

BUCKETS = ("done", "review", "in_progress", "waiting", "other")
REVIEW_SQL = ",".join(f"'{s}'" for s in sorted(REVIEW_STATUSES))
LATE_SQL = (
    f"json_extract(r.data_json,'$.due_date') < date('now') "
    f"AND LOWER(COALESCE(r.status,'')) NOT IN ({DONE_SQL})"
)


def _rows(rows, entity_type: Optional[str] = None) -> list[dict]:
    return [present(json.loads(row["data_json"]), entity_type or row["entity_type"]) for row in rows]


def _bucket_counts(status_rows) -> dict[str, int]:
    counts = dict.fromkeys(BUCKETS, 0)
    for status, n in status_rows:
        counts[status_bucket(status)] += n
    return counts


@router.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/dashboard")
def dashboard(user: User = Depends(require_user)) -> dict[str, Any]:
    c = database(user.visible_projects)
    try:
        projects = _rows(c.execute(
            "SELECT entity_type, data_json FROM shotgrid_records WHERE entity_type='Project' "
            "ORDER BY name COLLATE NOCASE"
        ).fetchall(), "Project")

        task_status: dict[int, list] = {}
        for row in c.execute(
            "SELECT project_id, status, COUNT(*) n FROM shotgrid_records "
            "WHERE entity_type='Task' GROUP BY project_id, status"
        ):
            task_status.setdefault(row["project_id"], []).append((row["status"], row["n"]))
        late = dict(c.execute(
            f"SELECT r.project_id, COUNT(*) FROM shotgrid_records r WHERE r.entity_type='Task' AND {LATE_SQL} "
            "GROUP BY r.project_id"
        ).fetchall())
        shots = dict(c.execute(
            "SELECT project_id, COUNT(*) FROM shotgrid_records WHERE entity_type='Shot' GROUP BY project_id"
        ).fetchall())
        activity = dict(c.execute(
            "SELECT project_id, MAX(json_extract(data_json,'$.updated_at')) FROM shotgrid_records "
            "WHERE entity_type IN ('Task','Note','Version','Shot') GROUP BY project_id"
        ).fetchall())
        for p in projects:
            p["tasks"] = _bucket_counts(task_status.get(p["id"], []))
            p["tasks_total"] = sum(p["tasks"].values())
            p["tasks_late"] = late.get(p["id"], 0)
            p["shots_total"] = shots.get(p["id"], 0)
            p["last_activity"] = activity.get(p["id"])

        totals = dict(c.execute(
            "SELECT entity_type, COUNT(*) FROM shotgrid_records GROUP BY entity_type"
        ).fetchall())
        recent_notes = _rows(c.execute(
            "SELECT entity_type, data_json FROM shotgrid_records WHERE entity_type='Note' "
            "ORDER BY entity_id DESC LIMIT 12"
        ).fetchall())
        last_sync = c.execute(
            "SELECT started_at, finished_at, records_count, status, error, mode FROM sync_runs "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        c.close()

    active = [p for p in projects if p["is_active"]]
    return {
        "projects": projects,
        "projects_total": len(projects),
        "projects_active": len(active),
        "tasks_total": totals.get("Task", 0),
        "tasks_late": sum(p["tasks_late"] for p in active),
        "tasks_review": sum(p["tasks"]["review"] for p in active),
        "shots_total": totals.get("Shot", 0),
        "notes_total": totals.get("Note", 0),
        "totals": totals,
        "recent_notes": recent_notes,
        "last_sync": dict(last_sync) if last_sync else None,
    }


@router.get("/api/projects/{project_id}")
def project_details(project_id: int, user: User = Depends(require_user)) -> dict[str, Any]:
    c = database(user.visible_projects)
    try:
        row = c.execute(
            "SELECT data_json FROM shotgrid_records WHERE entity_type='Project' AND entity_id=?", (project_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Projet introuvable")
        project = present(json.loads(row["data_json"]), "Project")

        counts = dict(c.execute(
            "SELECT entity_type, COUNT(*) FROM shotgrid_records WHERE project_id=? AND entity_type!='Project' "
            "GROUP BY entity_type",
            (project_id,),
        ).fetchall())
        task_buckets = _bucket_counts(c.execute(
            "SELECT status, COUNT(*) FROM shotgrid_records WHERE entity_type='Task' AND project_id=? GROUP BY status",
            (project_id,),
        ).fetchall())

        steps: dict[str, dict] = {}
        for r in c.execute(
            """
            SELECT COALESCE(s.name, 'Sans étape') AS step, s.entity_id AS step_id, t.status, COUNT(*) AS n
            FROM shotgrid_records t
            LEFT JOIN shotgrid_links l ON l.src_type='Task' AND l.src_id=t.entity_id AND l.field='step'
            LEFT JOIN shotgrid_records s ON s.entity_type='Step' AND s.entity_id=l.dst_id
            WHERE t.entity_type='Task' AND t.project_id=?
            GROUP BY step, step_id, t.status
            """,
            (project_id,),
        ):
            entry = steps.setdefault(r["step"], {"step": r["step"], "step_id": r["step_id"],
                                                 **dict.fromkeys(BUCKETS, 0)})
            entry[status_bucket(r["status"])] += r["n"]
        step_rows = sorted(steps.values(), key=lambda s: -sum(s[b] for b in BUCKETS))

        sequences = []
        for r in c.execute(
            """
            SELECT q.entity_id, q.name, sh.status, COUNT(sh.entity_id) AS n
            FROM shotgrid_records q
            LEFT JOIN shotgrid_links l ON l.dst_type='Sequence' AND l.dst_id=q.entity_id AND l.src_type='Shot'
            LEFT JOIN shotgrid_records sh ON sh.entity_type='Shot' AND sh.entity_id=l.src_id
            WHERE q.entity_type='Sequence' AND q.project_id=?
            GROUP BY q.entity_id, q.name, sh.status
            """,
            (project_id,),
        ):
            if not sequences or sequences[-1]["id"] != r["entity_id"]:
                sequences.append({"id": r["entity_id"], "name": r["name"], "shots": dict.fromkeys(BUCKETS, 0)})
            if r["n"]:
                sequences[-1]["shots"][status_bucket(r["status"])] += r["n"]
        sequences.sort(key=lambda s: (s["name"] or "").casefold())

        late_tasks = _rows(c.execute(
            f"SELECT r.entity_type, r.data_json FROM shotgrid_records r WHERE r.entity_type='Task' "
            f"AND r.project_id=? AND {LATE_SQL} ORDER BY json_extract(r.data_json,'$.due_date') LIMIT 50",
            (project_id,),
        ).fetchall())
        blocked_scope = Scope(project={"id": project_id, "name": ""}, blocked=True)
        where, params = _filters(blocked_scope, "Task")
        blocked_tasks = _rows(c.execute(
            f"SELECT r.entity_type, r.data_json FROM shotgrid_records r WHERE {where} LIMIT 50", params
        ).fetchall())

        people = [
            {"id": r["id"], "name": r["name"], "tasks": r["n"], "open": r["open"]}
            for r in c.execute(
                f"""
                SELECT u.entity_id AS id, u.name, COUNT(*) AS n,
                       SUM(CASE WHEN LOWER(COALESCE(t.status,'')) NOT IN ({DONE_SQL}) THEN 1 ELSE 0 END) AS open
                FROM shotgrid_records t
                JOIN shotgrid_links l ON l.src_type='Task' AND l.src_id=t.entity_id AND l.field='task_assignees'
                JOIN shotgrid_records u ON u.entity_type='HumanUser' AND u.entity_id=l.dst_id
                WHERE t.entity_type='Task' AND t.project_id=?
                GROUP BY u.entity_id, u.name ORDER BY open DESC, n DESC LIMIT 30
                """,
                (project_id,),
            )
        ]
        hours = c.execute(
            "SELECT COALESCE(SUM(json_extract(data_json,'$.duration')),0)/60.0 FROM shotgrid_records "
            "WHERE entity_type='TimeLog' AND project_id=?",
            (project_id,),
        ).fetchone()[0]
        recent_notes = _rows(c.execute(
            "SELECT entity_type, data_json FROM shotgrid_records WHERE entity_type='Note' AND project_id=? "
            "ORDER BY entity_id DESC LIMIT 15",
            (project_id,),
        ).fetchall())
    finally:
        c.close()

    return {
        "project": project,
        "counts": counts,
        "tasks": task_buckets,
        "steps": step_rows,
        "sequences": sequences,
        "late_tasks": late_tasks,
        "blocked_tasks": blocked_tasks,
        "people": people,
        "hours_logged": round(hours or 0, 1),
        "recent_notes": recent_notes,
    }


SORTS = {
    "name": "r.name COLLATE NOCASE",
    "due": "CASE WHEN json_extract(r.data_json,'$.due_date') IS NULL THEN 1 ELSE 0 END, "
           "json_extract(r.data_json,'$.due_date')",
    "recent": "r.entity_id DESC",
    "updated": "json_extract(r.data_json,'$.updated_at') DESC",
}


@router.get("/api/records/{entity_type}")
def records(
    entity_type: str,
    project_id: Optional[int] = None,
    sequence_id: Optional[int] = None,
    step_id: Optional[int] = None,
    person_id: Optional[int] = None,
    bucket: Optional[str] = Query(None, pattern="^(open|done|review|in_progress|waiting)$"),
    late: bool = False,
    blocked: bool = False,
    search: Optional[str] = None,
    sort: str = Query("name", pattern="^(name|due|recent|updated)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_user),
) -> dict[str, Any]:
    scope = Scope(
        project={"id": project_id, "name": ""} if project_id else None,
        sequence={"id": sequence_id, "name": ""} if sequence_id else None,
        step={"id": step_id, "name": ""} if step_id else None,
        person={"id": person_id, "name": ""} if person_id else None,
        bucket=bucket, late=late, blocked=blocked,
    )
    where, params = _filters(scope, entity_type)
    if search and search.strip():
        terms = " ".join(f'"{w}"*' for w in search.replace('"', " ").split()[:6])
        where += " AND r.rowid IN (SELECT rowid FROM shotgrid_fts WHERE shotgrid_fts MATCH ?)"
        params.append(terms)
    c = database(user.visible_projects)
    try:
        total = c.execute(f"SELECT COUNT(*) FROM shotgrid_records r WHERE {where}", params).fetchone()[0]
        rows = c.execute(
            f"SELECT r.entity_type, r.data_json FROM shotgrid_records r WHERE {where} "
            f"ORDER BY {SORTS[sort]} LIMIT ? OFFSET ?",
            [*params, limit, (page - 1) * limit],
        ).fetchall()
    finally:
        c.close()
    return {
        "entity_type": entity_type,
        "records": _rows(rows),
        "total": total,
        "page": page,
        "pages": max(1, (total + limit - 1) // limit),
    }


@router.get("/api/people")
def people(user: User = Depends(require_user)) -> dict[str, Any]:
    c = database(user.visible_projects)
    try:
        rows = c.execute(
            f"""
            SELECT u.entity_id AS id, u.name, u.data_json,
                   COUNT(t.entity_id) AS tasks,
                   SUM(CASE WHEN LOWER(COALESCE(t.status,'')) NOT IN ({DONE_SQL}) THEN 1 ELSE 0 END) AS open,
                   SUM(CASE WHEN json_extract(t.data_json,'$.due_date') < date('now')
                            AND LOWER(COALESCE(t.status,'')) NOT IN ({DONE_SQL}) THEN 1 ELSE 0 END) AS late,
                   SUM(CASE WHEN LOWER(COALESCE(t.status,'')) IN ({REVIEW_SQL}) THEN 1 ELSE 0 END) AS review,
                   COUNT(DISTINCT t.project_id) AS projects
            FROM shotgrid_records u
            LEFT JOIN shotgrid_links l ON l.dst_type='HumanUser' AND l.dst_id=u.entity_id
                 AND l.src_type='Task' AND l.field='task_assignees'
            LEFT JOIN shotgrid_records t ON t.entity_type='Task' AND t.entity_id=l.src_id
            WHERE u.entity_type='HumanUser'
            GROUP BY u.entity_id, u.name
            ORDER BY open DESC, u.name COLLATE NOCASE
            """
        ).fetchall()
    finally:
        c.close()
    result = []
    for r in rows:
        data = json.loads(r["data_json"])
        result.append({
            "id": r["id"], "name": r["name"], "email": data.get("email"),
            "active": data.get("sg_status_list") != "dis",
            "department": (data.get("department") or {}).get("name"),
            "tasks": r["tasks"], "open": r["open"] or 0, "late": r["late"] or 0,
            "review": r["review"] or 0, "projects": r["projects"],
        })
    return {"people": result}


@router.get("/api/people/{person_id}")
def person(person_id: int, user: User = Depends(require_user)) -> dict[str, Any]:
    c = database(user.visible_projects)
    try:
        row = c.execute(
            "SELECT data_json FROM shotgrid_records WHERE entity_type='HumanUser' AND entity_id=?", (person_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Personne introuvable")
        scope = Scope(person={"id": person_id, "name": ""})
        where, params = _filters(scope, "Task")
        tasks = _rows(c.execute(
            f"SELECT r.entity_type, r.data_json FROM shotgrid_records r WHERE {where} "
            f"ORDER BY CASE WHEN LOWER(COALESCE(r.status,'')) IN ({DONE_SQL}) THEN 1 ELSE 0 END, {SORTS['due']} "
            "LIMIT 300",
            params,
        ).fetchall())
        where_t, params_t = _filters(scope, "TimeLog")
        hours = c.execute(
            f"SELECT COALESCE(SUM(json_extract(r.data_json,'$.duration')),0)/60.0 FROM shotgrid_records r "
            f"WHERE {where_t}",
            params_t,
        ).fetchone()[0]
    finally:
        c.close()
    return {"person": present(json.loads(row["data_json"]), "HumanUser"), "tasks": tasks,
            "hours_logged": round(hours or 0, 1)}


@router.get("/api/search")
def search(q: str = Query(..., min_length=2), limit: int = Query(20, ge=1, le=50),
           user: User = Depends(require_user)) -> dict[str, Any]:
    terms = " ".join(f'"{w}"*' for w in q.replace('"', " ").split()[:6])
    c = database(user.visible_projects)
    try:
        rows = c.execute(
            """
            SELECT r.entity_type, r.entity_id, r.name, r.project_id, r.status,
                   (SELECT p.name FROM shotgrid_records p WHERE p.entity_type='Project' AND p.entity_id=r.project_id)
                   AS project_name
            FROM shotgrid_fts f JOIN shotgrid_records r ON r.rowid=f.rowid
            WHERE shotgrid_fts MATCH ? ORDER BY rank LIMIT ?
            """,
            (terms, limit),
        ).fetchall()
    except Exception:
        rows = []
    finally:
        c.close()
    return {"results": [dict(r) for r in rows]}


def status_labels() -> dict[str, dict[str, str]]:
    """ShotGrid Status entity: code -> {name, bucket}. Empty until Status is synced."""
    c = database()
    try:
        rows = c.execute(
            "SELECT json_extract(data_json,'$.code') AS code, name FROM shotgrid_records WHERE entity_type='Status'"
        ).fetchall()
    finally:
        c.close()
    return {r["code"]: {"name": r["name"], "bucket": status_bucket(r["code"])} for r in rows if r["code"]}


@router.get("/api/statuses")
def statuses(_user: User = Depends(require_user)) -> dict[str, Any]:
    return {"statuses": status_labels()}


@router.get("/api/entity-types")
def entity_types(_admin: User = Depends(require_admin)) -> dict[str, Any]:
    c = database()
    try:
        rows = c.execute(
            "SELECT entity_type, display_name, record_count, last_synced_at, last_full_sync_at "
            "FROM entity_types ORDER BY record_count DESC"
        ).fetchall()
    finally:
        c.close()
    return {"entity_types": [dict(r) for r in rows]}


# ---------------------------------------------------------------------------- sync

@router.post("/api/sync")
def start_sync(background_tasks: BackgroundTasks,
               mode: str = Query("auto", pattern="^(auto|full|incremental)$"),
               _admin: User = Depends(require_admin)) -> dict[str, Any]:
    c = database()
    try:
        run_id = sync.start_sync_run(c, mode)
    finally:
        c.close()
    if run_id is None:
        raise HTTPException(status_code=409, detail="Une synchronisation est déjà en cours")
    background_tasks.add_task(sync.sync_shotgrid, run_id, mode)
    return {"status": "started", "run_id": run_id}


@router.get("/api/sync/status")
def sync_status(_user: User = Depends(require_user)) -> dict[str, Any]:
    c = database()
    try:
        row = c.execute(
            "SELECT id, started_at, finished_at, records_count, status, error, mode FROM sync_runs "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        c.close()
    return {"last_sync": dict(row) if row else None}


@router.get("/api/sync/runs")
def sync_runs(limit: int = Query(20, ge=1, le=100), _admin: User = Depends(require_admin)) -> dict[str, Any]:
    c = database()
    try:
        rows = c.execute(
            "SELECT id, started_at, finished_at, records_count, status, error, mode FROM sync_runs "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        c.close()
    return {"runs": [dict(r) for r in rows]}


@router.get("/api/sync/audit")
def sync_audit(include_unsynced: bool = False, _admin: User = Depends(require_admin)) -> dict[str, Any]:
    return sync.audit_shotgrid(include_unsynced=include_unsynced)


# ---------------------------------------------------------------------- thumbnails

_THUMB_TTL = 45 * 60  # ShotGrid signs media URLs for a limited time
_thumb_cache: dict[tuple[str, int], tuple[float, Optional[str]]] = {}
_thumb_lock = threading.Lock()
_thumb_client = None


@router.get("/api/thumbnails")
def thumbnails(
    entity_type: str = Query(..., pattern="^[A-Za-z0-9_]+$"),
    ids: str = Query(..., description="Comma-separated ids"),
    user: User = Depends(require_user),
) -> dict[str, Optional[str]]:
    """Fresh (non-expired) thumbnail URLs, fetched from ShotGrid in one batch and cached.

    Only ids the user may see are looked up; the others are silently dropped.
    """
    global _thumb_client
    requested = [int(i) for i in ids.split(",") if i.strip().isdigit()][:100]
    c = database(user.visible_projects)
    try:
        marks = ",".join("?" * len(requested)) or "NULL"
        visible = {r[0] for r in c.execute(
            f"SELECT entity_id FROM shotgrid_records WHERE entity_type=? AND entity_id IN ({marks})",
            [entity_type, *requested],
        )}
    finally:
        c.close()
    wanted = [i for i in requested if i in visible]
    now = time.time()
    result: dict[str, Optional[str]] = {}
    missing = []
    for entity_id in wanted:
        cached = _thumb_cache.get((entity_type, entity_id))
        if cached and cached[0] > now:
            result[str(entity_id)] = cached[1]
        else:
            missing.append(entity_id)
    if missing:
        with _thumb_lock:
            try:
                if _thumb_client is None:
                    _thumb_client = shotgrid.shotgrid_client()
                found = _thumb_client.find(entity_type, [["id", "in", missing]], ["image"])
            except Exception:
                _thumb_client = None
                found = []
        urls = {r["id"]: r.get("image") for r in found}
        for entity_id in missing:
            url = urls.get(entity_id)
            if url and "no_preview" in url:
                url = None
            _thumb_cache[(entity_type, entity_id)] = (now + _THUMB_TTL, url)
            result[str(entity_id)] = url
    return result
