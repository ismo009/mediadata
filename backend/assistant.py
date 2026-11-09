"""Assistant endpoint: retrieval + Google Drive search + streamed Ollama answer."""
import asyncio
import json
import re
from typing import Any, AsyncGenerator, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend import config
from backend.api import status_labels
from backend.auth import google_access_token
from backend.context import render_context
from backend.prompt import SYSTEM_PROMPT
from backend.retrieval import STOP_WORDS, normalize, retrieve, subject_names

router = APIRouter()


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[dict[str, Any]] = Field(default_factory=list, max_length=30)
    model: Optional[str] = None


def _name(value: Any) -> Optional[str]:
    if isinstance(value, dict):
        return value.get("name") or value.get("code")
    return value if isinstance(value, str) else None


def _names(value: Any) -> list[str]:
    if isinstance(value, list):
        return [n for n in (_name(v) for v in value) if n]
    single = _name(value)
    return [single] if single else []


def compact_record_for_llm(record: dict[str, Any], entity_type: str, long_text: bool = False) -> dict[str, Any]:
    """Keep only the business fields of a record, to fit many records in the context window."""
    compact: dict[str, Any] = {"type": entity_type, "id": record.get("id")}
    if entity_type == "Task":
        compact["name"] = record.get("content") or record.get("name")
    else:
        compact["name"] = (record.get("name") or record.get("code") or record.get("subject")
                           or record.get("cached_display_name"))

    if entity_type == "Project":
        compact["status"] = record.get("status_label")
        compact["is_active"] = record.get("is_active")
    else:
        status = record.get("sg_status_list") or record.get("sg_status")
        if status:
            compact["status"] = status
        if record.get("project"):
            compact["project"] = _name(record["project"])

    for key, label in (("step", "step"), ("entity", "entity"), ("sg_sequence", "sequence"),
                       ("user", "user")):
        if record.get(key):
            compact[label] = _name(record[key])
    for key, label in (("task_assignees", "assigned_to"), ("note_links", "links"),
                       ("addressings_to", "to")):
        names = _names(record.get(key))
        if names:
            compact[label] = names

    text_limit = 1500 if long_text else 400
    if entity_type != "Task" and record.get("content"):
        compact["content"] = str(record["content"])[:text_limit]
    if record.get("subject") and compact.get("name") != record["subject"]:
        compact["subject"] = record["subject"]
    for key in ("description", "sg_description"):
        if record.get(key):
            compact["description"] = str(record[key])[:300]
            break

    for key in ("start_date", "due_date", "end_date", "date"):
        if record.get(key):
            compact[key] = record[key]
    if entity_type in ("Note", "Version", "Reply") and record.get("created_at"):
        compact["created_at"] = str(record["created_at"])[:16]
    if entity_type == "TimeLog" and isinstance(record.get("duration"), (int, float)):
        compact["duration_hours"] = round(record["duration"] / 60, 2)
    if record.get("late"):
        compact["late"] = True
    if record.get("blocked_by"):
        compact["blocked_by"] = record["blocked_by"]
    if record.get("source_url"):
        compact["source_url"] = record["source_url"]
    return compact


async def search_drive(access_token: Optional[str], question: str) -> list[dict[str, Any]]:
    if not access_token:
        return []
    words = [w for w in re.findall(r"[\w-]{3,}", normalize(question)) if w not in STOP_WORDS][:3]
    if not words:
        return []
    query = "trashed = false and (" + " or ".join(
        "name contains '{}'".format(w.replace("\\", "\\\\").replace("'", "\\'")) for w in words
    ) + ")"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                "https://www.googleapis.com/drive/v3/files",
                params={"q": query, "pageSize": 15, "fields": "files(id,name,mimeType,webViewLink)"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if response.status_code < 400:
            return response.json().get("files", [])
    except httpx.HTTPError:
        pass
    return []


async def list_models() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{config.settings.ollama_url}/api/tags")
        if resp.status_code == 200:
            models = [m.get("name") for m in resp.json().get("models", [])]
            return {"models": models, "default": config.settings.ollama_model or (models[0] if models else "")}
    except httpx.HTTPError:
        pass
    return {"models": [], "default": config.settings.ollama_model}


@router.get("/api/models")
async def models() -> dict[str, Any]:
    return await list_models()


def _stat_codes(stats: Any) -> list[str]:
    """Every status code mentioned in a (possibly nested) stats dict."""
    if not isinstance(stats, dict):
        return []
    codes = list((stats.get("par_statut") or {}).keys())
    for value in stats.values():
        if isinstance(value, dict) and "par_statut" in value:
            codes += list(value["par_statut"].keys())
    return codes


HISTORY_MESSAGES = 6
HISTORY_ANSWER_CHARS = 700


def build_messages(payload: QueryRequest, context: str) -> list[dict[str, str]]:
    """System prompt, a short conversation history, then DONNÉES + QUESTION.

    Past answers are truncated: they only serve to resolve follow-ups ("et ses tâches ?"),
    the facts always come from the fresh DONNÉES block.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in payload.history[-HISTORY_MESSAGES:]:
        role = msg.get("role") if msg.get("role") in ("user", "assistant") else "user"
        content = str(msg.get("content", ""))
        if role == "assistant" and len(content) > HISTORY_ANSWER_CHARS:
            content = content[:HISTORY_ANSWER_CHARS] + "…"
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": f"DONNÉES :\n{context}\n\nQUESTION : {payload.question}"})
    return messages


FOLLOW_UP_MAX_WORDS = 10


def retrieval_question(payload: QueryRequest) -> str:
    """Follow-ups inherit their subject from the conversation.

    "et combien sont en retard ?" after "Où en est Les Cocottes en Papier ?" is searched as
    "et combien sont en retard ? Les Cocottes en Papier": only the subject (production,
    sequence, person) is carried over, not the previous filters.
    """
    question = payload.question.strip()
    if not payload.history or len(question.split()) > FOLLOW_UP_MAX_WORDS or subject_names(question):
        return question
    for message in reversed(payload.history):
        if message.get("role") == "user":
            names = subject_names(str(message.get("content", "")))
            if names:
                return f"{question} {' '.join(names)}"
    return question


@router.post("/api/query/stream")
async def query_stream(request: Request, payload: QueryRequest):
    search_q = retrieval_question(payload)
    found, drive = await asyncio.gather(
        asyncio.to_thread(retrieve, search_q),
        search_drive(google_access_token(request), payload.question),
    )
    long_text = bool(re.search(r"\b(notes?|retours?|feedbacks?)\b", normalize(search_q)))
    shotgrid_records = [
        compact_record_for_llm(r, r.get("entity_type", "Unknown"), long_text) for r in found["records"]
    ]
    used_codes = {r.get("status") for r in shotgrid_records} | set(_stat_codes(found["stats"]))
    labels = await asyncio.to_thread(status_labels)
    sources = {
        "scope": found["scope"],
        "stats": found["stats"],
        "status_labels": {code: v["name"] for code, v in labels.items() if code in used_codes},
        "shotgrid": shotgrid_records,
        "google_drive": drive,
    }

    model = payload.model or config.settings.ollama_model
    if not model:
        available = (await list_models())["models"]
        if not available:
            raise HTTPException(status_code=503, detail="Aucun modèle Ollama disponible.")
        model = available[0]

    context = render_context(found, labels, drive, long_text=long_text)
    messages = build_messages(payload, context)

    async def event_generator() -> AsyncGenerator[str, None]:
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources}, ensure_ascii=False, default=str)}\n\n"
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                async with client.stream(
                    "POST",
                    f"{config.settings.ollama_url}/api/chat",
                    json={
                        "model": model,
                        "messages": messages,
                        "stream": True,
                        # Factual answers: low temperature; context large enough for data + history.
                        "options": {"temperature": 0.2, "num_ctx": config.settings.ollama_num_ctx},
                    },
                ) as response:
                    if response.status_code >= 400:
                        err_text = (await response.aread()).decode(errors="replace")
                        yield f"data: {json.dumps({'type': 'error', 'error': f'Erreur Ollama : {err_text}'})}\n\n"
                        return
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            yield f"data: {json.dumps({'type': 'token', 'token': token}, ensure_ascii=False)}\n\n"
                        if chunk.get("done"):
                            break
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except httpx.HTTPError as exc:
            message = (f"Ollama est injoignable sur {config.settings.ollama_url}. "
                       f"Lancez « ollama serve » puis réessayez. ({type(exc).__name__})")
            yield f"data: {json.dumps({'type': 'error', 'error': message}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
