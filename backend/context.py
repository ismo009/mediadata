"""Render retrieval results as plain French text for the language model.

Small local models (8B) read short labelled lines far more reliably than nested JSON:
every status is already translated, every date already compared with today, and the
exact totals come first, clearly separated from the (possibly truncated) list of items.
"""
from datetime import date
from typing import Any, Optional

from backend.records import is_late, record_status, status_bucket

BUCKET_FR = {
    "done": "Terminé", "review": "En review", "in_progress": "En cours",
    "waiting": "En attente", "other": "Autre",
}
TYPE_FR = {
    "Project": "Production", "Task": "Tâche", "Shot": "Plan", "Sequence": "Séquence", "Asset": "Asset",
    "Version": "Version", "Note": "Note", "Reply": "Réponse", "HumanUser": "Personne", "TimeLog": "Temps saisi",
    "Playlist": "Playlist", "PublishedFile": "Fichier publié", "Attachment": "Fichier", "Step": "Étape",
}
TYPE_FR_PLURAL = {
    "Project": "productions", "Task": "tâches", "Shot": "plans", "Sequence": "séquences", "Asset": "assets",
    "Version": "versions", "Note": "notes", "TimeLog": "temps saisis", "Playlist": "playlists",
}
MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
STATS_LABELS = {"par_etape": "Par étape", "par_personne": "Par personne", "par_production": "Par production"}


def fr_date(value: Any) -> str:
    try:
        d = date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value)
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def _name(value: Any) -> Optional[str]:
    if isinstance(value, dict):
        return value.get("name") or value.get("code")
    return value if isinstance(value, str) and value else None


def _names(value: Any) -> list[str]:
    items = value if isinstance(value, list) else [value]
    return [n for n in (_name(v) for v in items) if n]


def status_text(code: Optional[str], labels: dict[str, dict]) -> str:
    if not code:
        return "sans statut"
    bucket = BUCKET_FR[status_bucket(code)]
    name = (labels.get(code) or {}).get("name")
    return f"{bucket} ({name})" if name and name.casefold() != bucket.casefold() else bucket


def _clip(text: Any, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def record_line(record: dict[str, Any], labels: dict[str, dict], today: date, long_text: bool) -> str:
    """One item as a single line of 'label : value' fields."""
    kind = record.get("entity_type") or record.get("type") or "?"
    if kind == "Task":
        name = record.get("content") or record.get("name")
    else:
        name = record.get("name") or record.get("code") or record.get("subject") or record.get("cached_display_name")
    fields = [f"{TYPE_FR.get(kind, kind)} « {name or '#' + str(record.get('id'))} »"]

    if kind == "Project":
        fields.append(record.get("status_label") or "")
        if record.get("start_date") or record.get("end_date"):
            fields.append(f"du {fr_date(record['start_date']) if record.get('start_date') else '?'} "
                          f"au {fr_date(record['end_date']) if record.get('end_date') else '?'}")
        if "tasks_total" in record:
            fields.append(f"{record['tasks_total']} tâches dont {record['tasks_open']} non terminées "
                          f"et {record['tasks_late']} en retard")
        return " — ".join(f for f in fields if f)

    project = _name(record.get("project"))
    for label, key in (("élément", "entity"), ("séquence", "sg_sequence"), ("étape", "step")):
        value = _name(record.get(key))
        if value:
            fields.append(f"{label} : {value}")
    assignees = _names(record.get("task_assignees"))
    if assignees:
        fields.append("assignée à : " + ", ".join(assignees))
    elif kind == "Task":
        fields.append("non assignée")
    user = _name(record.get("user"))
    if user:
        fields.append(f"par : {user}")
    if kind != "Project" and (record_status(record) or kind in ("Task", "Shot", "Asset", "Version")):
        fields.append("statut : " + status_text(record_status(record), labels))
    if record.get("due_date"):
        due = f"échéance : {fr_date(record['due_date'])}"
        if is_late(record, today):
            days = (today - date.fromisoformat(str(record["due_date"])[:10])).days
            due += f" (EN RETARD de {days} jour{'s' if days > 1 else ''})"
        fields.append(due)
    if record.get("blocked_by"):
        fields.append("bloquée par : " + "; ".join(record["blocked_by"]))
    if kind == "TimeLog" and isinstance(record.get("duration"), (int, float)):
        fields.append(f"durée : {round(record['duration'] / 60, 2)} h")
    if record.get("date"):
        fields.append(f"date : {fr_date(record['date'])}")
    if kind in ("Note", "Version", "Reply") and record.get("created_at"):
        fields.append(f"le {fr_date(record['created_at'])}")
    links = _names(record.get("note_links"))
    if links:
        fields.append("concerne : " + ", ".join(links[:5]))
    if project:
        fields.append(f"production : {project}")
    if kind != "Task" and record.get("content"):
        fields.append("texte : " + _clip(record["content"], 1200 if long_text else 300))
    description = record.get("description") or record.get("sg_description")
    if description:
        fields.append("description : " + _clip(description, 200))
    return " — ".join(fields)


def _counts(mapping: dict[str, int]) -> str:
    return ", ".join(f"{k} : {v}" for k, v in mapping.items())


def stats_lines(stats: dict[str, Any], labels: dict[str, dict]) -> list[str]:
    kind = stats.get("entity_type")
    if kind == "Project":
        return [f"- {stats['total']} productions au total, dont {stats['actifs']} actives "
                f"et {stats['non_actifs']} non actives (archivées, templates ou terminées)."]
    noun = TYPE_FR_PLURAL.get(kind, kind)
    lines = [f"- Nombre total de {noun} correspondant à la recherche : {stats['total']}"]
    groups = {BUCKET_FR[k]: v for k, v in sorted(stats.get("par_groupe", {}).items(),
                                                 key=lambda kv: -kv[1])}
    if groups:
        lines.append(f"- Par état : {_counts(groups)}")
    detail = {
        (labels.get(code) or {}).get("name", code): n
        for code, n in sorted(stats.get("par_statut", {}).items(), key=lambda kv: -kv[1])
    }
    if len(detail) > 1:
        lines.append(f"- Par statut ShotGrid : {_counts(detail)}")
    if "en_retard" in stats:
        lines.append(f"- En retard (échéance dépassée et non terminées) : {stats['en_retard']}")
    for key, label in STATS_LABELS.items():
        if stats.get(key):
            ranked = " ; ".join(f"{i}) {name} : {n}" for i, (name, n) in enumerate(stats[key].items(), 1))
            lines.append(f"- {label}, classement du plus grand au plus petit : {ranked}")
    return lines


def render_context(found: dict[str, Any], labels: dict[str, dict], drive: list[dict],
                   today: Optional[date] = None, long_text: bool = False, user=None) -> str:
    today = today or date.today()
    out = [f"DATE DU JOUR : {fr_date(today.isoformat())}"]
    if user is not None:
        access = ("toutes les productions" if user.sees_all
                  else "uniquement les productions dont cette personne est membre")
        out.append(f"UTILISATEUR CONNECTÉ : {user.name} ({user.role or 'sans rôle'}) ; "
                   f"données visibles : {access}")
    out += [f"RECHERCHE EFFECTUÉE : {found['scope']}", ""]

    stats = found.get("stats")
    if stats:
        out.append("CHIFFRES EXACTS (calculés sur toute la base ; utilise-les pour tout total) :")
        if "taches" in stats:  # project snapshot
            out.append("Tâches de la production :")
            out += stats_lines(stats["taches"], labels)
            out.append("Plans de la production :")
            out += stats_lines(stats["shots"], labels)
        else:
            out += stats_lines(stats, labels)
        out.append("")

    records = found.get("records") or []
    if records:
        header = f"ÉLÉMENTS TROUVÉS ({len(records)} affichés"
        # Say explicitly when the list is a sample of a larger exact total.
        main_type = stats.get("entity_type") if stats and "taches" not in stats else None
        if main_type and main_type != "Project":
            shown = sum(1 for r in records if r.get("entity_type") == main_type)
            if stats["total"] > shown:
                header += (f" ; liste PARTIELLE : seulement {shown} {TYPE_FR_PLURAL.get(main_type, main_type)}"
                           f" sur {stats['total']}")
        out.append(header + ") :")
        for i, record in enumerate(records, 1):
            out.append(f"{i}. {record_line(record, labels, today, long_text)}")
    elif stats:
        out.append("ÉLÉMENTS TROUVÉS : non listés ; réponds avec les CHIFFRES EXACTS ci-dessus.")
    else:
        out.append("ÉLÉMENTS TROUVÉS : aucun élément ne correspond dans la base ShotGrid locale.")

    if drive:
        out += ["", "FICHIERS GOOGLE DRIVE (trouvés par leur nom) :"]
        out += [f"- {f.get('name')} ({f.get('mimeType', '').split('.')[-1]})" for f in drive]
    return "\n".join(out)
