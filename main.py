"""AgentForge — FastAPI entry point.

Serves:
  /api/agents/*   Agent CRUD, file upload, KB ingestion (agent_store/router.py)
  /assets/*       React SPA static assets (forge/dist/assets/)
  /*              React SPA index.html (catch-all for client-side routing)

Run in development:
  uvicorn main:app --reload --port 8000

Then start Chainlit separately:
  chainlit run chainlit_app.py --port 8080
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agent_store.router import router as agents_router

log = logging.getLogger(__name__)

app = FastAPI(
    title="AgentForge",
    description="Build, configure, and deploy AI agents backed by a Weaviate knowledge base.",
    version="0.1.0",
)

# Allow the Vite dev server (localhost:5173) to hit the API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8080"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routes ────────────────────────────────────────────────────────────────

app.include_router(agents_router, prefix="/api/agents")

# ── React SPA static files ────────────────────────────────────────────────────
# Only mounted when the production build exists; dev uses Vite's own dev server.

_DIST = Path(__file__).parent / "forge" / "dist"

if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        """Return index.html for all non-API paths (React Router handles routing)."""
        return FileResponse(str(_DIST / "index.html"))
else:
    log.warning(
        "forge/dist not found — React UI not served. "
        "Run 'cd forge && npm run build' to build it, "
        "or 'npm run dev' for hot-reload development."
    )

    @app.get("/", include_in_schema=False)
    async def dev_redirect():
        from fastapi.responses import HTMLResponse
        return HTMLResponse(
            "<h2>AgentForge API is running</h2>"
            "<p>The React UI is not built yet. "
            "Run <code>cd forge && npm install && npm run dev</code> to start the builder UI, "
            "or <code>npm run build</code> to produce a production bundle.</p>"
            "<p><a href='/docs'>API docs →</a></p>"
        )
