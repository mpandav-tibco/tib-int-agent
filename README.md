# AgentForge

A "Shopify for AI agents" — a visual builder where you create named agents, write their system prompts, upload knowledge documents or URL sources, then immediately test them in an embedded chat panel.

TARA (TIBCO AI Review Agent) is the built-in first-party agent; you can build as many additional agents as you like alongside it.

## What you can do

- **Create agents** — name, title, system prompt, LLM provider/model, API key
- **Upload knowledge** — drag-and-drop PDFs, Markdown, text; or add URLs to crawl
- **Build knowledge base** — one-click ingestion into an isolated Weaviate collection per agent
- **Test in-place** — embedded Chainlit chat panel, no tab-switching needed
- **Open in new tab** — share a direct chat link for any agent
- **Start from a template** — 6 built-in starting points (Customer Support, HR, DevOps, Code Review, Sales, Docs)
- **View feedback** — per-agent thumbs-up/down counts and rated exchange history

---

## Architecture

```
Port 8000 — FastAPI (main.py)
  ├── /api/agents/*     CRUD, file upload, ingest, feedback
  └── /*                React SPA (forge/dist/) — AgentForge builder UI

Port 8080 — Chainlit (chainlit_app.py)
  └── ?agent_id=<id>    Loads agent config from SQLite, uses per-agent
                        system prompt + Weaviate collection

SQLite (data/agents.db)
  ├── agents table      Agent config, status, LLM settings
  └── agent_urls table  URL knowledge sources per agent

Weaviate (port 8080 in Docker / localhost:8080 local)
  └── Agent_<id> collection per agent  (isolated KB)
```

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.11+ | |
| Node.js | 18+ | For building/running the React UI |
| [Ollama](https://ollama.ai) | latest | Skip if using a cloud LLM |
| Weaviate | 1.24+ | Via Docker Compose or local install |

**Pull models for local use (Ollama):**
```bash
ollama pull deepseek-r1:latest   # LLM (~4.9 GB)
ollama pull nomic-embed-text     # Embeddings (~274 MB) — required
```

---

## Quick Start — Local Development

Three terminals. Run them in order.

### 1. Python backend (FastAPI + Chainlit)

```bash
git clone https://github.com/mpandav-tibco/tibco-ai-agent.git
cd tibco-ai-agent

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate    # macOS / Linux

pip install -r requirements.txt
```

**Terminal A — API server (port 8000):**
```bash
uvicorn main:app --reload --port 8000
```

**Terminal B — Chainlit chat UI (port 8080):**
```bash
chainlit run chainlit_app.py --port 8080
```

### 2. React builder UI

**Terminal C — Vite dev server (port 5173):**
```bash
cd forge
npm install
npm run dev
```

Open **http://localhost:5173** — you should see the AgentForge gallery.

### Using the Makefile

```bash
make install       # pip install -r requirements.txt
make forge-install # cd forge && npm install
make dev           # starts FastAPI + Chainlit together
make forge-dev     # starts Vite dev server
```

---

## Quick Start — Docker Compose (recommended for testing on another machine)

Builds and starts Weaviate + API + Chainlit in one command. Ollama runs on the host.
The Dockerfile uses a multi-stage build — Node.js builds the React SPA inside Docker, so no local `npm` install is required.

```bash
# 1. Pull Ollama models on the host first
ollama pull deepseek-r1:latest
ollama pull nomic-embed-text

# 2. Start everything (React SPA is built inside Docker automatically)
docker compose up --build
```

| URL | Service |
|-----|---------|
| http://localhost:8000 | AgentForge builder UI + API |
| http://localhost:8080 | Chainlit chat (used by iframe + direct link) |

Or with make:
```bash
make docker-up    # builds React SPA then docker compose up --build
make docker-down  # docker compose down
```

### Cloud LLM instead of Ollama

```bash
# Anthropic
LLM_PROVIDER=anthropic LLM_MODEL=claude-sonnet-4-6 LLM_API_KEY=sk-ant-... docker compose up --build

# OpenAI
LLM_PROVIDER=openai LLM_MODEL=gpt-4o LLM_API_KEY=sk-... docker compose up --build

# Groq
LLM_PROVIDER=groq LLM_MODEL=llama-3.3-70b-versatile LLM_API_KEY=gsk_... docker compose up --build
```

---

## Environment Variables

### Backend (FastAPI / Chainlit)

| Variable | Default | Description |
|----------|---------|-------------|
| `WEAVIATE_URL` | `http://localhost:8080` | Weaviate instance URL |
| `CHAINLIT_URL` | `http://localhost:8080` | Chainlit base URL (used to build agent chat links) |
| `LLM_PROVIDER` | `ollama` | `ollama` · `openai` · `anthropic` · `groq` · `ollama-cloud` · `custom` |
| `LLM_MODEL` | `deepseek-r1:latest` | Model name for the selected provider |
| `LLM_API_KEY` | _(empty)_ | API key for cloud providers |
| `LLM_API_BASE` | _(empty)_ | Base URL for custom / ollama-cloud providers |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `EMBED_MODEL` | `nomic-embed-text` | Embedding model (always via Ollama) |
| `COLLECTION_NAME` | `TibcoKnowledge` | Default Weaviate collection (TARA / legacy) |
| `REQUEST_TIMEOUT` | `180` | LLM request timeout in seconds |
| `FORGE_API_KEY` | _(empty)_ | Set to enable API key auth on all `/api/*` routes |
| `AGENTS_DB_PATH` | `data/agents.db` | SQLite database path |
| `AGENT_FILES_ROOT` | `data/agent_files/` | Uploaded knowledge files root |

### Chainlit auth (optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `CHAINLIT_AUTH_SECRET` | _(empty)_ | Set to enable Chainlit login |
| `TARA_USERNAME` | `tara` | Chainlit login username |
| `TARA_PASSWORD` | `tara` | Chainlit login password |

### React builder UI

| Variable | Description |
|----------|-------------|
| `VITE_REQUIRE_AUTH=true` | Force login screen when no API key is stored (set in `forge/.env`) |

---

## AgentForge API key auth (optional)

To lock down the builder UI, set `FORGE_API_KEY` on the server:

```bash
export FORGE_API_KEY="my-secret-key"
uvicorn main:app --port 8000
```

To force the React login screen on clients that have no key stored:
```bash
# forge/.env
VITE_REQUIRE_AUTH=true
```

Leave `FORGE_API_KEY` unset for open dev mode (no login required).

---

## Building Agents — Step by Step

1. Open **http://localhost:5173** (dev) or **http://localhost:8000** (prod)
2. Click **New Agent** or pick a **Template**
3. Fill in Name, system prompt, and choose an LLM provider/model
4. Click **Save**
5. In the **Knowledge Base** tab:
   - Drag-and-drop files (PDF, Markdown, text)
   - Add URL sources to crawl
   - Click **Build Knowledge Base**
6. Wait for the status indicator to turn green (ready)
7. Switch to **Test Chat** — an embedded Chainlit panel loads your agent
8. Click **Open in new tab** to share the chat link

---

## LLM Provider Reference

| `LLM_PROVIDER` | Example model | Required extra vars |
|---|---|---|
| `ollama` (default) | `deepseek-r1:latest` | `OLLAMA_BASE_URL` |
| `openai` | `gpt-4o` | `LLM_API_KEY` |
| `anthropic` | `claude-sonnet-4-6` | `LLM_API_KEY` |
| `groq` | `llama-3.3-70b-versatile` | `LLM_API_KEY` |
| `ollama-cloud` | `llama3.3:70b-instruct-cloud` | `LLM_API_KEY`, `LLM_API_BASE` |
| `custom` | any OpenAI-compatible model | `LLM_API_KEY`, `LLM_API_BASE` |

Per-agent LLM settings (set in the editor) override the server defaults.

---

## TARA — Built-in TIBCO Agent

TARA is the original built-in agent for TIBCO integration engineers. It reviews `.flogo`, `.bwp`, `.log`, and `.zip` files and answers questions from your TIBCO knowledge base.

**To use TARA standalone (without the builder UI):**
```bash
chainlit run chainlit_app.py   # → http://localhost:8000
```

**Flogo static rules:**

| Rule ID | Severity | Description |
|---------|----------|-------------|
| FLOGO-001 | Error | Sensitive data logged (auth tokens, passwords) |
| FLOGO-002 | Error | SSL verification disabled |
| FLOGO-003 | Warning | No error handler on flow |
| FLOGO-004 | Warning | SELECT * in JDBC query |
| FLOGO-005 | Error | Hardcoded credentials |
| FLOGO-006 | Warning | Flow has no links (unreachable activities) |
| FLOGO-007 | Info | No triggers defined |
| FLOGO-008 | Warning | Timeout not set on REST activity |
| FLOGO-009 | Warning | Very large flow (>20 tasks) |
| FLOGO-010 | Info | No correlation ID propagation |
| FLOGO-011 | Warning | Log activity maps entire `$flow` or `$activity` |
| FLOGO-012 | Warning | Hardcoded URL in REST activity |

**Ingest TIBCO knowledge docs:**
```bash
# Drop .md, .txt, .pdf, .html files into data/knowledge/
# Use flogo/ or bw/ subfolders for automatic product tagging
python ingest.py              # reset and rebuild
python ingest.py --no-reset   # append to existing collection
python ingest.py --web        # also crawl TIBCO web docs
```

---

## Project Structure

```
tibco-ai-agent/
├── main.py                    # FastAPI entry point — API + React SPA
├── chainlit_app.py            # Chainlit chat UI (per-agent via ?agent_id=)
├── ingest.py                  # TARA knowledge ingestion script
├── Makefile
├── Dockerfile.api             # API + React SPA container
├── docker-compose.yml         # Weaviate + API + Chainlit stack
├── requirements.txt
├── data/
│   ├── agents.db              # SQLite — agent configs + URLs (auto-created)
│   ├── agent_files/           # Uploaded knowledge files per agent
│   └── knowledge/             # TARA legacy knowledge docs
├── agent_store/
│   ├── models.py              # Agent dataclass
│   ├── store.py               # Thread-safe SQLite store (agents + agent_urls)
│   └── router.py              # FastAPI router — CRUD, upload, ingest, feedback, URLs
├── forge/                     # React builder UI (Vite + React + Tailwind)
│   ├── src/
│   │   ├── App.tsx
│   │   ├── api.ts             # Typed fetch wrappers (auth-header aware)
│   │   ├── types.ts
│   │   ├── contexts/
│   │   │   └── AuthContext.tsx
│   │   ├── pages/
│   │   │   ├── Gallery.tsx    # Agent card grid + template picker
│   │   │   ├── Editor.tsx     # Config form + KB panel + chat iframe + feedback
│   │   │   └── Login.tsx      # API key login screen
│   │   └── components/
│   │       ├── AgentCard.tsx
│   │       ├── FileUpload.tsx
│   │       ├── IngestStatus.tsx
│   │       └── TemplateModal.tsx
│   └── package.json
└── tibco_agent/
    ├── agent/core.py          # LLM setup, prompt assembly, streaming
    ├── analyzers/             # Flogo, BW, Log, ZIP static analyzers
    ├── ingest/
    │   ├── pipeline.py        # IngestionPipeline (per-collection)
    │   └── sources/
    │       ├── file_source.py
    │       └── web_source.py  # URL crawling (used by agent URL sources)
    ├── streaming.py           # ThinkFilter — strips <think> blocks (deepseek-r1)
    ├── tools/agent_tools.py   # Weaviate search (per-collection LRU cache)
    ├── feedback.py            # Thumbs-up/down rating store (SQLite)
    └── config.py              # Settings (pydantic-settings)
```

---

## Running Tests

```bash
# Analyzers + critical path (no external services required)
pytest tests/ test_analyzers.py -v -k "not weaviate and not rag"

# Or via make
make test
```
