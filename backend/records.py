"""Pure helpers that turn a raw ShotGrid record into the columns we index locally."""
import json
from datetime import date
from typing import Any, Iterator, Optional

from backend import config

# Text fields worth full-text indexing, when present on a record.
FTS_CONTENT_FIELDS = (
    "subject", "content", "description", "sg_description", "code",
    "filename", "sg_status_list", "tag_list",
)
# Entity links that only add noise to the relation graph.
SKIPPED_LINK_FIELDS = {"created_by", "updated_by", "image_source_entity"}

# Status codes grouped by meaning (codes from this site's Status entity included).
# DONE = the work is finished or accepted: never "late" and never "blocking".
DONE_STATUSES = {
    "fin", "apr", "cmpt", "clsd", "na", "omt", "cbb", "dlvr", "vwd", "res", "cfrm", "recd",
    "valide",   # Validé
    "cliapp",   # Client Approved
    "intapp",   # Internally approved
}
REVIEW_STATUSES = {"rev", "av", "rsb", "pub"}  # av = A valider
IN_PROGRESS_STATUSES = {"ip", "act", "wip", "ren", "rtk", "tr"}  # rtk = retake, tr = Tout roule
WAITING_STATUSES = {"wtg", "rdy", "rdysta", "hld", "opn", "pndng"}

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


def record_name(record: dict[str, Any]) -> Optional[str]:
    """Human name of a record. Tasks keep their name in `content`."""
    for key in ("name", "code", "cached_display_name", "subject", "filename"):
        value = record.get(key)
        if value:
            return str(value)
    if record.get("type") == "Task" and record.get("content"):
        return str(record["content"])
    return None


def record_status(record: dict[str, Any]) -> Optional[str]:
    return record.get("sg_status_list") or record.get("sg_status")


def record_project_id(entity_type: str, record: dict[str, Any]) -> Optional[int]:
    if entity_type == "Project":
        return record["id"]
    proj = record.get("project")
    return proj["id"] if isinstance(proj, dict) and "id" in proj else None


def fts_content(record: dict[str, Any]) -> str:
    return " ".join(str(record[k]) for k in FTS_CONTENT_FIELDS if record.get(k))


def iter_links(record: dict[str, Any]) -> Iterator[tuple[str, str, int]]:
    """Yield (field, target_type, target_id) for every entity link held by the record."""
    for field_name, value in record.items():
        if field_name in SKIPPED_LINK_FIELDS or field_name == "type":
            continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, dict) and isinstance(item.get("id"), int) and item.get("type"):
                yield field_name, item["type"], item["id"]


def record_row(entity_type: str, record: dict[str, Any], now: str) -> tuple:
    return (
        entity_type,
        record["id"],
        record_name(record),
        record_project_id(entity_type, record),
        record_status(record),
        json.dumps(record, default=str),
        now,
    )


def status_bucket(status: Optional[str]) -> str:
    """Group the many ShotGrid status codes into the five buckets the UI shows."""
    s = (status or "").casefold()
    if s in DONE_STATUSES:
        return "done"
    if s in REVIEW_STATUSES:
        return "review"
    if s in IN_PROGRESS_STATUSES:
        return "in_progress"
    if s in WAITING_STATUSES or not s:
        return "waiting"
    return "other"


def is_late(record: dict[str, Any], today: Optional[date] = None) -> bool:
    due = record.get("due_date")
    if not due or (record_status(record) or "").casefold() in DONE_STATUSES:
        return False
    try:
        return date.fromisoformat(str(due)[:10]) < (today or date.today())
    except ValueError:
        return False


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


def present(record: dict[str, Any], entity_type: Optional[str] = None) -> dict[str, Any]:
    """Record as returned by the API: adds its ShotGrid URL and, for projects, its state."""
    result = dict(record)
    record_type = entity_type or result.get("type")
    if record_type and result.get("id") and config.settings.shotgrid_url:
        result["source_url"] = f"{config.settings.shotgrid_url}/detail/{record_type}/{result['id']}"
    if record_type == "Project":
        result["status_label"], result["is_active"] = project_state(result)
    elif "due_date" in result:
        result["late"] = is_late(result)
    return result
