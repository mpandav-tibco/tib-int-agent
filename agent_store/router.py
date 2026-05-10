"""FastAPI router for AgentForge — agent CRUD, file upload, KB ingestion."""
from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile
from fastapi.responses import JSONResponse
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
_CHAINLIT_URL = os.environ.get("CHAINLIT_URL", "http://localhost:8000")


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


def _drop_weaviate_collection(collection_name: str) -> None:
    try:
        from tibco_agent.tools.agent_tools import _get_weaviate_client
        client = _get_weaviate_client()
        if client.collections.exists(collection_name):
            client.collections.delete(collection_name)
            log.info("Dropped Weaviate collection %s", collection_name)
    except Exception as exc:
        log.warning("Could not drop Weaviate collection %s: %s", collection_name, exc)


def _run_ingest(agent_id: str, collection_name: str, files_dir: Path) -> None:
    """Background task: ingest all files in files_dir into the agent's Weaviate collection."""
    _ingest_status[agent_id] = {"status": "ingesting", "chunks": 0, "error": None,
                                 "started_at": datetime.now(timezone.utc).isoformat()}
    store.set_status(agent_id, "ingesting")
    try:
        from tibco_agent.ingest.pipeline import IngestionPipeline
        from tibco_agent.ingest.sources.file_source import FileSource
        from tibco_agent.config import settings

        pipeline = IngestionPipeline(
            chunk_size=300,
            chunk_overlap=50,
            collection_name=collection_name,
            weaviate_url=settings.weaviate_url,
        )
        pipeline.add_source(FileSource(path=str(files_dir), glob_pattern="**/*"))
        chunks = pipeline.run(reset=True)

        _ingest_status[agent_id].update({"status": "ready", "chunks": chunks,
                                          "finished_at": datetime.now(timezone.utc).isoformat()})
        store.set_status(agent_id, "ready")
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


@router.delete("/{agent_id}", status_code=204)
def delete_agent(agent_id: str):
    agent = _require_agent(agent_id)
    # Remove files
    files_dir = _FILES_ROOT / agent_id
    if files_dir.exists():
        shutil.rmtree(files_dir)
    # Drop Weaviate collection
    _drop_weaviate_collection(agent.collection_name)
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
    if not files_dir.exists() or not any(files_dir.iterdir()):
        raise HTTPException(status_code=400, detail="No files uploaded yet — upload files first")
    if _ingest_status.get(agent_id, {}).get("status") == "ingesting":
        raise HTTPException(status_code=409, detail="Ingestion already in progress")
    background_tasks.add_task(_run_ingest, agent_id, agent.collection_name, files_dir)
    return {"message": "Ingestion started", "collection": agent.collection_name}


@router.get("/{agent_id}/status")
def get_status(agent_id: str):
    agent = _require_agent(agent_id)
    ingest = _ingest_status.get(agent_id, {})
    return {
        "agent_id": agent_id,
        "status": ingest.get("status", agent.status),
        "chunks": ingest.get("chunks", 0),
        "error": ingest.get("error"),
        "started_at": ingest.get("started_at"),
        "finished_at": ingest.get("finished_at"),
    }


# ── Chat URL ──────────────────────────────────────────────────────────────────

@router.get("/{agent_id}/chat-url")
def get_chat_url(agent_id: str):
    _require_agent(agent_id)
    return {"url": f"{_CHAINLIT_URL}?agent_id={agent_id}"}
