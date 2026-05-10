"""AgentForge — FastAPI backend.

Serves:
  - /api/v1/agents  — agent CRUD + file upload + KB ingestion
  - /               — React builder UI (static files from builder/dist)

Run:
  uvicorn api:app --port 8001 --reload
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from agent_store.router import router

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(
    title="AgentForge API",
    version="1.0.0",
    description="Build, configure, and deploy domain-specific AI agents.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1/agents")

# Serve the React builder SPA if the build output exists.
_BUILDER_DIST = Path(__file__).parent / "builder" / "dist"
if _BUILDER_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_BUILDER_DIST), html=True), name="builder")
    log.info("Serving builder UI from %s", _BUILDER_DIST)
else:
    log.info("Builder UI not built yet — run: cd builder && npm run build")
