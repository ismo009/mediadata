"""Question -> relevant ShotGrid records + exact statistics, for the assistant.

The question is parsed into a structured scope (project, sequence, step, person, entity
type, status bucket, late/blocked flags). Records and statistics are then read with SQL
over the local cache, so totals are exact even when only a sample of records is sent to
the model.
"""
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Optional

from backend.db import database
from backend.records import (
    DONE_STATUSES, IN_PROGRESS_STATUSES, REVIEW_STATUSES, WAITING_STATUSES, present, status_bucket,
)

RECORD_LIMIT = 60

STOP_WORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "en", "au", "aux", "et", "ou",
    "qui", "que", "quoi", "dont", "est", "sont", "a", "ont", "ce", "ces", "cet", "cette",
    "quels", "quelles", "quel", "quelle", "comment", "pourquoi", "pour", "dans", "sur",
    "avec", "sans", "sous", "par", "actuel", "actuels", "actuelle", "actuellement", "projet",
    "projets", "donne", "moi", "affiche", "trouve", "faire", "tous", "toutes", "peux", "voir",
    "liste", "combien", "il", "y", "the", "an", "and", "or", "is", "are", "of", "to", "in",
    "on", "with", "for", "about", "all", "what", "which", "show", "list", "me", "my", "mes",
    "nos", "notre", "leur", "leurs", "son", "sa", "ses", "plus", "moins", "tache", "taches",
    "tâche", "tâches", "shot", "shots", "plan", "plans", "note", "notes",
}

TYPE_PATTERNS = [
    ("Task", r"\b(taches?|tasks?)\b"),
    ("Shot", r"\b(shots?|plans?)\b"),
    ("Asset", r"\b(assets?)\b"),
    ("Version", r"\b(versions?|dailies)\b"),
    ("Note", r"\b(notes?|retours?|feedbacks?|commentaires?)\b"),
    ("TimeLog", r"\b(temps (passe|saisi)|heures|time ?logs?|timesheets?)\b"),
    ("Playlist", r"\b(playlists?)\b"),
    ("PublishedFile", r"\b(publish(es|ed)?|fichiers? publies?)\b"),
    # Last: "les shots de la séquence X" asks for shots, not for the sequence itself.
    ("Sequence", r"\b(sequences?)\b"),
]

STATUS_PATTERNS = [
    # "open" = anything not finished; checked first ("tâches ouvertes", "restantes", "à faire").
    ("open", r"\b(ouverte?s?|open|restante?s?|non terminee?s?|pas terminee?s?|a faire|todo)\b"),
    ("waiting", r"\b(en attente|wtg|waiting|pas commence|rdy)\b"),
    ("in_progress", r"\b(en cours|ip|in progress|wip)\b"),
    ("review", r"\b(en review|review|rev|a valider|en validation|pending review)\b"),
    ("done", r"\b(termine(e|es|s)?|finis?|fin|approuve(e|es|s)?|apr|done|final(e|es|s)?)\b"),
]
BUCKET_CODES = {
    "waiting": WAITING_STATUSES,
    "in_progress": IN_PROGRESS_STATUSES,
    "review": REVIEW_STATUSES,
    "done": DONE_STATUSES,
}

LATE_RE = r"\b(retards?|en retard|late|overdue|depasse(e|es|s)?|echeances? depassee?s?)\b"
BLOCKED_RE = r"\b(bloque(e|es|s)?|blocked|blocages?|dependances?|bloquant(e|es|s)?)\b"
COUNT_RE = (
    r"\b(combien|nombre|how many|total|repartition|statistiques?|stats?|bilan|"
    r"le plus|le moins|classement|top|qui a)\b"
)
# Aggregate questions are answered from the exact stats: a short sample of items is enough.
COUNTING_RECORD_LIMIT = 10
# Ranking questions ("qui a le plus…") are answered only from the stats: listing items makes
# small models count the list instead of reading the ranking.
RANK_RE = r"\b(le plus|le moins|classement|top \d*|la plus|les plus)\b"
PROJECTS_RE = r"\b(projets?|projects?|productions?)\b"
ACTIVE_RE = r"\b(actif|actifs|active|actives|en cours|en production)\b"

DONE_SQL = ",".join(f"'{s}'" for s in sorted(DONE_STATUSES))


def normalize(text: str) -> str:
    """Lower-case, accent-free text so 'Tâches' matches 'taches'."""
    text = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in text if not unicodedata.combining(c))


@dataclass
class Scope:
    project: Optional[dict] = None
    sequence: Optional[dict] = None
    step: Optional[dict] = None
    person: Optional[dict] = None
    entity_type: Optional[str] = None
    bucket: Optional[str] = None
    late: bool = False
    blocked: bool = False
    counting: bool = False
    keywords: list[str] = field(default_factory=list)

    @property
    def structured(self) -> bool:
        return any([self.project, self.sequence, self.step, self.person, self.bucket,
                    self.late, self.blocked])

    def describe(self, target: Optional[str] = None) -> str:
        """Human (French) description of the scope, e.g. 'tâches, production « X », en retard'."""
        parts = []
        entity_type = target or self.entity_type
        if entity_type:
            parts.append(TYPE_LABELS.get(entity_type, entity_type))
        for label, value in (("production", self.project), ("séquence", self.sequence),
                             ("étape", self.step), ("personne", self.person)):
            if value:
                parts.append(f"{label} « {value['name']} »")
        if self.bucket:
            parts.append(BUCKET_LABELS[self.bucket])
        if self.late:
            parts.append("en retard (échéance dépassée, non terminées)")
        if self.blocked:
            parts.append("bloquées par une tâche amont non terminée")
        return ", ".join(parts) or "recherche libre"


TYPE_LABELS = {
    "Task": "tâches", "Shot": "plans", "Sequence": "séquences", "Asset": "assets", "Version": "versions",
    "Note": "notes", "TimeLog": "temps saisis", "Playlist": "playlists", "PublishedFile": "fichiers publiés",
    "Project": "productions", "HumanUser": "personnes",
}
BUCKET_LABELS = {
    "open": "non terminées", "waiting": "en attente", "in_progress": "en cours",
    "review": "en review", "done": "terminées",
}


# --------------------------------------------------------------------------- parsing

def _named(connection: sqlite3.Connection, entity_type: str) -> list[dict]:
    rows = connection.execute(
        "SELECT entity_id, name, data_json FROM shotgrid_records WHERE entity_type=? AND name IS NOT NULL",
        (entity_type,),
    ).fetchall()
    result = []
    by_name: dict[str, dict] = {}
    for row in rows:
        data = json.loads(row["data_json"])
        aliases = {normalize(row["name"])}
        if entity_type == "Step":
            # Several steps share a name (e.g. "Animation" for shots, assets and levels):
            # a step mentioned by name means all of them.
            if data.get("short_name"):
                aliases.add(normalize(data["short_name"]))
            existing = by_name.get(normalize(row["name"]))
            if existing:
                existing["ids"].append(row["entity_id"])
                existing["aliases"] |= aliases
                continue
        if entity_type == "HumanUser":
            if data.get("sg_status_list") == "dis":
                continue
            aliases.add(normalize(f"{data.get('firstname', '')} {data.get('lastname', '')}".strip()))
        candidate = {"id": row["entity_id"], "ids": [row["entity_id"]], "name": row["name"],
                     "aliases": aliases, "data": data}
        by_name[normalize(row["name"])] = candidate
        result.append(candidate)
    return result


def _find_in(question: str, candidates: list[dict], min_len: int = 3) -> Optional[dict]:
    """Longest candidate alias that appears as whole words in the (normalized) question."""
    best, best_len = None, 0
    for candidate in candidates:
        for alias in candidate["aliases"]:
            if len(alias) < min_len or len(alias) <= best_len:
                continue
            if re.search(rf"(?<![\w]){re.escape(alias)}(?![\w])", question):
                best, best_len = candidate, len(alias)
    return best


LEADING_ARTICLES = re.compile(r"^(les|des|le|la|l|du|de|d|the)\s+")
FUZZY_MIN_RATIO = 0.86
FUZZY_MIN_CHARS = 6


def _core(text: str) -> str:
    """Words only, no leading article: 'Les Cocottes en Papier' -> 'cocottes en papier'."""
    words = " ".join(re.findall(r"\w+", text))
    return LEADING_ARTICLES.sub("", words)


def _fuzzy_find(question: str, candidates: list[dict]) -> Optional[dict]:
    """Best candidate whose name approximately appears in the question (typos, other article).

    'des cocottes en pappier' matches 'Les Cocottes en Papier'. Each alias is compared with
    every window of the question of about the same number of words.
    """
    words = re.findall(r"\w+", question)
    best, best_score = None, FUZZY_MIN_RATIO
    for candidate in candidates:
        for alias in candidate["aliases"]:
            full = _core(alias)
            alias_words = full.split()
            # The full name, plus its leading words ("stranger things" for "Stranger Things - PXFK"),
            # slightly penalised so a full match always wins.
            variants = [(full, 1.0)] + [
                (" ".join(alias_words[:k]), 0.97) for k in range(2, len(alias_words))
            ]
            for core, weight in variants:
                if len(core) < FUZZY_MIN_CHARS:
                    continue
                n = len(core.split())
                for size in {max(1, n - 1), n, n + 1}:
                    for i in range(len(words) - size + 1):
                        chunk = _core(" ".join(words[i:i + size]))
                        if not chunk or abs(len(chunk) - len(core)) > max(3, len(core) // 4):
                            continue
                        score = SequenceMatcher(None, core, chunk).ratio() * weight
                        if score > best_score:
                            best, best_score = candidate, score
    return best


def _find_named(question: str, candidates: list[dict], min_len: int = 3) -> Optional[dict]:
    """Exact whole-word match first, then a tolerant match for typos."""
    return _find_in(question, candidates, min_len) or _fuzzy_find(question, candidates)


def _find_person(question: str, people: list[dict]) -> Optional[dict]:
    match = _find_named(question, people, min_len=5)
    if match:
        return match
    # A single first or last name (>= 4 letters) that identifies exactly one person.
    words = set(re.findall(r"\w{4,}", question))
    hits = []
    for person in people:
        tokens = {normalize(t) for t in (person["data"].get("firstname"), person["data"].get("lastname")) if t}
        if tokens & words:
            hits.append(person)
    return hits[0] if len(hits) == 1 else None


def parse_question(connection: sqlite3.Connection, question: str) -> Scope:
    q = normalize(question)
    scope = Scope()
    scope.project = _find_named(q, _named(connection, "Project"))
    scope.sequence = _find_in(q, _named(connection, "Sequence"))
    scope.step = _find_in(q, _named(connection, "Step"), min_len=3)
    scope.person = _find_person(q, _named(connection, "HumanUser"))
    for entity_type, pattern in TYPE_PATTERNS:
        if re.search(pattern, q):
            scope.entity_type = entity_type
            break
    for bucket, pattern in STATUS_PATTERNS:
        if re.search(pattern, q):
            scope.bucket = bucket
            break
    scope.late = bool(re.search(LATE_RE, q))
    scope.blocked = bool(re.search(BLOCKED_RE, q))
    scope.counting = bool(re.search(COUNT_RE, q))

    consumed = " ".join(
        normalize(x["name"]) for x in (scope.project, scope.sequence, scope.step, scope.person) if x
    )
    scope.keywords = [
        w for w in re.findall(r"[\w-]{3,}", q)
        if w not in STOP_WORDS and w not in consumed.split()
    ][:8]
    return scope


# --------------------------------------------------------------------------- SQL

def _filters(scope: Scope, entity_type: str) -> tuple[str, list[Any]]:
    clauses = ["r.entity_type = ?"]
    params: list[Any] = [entity_type]
    if scope.project and entity_type != "Project":
        clauses.append("r.project_id = ?")
        params.append(scope.project["id"])
    if scope.sequence:
        if entity_type == "Shot":
            clauses.append(
                "EXISTS (SELECT 1 FROM shotgrid_links l WHERE l.src_type='Shot' AND l.src_id=r.entity_id "
                "AND l.dst_type='Sequence' AND l.dst_id=?)"
            )
            params.append(scope.sequence["id"])
        elif entity_type != "Sequence":
            clauses.append(
                "EXISTS (SELECT 1 FROM shotgrid_links l WHERE l.src_type=r.entity_type AND l.src_id=r.entity_id "
                "AND ((l.dst_type='Sequence' AND l.dst_id=?) OR (l.dst_type='Shot' AND l.dst_id IN "
                "(SELECT src_id FROM shotgrid_links WHERE src_type='Shot' AND dst_type='Sequence' AND dst_id=?))))"
            )
            params.extend([scope.sequence["id"], scope.sequence["id"]])
    if scope.step:
        step_ids = scope.step.get("ids") or [scope.step["id"]]
        clauses.append(
            "EXISTS (SELECT 1 FROM shotgrid_links l WHERE l.src_type=r.entity_type AND l.src_id=r.entity_id "
            f"AND l.dst_type='Step' AND l.dst_id IN ({','.join('?' * len(step_ids))}))"
        )
        params.extend(step_ids)
    if scope.person:
        clauses.append(
            "EXISTS (SELECT 1 FROM shotgrid_links l WHERE l.src_type=r.entity_type AND l.src_id=r.entity_id "
            "AND l.dst_type='HumanUser' AND l.dst_id=?)"
        )
        params.append(scope.person["id"])
    if scope.bucket == "open":
        clauses.append(f"LOWER(COALESCE(r.status,'')) NOT IN ({DONE_SQL})")
    elif scope.bucket:
        codes = sorted(BUCKET_CODES[scope.bucket])
        marks = ",".join("?" * len(codes))
        null_ok = " OR r.status IS NULL" if scope.bucket == "waiting" else ""
        clauses.append(f"(LOWER(r.status) IN ({marks}){null_ok})")
        params.extend(codes)
    if scope.late:
        clauses.append(
            f"json_extract(r.data_json,'$.due_date') < date('now') "
            f"AND LOWER(COALESCE(r.status,'')) NOT IN ({DONE_SQL})"
        )
    if scope.blocked:
        clauses.append(
            f"LOWER(COALESCE(r.status,'')) NOT IN ({DONE_SQL}) AND EXISTS ("
            "SELECT 1 FROM shotgrid_links l JOIN shotgrid_records u "
            "ON u.entity_type='Task' AND u.entity_id=l.dst_id "
            "WHERE l.src_type=r.entity_type AND l.src_id=r.entity_id AND l.field='upstream_tasks' "
            f"AND LOWER(COALESCE(u.status,'')) NOT IN ({DONE_SQL}))"
        )
    return " AND ".join(clauses), params


ORDER_BY = {
    "Task": "CASE WHEN json_extract(r.data_json,'$.due_date') IS NULL THEN 1 ELSE 0 END, "
            "json_extract(r.data_json,'$.due_date'), r.name COLLATE NOCASE",
    "Note": "r.entity_id DESC",
    "Version": "r.entity_id DESC",
    "TimeLog": "json_extract(r.data_json,'$.date') DESC",
}


def _query(connection, scope: Scope, entity_type: str, limit: int) -> list[dict]:
    where, params = _filters(scope, entity_type)
    order = ORDER_BY.get(entity_type, "r.name COLLATE NOCASE")
    rows = connection.execute(
        f"SELECT r.entity_type, r.data_json FROM shotgrid_records r WHERE {where} ORDER BY {order} LIMIT ?",
        [*params, limit],
    ).fetchall()
    return [{"entity_type": row["entity_type"], **present(json.loads(row["data_json"]), row["entity_type"])}
            for row in rows]


def _stats(connection, scope: Scope, entity_type: str) -> dict[str, Any]:
    where, params = _filters(scope, entity_type)
    rows = connection.execute(
        f"SELECT r.status, COUNT(*) AS n FROM shotgrid_records r WHERE {where} GROUP BY r.status", params
    ).fetchall()
    by_status = {(row["status"] or "aucun"): row["n"] for row in rows}
    by_bucket: dict[str, int] = {}
    for status, n in by_status.items():
        bucket = status_bucket(None if status == "aucun" else status)
        by_bucket[bucket] = by_bucket.get(bucket, 0) + n
    stats: dict[str, Any] = {
        "entity_type": entity_type,
        "total": sum(by_status.values()),
        "par_statut": by_status,
        "par_groupe": by_bucket,
    }
    if entity_type == "Task":
        late = connection.execute(
            f"SELECT COUNT(*) FROM shotgrid_records r WHERE {where} AND "
            f"json_extract(r.data_json,'$.due_date') < date('now') "
            f"AND LOWER(COALESCE(r.status,'')) NOT IN ({DONE_SQL})",
            params,
        ).fetchone()[0]
        stats["en_retard"] = late
        groupings = [("par_etape", "Step", "step"), ("par_personne", "HumanUser", "task_assignees")]
        if not scope.project:
            groupings.append(("par_production", "Project", "project"))
        for label, dst_type, fld in groupings:
            grouped = connection.execute(
                f"""
                SELECT d.name AS name, COUNT(*) AS n FROM shotgrid_records r
                JOIN shotgrid_links l ON l.src_type=r.entity_type AND l.src_id=r.entity_id
                     AND l.dst_type=? AND l.field=?
                JOIN shotgrid_records d ON d.entity_type=? AND d.entity_id=l.dst_id
                WHERE {where} GROUP BY d.name ORDER BY n DESC LIMIT 12
                """,
                [dst_type, fld, dst_type, *params],
            ).fetchall()
            if grouped:
                stats[label] = {row["name"]: row["n"] for row in grouped}
    return stats


def _blocked_by(connection, task_ids: list[int]) -> dict[int, list[str]]:
    if not task_ids:
        return {}
    marks = ",".join("?" * len(task_ids))
    rows = connection.execute(
        f"""
        SELECT l.src_id, u.name, u.status FROM shotgrid_links l
        JOIN shotgrid_records u ON u.entity_type='Task' AND u.entity_id=l.dst_id
        WHERE l.src_type='Task' AND l.field='upstream_tasks' AND l.src_id IN ({marks})
          AND LOWER(COALESCE(u.status,'')) NOT IN ({DONE_SQL})
        """,
        task_ids,
    ).fetchall()
    result: dict[int, list[str]] = {}
    for row in rows:
        result.setdefault(row["src_id"], []).append(f"{row['name']} ({row['status'] or 'sans statut'})")
    return result


def _dedupe(records: list[dict]) -> list[dict]:
    seen, result = set(), []
    for record in records:
        key = (record.get("entity_type"), record.get("id"))
        if key not in seen:
            seen.add(key)
            result.append(record)
    return result


def _rows_to_records(rows) -> list[dict]:
    return [{"entity_type": row["entity_type"], **present(json.loads(row["data_json"]), row["entity_type"])}
            for row in rows]


def _fulltext(connection, keywords: list[str], limit: int, entity_type: Optional[str] = None) -> list[dict]:
    if not keywords:
        return []
    fts_query = " OR ".join(f'"{w}"*' for w in keywords)
    type_clause = "AND r.entity_type = ?" if entity_type else ""
    params = [fts_query, *([entity_type] if entity_type else []), limit]
    try:
        rows = connection.execute(
            f"""
            SELECT r.entity_type, r.data_json FROM shotgrid_fts f
            JOIN shotgrid_records r ON r.rowid = f.rowid
            WHERE shotgrid_fts MATCH ? {type_clause} ORDER BY rank LIMIT ?
            """,
            params,
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return _rows_to_records(rows)


# --------------------------------------------------------------------------- entry point

def retrieve(question: str, limit: int = RECORD_LIMIT) -> dict[str, Any]:
    """Return {'scope': str, 'stats': dict|None, 'records': [...]} for a question."""
    connection = database()
    try:
        q = normalize(question)

        # Exact note lookup: "note #1234"
        note_id = re.search(r"\bnote\s*#?\s*(\d+)\b", q)
        if note_id:
            row = connection.execute(
                "SELECT entity_type, data_json FROM shotgrid_records WHERE entity_type='Note' AND entity_id=?",
                (int(note_id.group(1)),),
            ).fetchone()
            if row:
                return {"scope": f"note {note_id.group(1)}", "stats": None, "records": _rows_to_records([row])}

        scope = parse_question(connection, question)
        ranking = bool(re.search(RANK_RE, q))
        if scope.counting:
            limit = min(limit, COUNTING_RECORD_LIMIT)
        mentions_projects = bool(re.search(PROJECTS_RE, q))

        # General question about projects as a collection ("quels sont les projets actifs ?").
        about_tasks_of_something = any([scope.project, scope.sequence, scope.step, scope.person,
                                        scope.late, scope.blocked])
        if mentions_projects and scope.entity_type is None and not about_tasks_of_something:
            rows = connection.execute(
                "SELECT entity_type, data_json FROM shotgrid_records WHERE entity_type='Project' "
                "ORDER BY name COLLATE NOCASE"
            ).fetchall()
            records = _rows_to_records(rows)
            _add_task_counts(connection, records)
            active = [r for r in records if r.get("is_active")]
            only_active = bool(re.search(ACTIVE_RE, q)) or scope.bucket in ("open", "in_progress")
            return {
                "scope": "productions actives" if only_active else "toutes les productions",
                "stats": {"entity_type": "Project", "total": len(records), "actifs": len(active),
                          "non_actifs": len(records) - len(active)},
                "records": active if only_active else records,
            }

        # "notes sur le flou": a type plus free words -> full-text search within that type.
        if scope.entity_type and not scope.structured and scope.keywords:
            hits = _fulltext(connection, scope.keywords, limit, scope.entity_type)
            if hits:
                return {"scope": f"{TYPE_LABELS.get(scope.entity_type, scope.entity_type)} contenant : "
                                 + ", ".join(scope.keywords),
                        "stats": None, "records": hits}

        if scope.structured or scope.entity_type:
            target = scope.entity_type
            if target is None:
                if scope.late or scope.blocked or scope.bucket or scope.step or scope.person:
                    target = "Task"
                elif scope.sequence:
                    target = "Shot"
            records: list[dict] = []
            stats = None
            if scope.project and not scope.sequence and target is None:
                # A project on its own: a production snapshot.
                records.append({"entity_type": "Project",
                                **present(connection_project(connection, scope.project["id"]), "Project")})
                stats = {"taches": _stats(connection, scope, "Task"),
                         "shots": _stats(connection, scope, "Shot")}
                late_scope = Scope(project=scope.project, late=True)
                records += _query(connection, late_scope, "Task", 25)
                review_scope = Scope(project=scope.project, bucket="review")
                records += _query(connection, review_scope, "Task", 15)
                records += _query(connection, Scope(project=scope.project), "Note", 10)
                records += _query(connection, Scope(project=scope.project), "Sequence", 20)
            elif target:
                if scope.project and target != "Project":
                    records.append({"entity_type": "Project",
                                    **present(connection_project(connection, scope.project["id"]), "Project")})
                if scope.sequence and target != "Sequence":
                    records.append(_one(connection, "Sequence", scope.sequence["id"]))
                records += _query(connection, scope, target, limit)
                stats = _stats(connection, scope, target)
            records = [r for r in records if r]
            if any(r["entity_type"] == "Task" for r in records):
                blocked = _blocked_by(connection, [r["id"] for r in records if r["entity_type"] == "Task"])
                for record in records:
                    if record["entity_type"] == "Task" and record["id"] in blocked:
                        record["blocked_by"] = blocked[record["id"]]
            records = _dedupe([r for r in records if r])
            if ranking and stats and "taches" not in stats:
                # Keep only the context records (project/sequence), not the ranked items.
                records = [r for r in records if r["entity_type"] in ("Project", "Sequence")]
            if records or stats:
                for record in records:
                    if record["entity_type"] == "Project":
                        _add_task_counts(connection, [record])
                label = (f"synthèse de la production « {scope.project['name']} »"
                         if scope.project and not scope.sequence and target is None else scope.describe(target))
                return {"scope": label, "stats": stats, "records": records}

        # Free text.
        records = _fulltext(connection, scope.keywords, limit)
        if not records:
            pattern = f"%{question.strip()}%"
            rows = connection.execute(
                "SELECT entity_type, data_json FROM shotgrid_records WHERE name LIKE ? "
                "ORDER BY name COLLATE NOCASE LIMIT ?",
                (pattern, limit),
            ).fetchall()
            records = _rows_to_records(rows)
        return {"scope": "recherche plein texte : " + ", ".join(scope.keywords), "stats": None,
                "records": _dedupe(records)}
    finally:
        connection.close()


def _add_task_counts(connection, projects: list[dict]) -> None:
    """Attach tasks_total / tasks_open / tasks_late to project records (for the model)."""
    rows = connection.execute(
        f"""
        SELECT project_id, COUNT(*) AS total,
               SUM(CASE WHEN LOWER(COALESCE(status,'')) NOT IN ({DONE_SQL}) THEN 1 ELSE 0 END) AS open,
               SUM(CASE WHEN json_extract(data_json,'$.due_date') < date('now')
                        AND LOWER(COALESCE(status,'')) NOT IN ({DONE_SQL}) THEN 1 ELSE 0 END) AS late
        FROM shotgrid_records WHERE entity_type='Task' GROUP BY project_id
        """
    ).fetchall()
    by_project = {r["project_id"]: r for r in rows}
    for project in projects:
        row = by_project.get(project["id"])
        project["tasks_total"] = row["total"] if row else 0
        project["tasks_open"] = row["open"] if row else 0
        project["tasks_late"] = row["late"] if row else 0


def subject_names(question: str) -> list[str]:
    """Names of the production, sequence and person the question is about (if any)."""
    connection = database()
    try:
        scope = parse_question(connection, question)
    finally:
        connection.close()
    return [x["name"] for x in (scope.project, scope.sequence, scope.person) if x]


def connection_project(connection, project_id: int) -> dict:
    row = connection.execute(
        "SELECT data_json FROM shotgrid_records WHERE entity_type='Project' AND entity_id=?", (project_id,)
    ).fetchone()
    return json.loads(row["data_json"]) if row else {"id": project_id}


def _one(connection, entity_type: str, entity_id: int) -> Optional[dict]:
    row = connection.execute(
        "SELECT entity_type, data_json FROM shotgrid_records WHERE entity_type=? AND entity_id=?",
        (entity_type, entity_id),
    ).fetchone()
    return _rows_to_records([row])[0] if row else None
