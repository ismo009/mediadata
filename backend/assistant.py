"""Assistant endpoint: retrieval + Google Drive search + streamed Ollama answer."""
import asyncio
import json
import re
from typing import Any, AsyncGenerator, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend import config
from backend.api import status_labels
from backend.auth import google_access_token, require_user
from backend.context import render_context
from backend.prompt import SYSTEM_PROMPT
from backend.users import User
from backend.retrieval import STOP_WORDS, normalize, retrieve, subject_names

router = APIRouter()


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[dict[str, Any]] = Field(default_factory=list, max_length=30)
    model: Optional[str] = None


def source_item(record: dict[str, Any]) -> dict[str, Any]:
    """What the UI's source list needs for one record: type, id, display name, ShotGrid link."""
    kind = record.get("entity_type") or record.get("type")
    name = (record.get("content") if kind == "Task" else None) or record.get("name") or record.get("code")         or record.get("subject") or record.get("cached_display_name")
    return {"type": kind, "id": record.get("id"), "name": name, "source_url": record.get("source_url")}


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
async def models(_user: User = Depends(require_user)) -> dict[str, Any]:
    return await list_models()


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


def retrieval_question(payload: QueryRequest, user=None) -> str:
    """Follow-ups inherit their subject from the conversation.

    "et combien sont en retard ?" after "Où en est Les Cocottes en Papier ?" is searched as
    "et combien sont en retard ? Les Cocottes en Papier": only the subject (production,
    sequence, person) is carried over, not the previous filters.
    """
    question = payload.question.strip()
    if not payload.history or len(question.split()) > FOLLOW_UP_MAX_WORDS or subject_names(question, user):
        return question
    for message in reversed(payload.history):
        if message.get("role") == "user":
            names = subject_names(str(message.get("content", "")), user)
            if names:
                return f"{question} {' '.join(names)}"
    return question


@router.post("/api/query/stream")
async def query_stream(request: Request, payload: QueryRequest, user: User = Depends(require_user)):
    search_q = retrieval_question(payload, user)
    found, drive = await asyncio.gather(
        asyncio.to_thread(retrieve, search_q, user=user),
        search_drive(google_access_token(request), payload.question),
    )
    long_text = bool(re.search(r"\b(notes?|retours?|feedbacks?)\b", normalize(search_q)))
    labels = await asyncio.to_thread(status_labels)
    # Sent to the UI for the "sources" list under the answer.
    sources = {
        "scope": found["scope"],
        "stats": found["stats"],
        "shotgrid": [source_item(r) for r in found["records"]],
        "google_drive": drive,
    }

    model = payload.model or config.settings.ollama_model
    if not model:
        available = (await list_models())["models"]
        if not available:
            raise HTTPException(status_code=503, detail="Aucun modèle Ollama disponible.")
        model = available[0]

    context = render_context(found, labels, drive, long_text=long_text, user=user)
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
