"""FastAPI router for AgentForge — agent CRUD, file upload, KB ingestion."""
from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile
from pydantic import BaseModel

from .store import store
from .models import Agent

log = logging.getLogger(__name__)

router = APIRouter(tags=["agents"])

# Per-agent uploaded files live here: data/agent_files/<agent_id>/
_FILES_ROOT = Path(
    os.environ.get("AGENT_FILES_ROOT")
    or str(Path(__file__).resolve().parent.parent / "data" / "agent_files")
)

# In-memory ingest status (agent_id → dict).  Lightweight — no Redis needed.
_ingest_status: dict[str, dict] = {}

# Default Chainlit chat URL base (override with CHAINLIT_URL env var)
_CHAINLIT_URL = os.environ.get("CHAINLIT_URL", "http://localhost:8080")


# ── Request / Response schemas ───────────────────────────────────────────────

class CreateAgentRequest(BaseModel):
    name: str
    title: str = ""
    description: str = ""
    system_prompt: str = ""
    llm_provider: str = "ollama"
    llm_model: str = ""
    llm_api_key: str = ""
    llm_api_base: str = ""
    embed_model: str = ""
    vector_db: str = "weaviate"
    vector_db_url: str = ""
    vector_db_api_key: str = ""


class UpdateAgentRequest(BaseModel):
    name: str | None = None
    title: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_api_base: str | None = None
    embed_model: str | None = None
    status: str | None = None
    vector_db: str | None = None
    vector_db_url: str | None = None
    vector_db_api_key: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _agent_files_dir(agent_id: str) -> Path:
    d = _FILES_ROOT / agent_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _require_agent(agent_id: str) -> Agent:
    agent = store.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return agent


def _drop_collection(collection_name: str, vector_db: str = "weaviate",
                     vector_db_url: str = "", vector_db_api_key: str = "") -> None:
    try:
        from tibco_agent.vectorstore.factory import get_adapter
        adapter = get_adapter(vector_db, vector_db_url, vector_db_api_key)
        adapter.delete_collection(collection_name)
    except Exception as exc:
        log.warning("Could not drop collection %s (%s): %s", collection_name, vector_db, exc)


def _run_ingest(
    agent_id: str,
    collection_name: str,
    files_dir: Path,
    vector_db: str = "weaviate",
    vector_db_url: str = "",
    vector_db_api_key: str = "",
) -> None:
    """Background task: ingest all files + URLs for the agent's collection."""
    _ingest_status[agent_id] = {"status": "ingesting", "chunks": 0, "error": None,
                                 "started_at": datetime.now(timezone.utc).isoformat()}
    store.set_status(agent_id, "ingesting")
    try:
        from tibco_agent.ingest.pipeline import IngestionPipeline
        from tibco_agent.ingest.sources.file_source import FileSource
        from tibco_agent.ingest.sources.web_source import WebSource

        pipeline = IngestionPipeline(
            chunk_size=300,
            chunk_overlap=50,
            collection_name=collection_name,
            vector_db=vector_db,
            vector_db_url=vector_db_url,
            vector_db_api_key=vector_db_api_key,
        )

        # Files
        has_files = files_dir.exists() and any(files_dir.iterdir())
        if has_files:
            pipeline.add_source(FileSource(path=str(files_dir), glob_pattern="**/*"))

        # URLs stored in the agent_urls table
        urls = store.get_urls_for_agent(agent_id)
        if urls:
            pipeline.add_source(WebSource(urls=urls, name=f"agent-{agent_id[:8]}-web"))

        chunks = pipeline.run(reset=True)

        finished_at = datetime.now(timezone.utc).isoformat()
        _ingest_status[agent_id].update({"status": "ready", "chunks": chunks,
                                          "finished_at": finished_at})
        store.record_ingest(agent_id, chunks)  # persists status=ready + chunks + timestamp
        log.info("Ingest complete for agent %s: %d chunks in %s", agent_id, chunks, collection_name)
    except Exception as exc:
        log.error("Ingest failed for agent %s: %s", agent_id, exc)
        _ingest_status[agent_id].update({"status": "error", "error": str(exc)})
        store.set_status(agent_id, "draft")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/")
def list_agents():
    return [a.to_public_dict() for a in store.list_all()]


@router.post("/", status_code=201)
def create_agent(req: CreateAgentRequest):
    agent = store.create(
        name=req.name,
        title=req.title,
        description=req.description,
        system_prompt=req.system_prompt,
        llm_provider=req.llm_provider,
        llm_model=req.llm_model,
        llm_api_key=req.llm_api_key,
        llm_api_base=req.llm_api_base,
        embed_model=req.embed_model,
        vector_db=req.vector_db,
        vector_db_url=req.vector_db_url,
        vector_db_api_key=req.vector_db_api_key,
    )
    _agent_files_dir(agent.id)  # pre-create upload directory
    return agent.to_public_dict()


@router.get("/{agent_id}")
def get_agent(agent_id: str):
    return _require_agent(agent_id).to_public_dict()


@router.patch("/{agent_id}")
def update_agent(agent_id: str, req: UpdateAgentRequest):
    _require_agent(agent_id)
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    agent = store.update(agent_id, **updates)
    return agent.to_public_dict()


@router.post("/{agent_id}/clone", status_code=201)
def clone_agent(agent_id: str):
    _require_agent(agent_id)
    try:
        cloned = store.clone(agent_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return cloned.to_public_dict()


@router.delete("/{agent_id}", status_code=204)
def delete_agent(agent_id: str):
    agent = _require_agent(agent_id)
    # Remove files
    files_dir = _FILES_ROOT / agent_id
    if files_dir.exists():
        shutil.rmtree(files_dir)
    _drop_collection(agent.collection_name, agent.vector_db, agent.vector_db_url, agent.vector_db_api_key)
    store.delete(agent_id)
    _ingest_status.pop(agent_id, None)


# ── File management ───────────────────────────────────────────────────────────

@router.post("/{agent_id}/files", status_code=201)
async def upload_files(agent_id: str, files: list[UploadFile]):
    _require_agent(agent_id)
    dest_dir = _agent_files_dir(agent_id)
    saved = []
    for f in files:
        dest = dest_dir / (f.filename or "upload")
        content = await f.read()
        dest.write_bytes(content)
        saved.append({"name": dest.name, "size": len(content)})
    return {"uploaded": saved}


@router.get("/{agent_id}/files")
def list_files(agent_id: str):
    _require_agent(agent_id)
    d = _FILES_ROOT / agent_id
    if not d.exists():
        return []
    return [
        {
            "name": p.name,
            "size": p.stat().st_size,
            "modified": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(),
        }
        for p in sorted(d.iterdir()) if p.is_file()
    ]


@router.delete("/{agent_id}/files/{filename}", status_code=204)
def delete_file(agent_id: str, filename: str):
    _require_agent(agent_id)
    target = _FILES_ROOT / agent_id / filename
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found")
    target.unlink()


# ── Ingestion ─────────────────────────────────────────────────────────────────

@router.post("/{agent_id}/ingest", status_code=202)
def trigger_ingest(agent_id: str, background_tasks: BackgroundTasks):
    agent = _require_agent(agent_id)
    files_dir = _FILES_ROOT / agent_id
    has_files = files_dir.exists() and any(files_dir.iterdir())
    has_urls = bool(store.get_urls_for_agent(agent_id))
    if not has_files and not has_urls:
        raise HTTPException(status_code=400, detail="No files or URLs added yet — add some knowledge sources first")
    if _ingest_status.get(agent_id, {}).get("status") == "ingesting":
        raise HTTPException(status_code=409, detail="Ingestion already in progress")
    background_tasks.add_task(
        _run_ingest, agent_id, agent.collection_name, files_dir,
        agent.vector_db, agent.vector_db_url, agent.vector_db_api_key,
    )
    return {"message": "Ingestion started", "collection": agent.collection_name}


@router.get("/{agent_id}/status")
def get_status(agent_id: str):
    agent = _require_agent(agent_id)
    ingest = _ingest_status.get(agent_id, {})
    # Fall back to DB-persisted values when the in-memory dict has no entry
    # (e.g. after a server restart where the agent was previously ingested)
    return {
        "agent_id": agent_id,
        "status": ingest.get("status", agent.status),
        "chunks": ingest.get("chunks", agent.last_ingest_chunks),
        "error": ingest.get("error"),
        "started_at": ingest.get("started_at"),
        "finished_at": ingest.get("finished_at", agent.last_ingest_at or None),
    }


# ── Chat URL ──────────────────────────────────────────────────────────────────

@router.get("/{agent_id}/chat-url")
def get_chat_url(agent_id: str):
    _require_agent(agent_id)
    return {"url": f"{_CHAINLIT_URL}?agent_id={agent_id}"}


# ── URL knowledge sources ─────────────────────────────────────────────────────

class AddUrlRequest(BaseModel):
    url: str
    label: str = ""


@router.get("/{agent_id}/urls")
def list_urls(agent_id: str):
    _require_agent(agent_id)
    return store.list_urls(agent_id)


@router.post("/{agent_id}/urls", status_code=201)
def add_url(agent_id: str, req: AddUrlRequest):
    _require_agent(agent_id)
    url = req.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")
    return store.add_url(agent_id, url, req.label)


@router.delete("/{agent_id}/urls/{url_id}", status_code=204)
def delete_url(agent_id: str, url_id: str):
    _require_agent(agent_id)
    if not store.delete_url(url_id):
        raise HTTPException(status_code=404, detail=f"URL '{url_id}' not found")


# ── Feedback ──────────────────────────────────────────────────────────────────

@router.get("/{agent_id}/feedback")
def get_feedback(agent_id: str):
    _require_agent(agent_id)
    from tibco_agent.feedback import summary as _fb_summary, get_recent as _fb_recent
    counts = _fb_summary(agent_id=agent_id)
    recent = _fb_recent(agent_id=agent_id, limit=20)
    return {
        "agent_id": agent_id,
        "thumbs_up": counts.get("up", 0),
        "thumbs_down": counts.get("down", 0),
        "recent": recent,
    }
