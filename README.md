# TARA — TIBCO AI Review Agent

A chat-based AI assistant for TIBCO integration engineers. TARA answers best-practice questions, reviews `.flogo` and `.bwp`/`.bwp6` application files, diagnoses Kubernetes pod logs, and retrieves answers from your ingested TIBCO documentation — all in a modern streaming chat UI powered by [Chainlit](https://docs.chainlit.io).

## Architecture

```
User (Chainlit chat — port 8000)
      │
      ├── File upload (.flogo · .bwp · .log · .zip)
      │         │
      │         └── Static analyzers (no LLM)
      │               ├── FlogoAnalyzer  (12 rules, FLOGO-001…012)
      │               ├── BWAnalyzer     (BW5/6/BWCE XML)
      │               ├── LogAnalyzer    (K8s / on-prem logs)
      │               └── analyze_zip    (multi-file projects)
      │
      ├── Knowledge retrieval
      │         └── Weaviate (hybrid BM25+vector, nomic-embed-text)
      │
      └── LLM (streaming)
                ├── Ollama (local) — deepseek-r1 · llama3 · mistral
                ├── OpenAI          — gpt-4o · gpt-4o-mini
                ├── Anthropic       — claude-opus-4 · claude-sonnet-4
                └── Groq / custom OpenAI-compatible
```

**Key design choices:**

- Retrieval-only RAG — no second LLM call inside the tool, halving inference latency
- Rule engine with `Rule` ABC — add new checks without touching the agent core
- `ToolRegistry` singleton — register new tools without modifying `build_agent()`
- Streaming responses with real-time token display and `<think>` block filtering (deepseek-r1)
- Intent classification — full review vs. specific question → different LLM prompt depth

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Runtime |
| [Ollama](https://ollama.ai) | latest | Local LLM inference (optional if using cloud provider) |
| Weaviate | 1.24+ | Vector store (or use Docker Compose) |

**Default Ollama models:**
```bash
ollama pull deepseek-r1:latest   # LLM (~4.9 GB) — best for analysis
ollama pull nomic-embed-text     # Embeddings (~274 MB) — required for RAG
```

Any Ollama-compatible model works. Cloud providers (OpenAI, Anthropic, Groq) need only an API key.

## Quick Start (local)

```bash
# 1. Clone and create virtual environment
git clone https://github.com/mpandav-tibco/tibco-ai-agent.git
cd tibco-ai-agent
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate    # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Add knowledge files (optional but recommended)
# Drop .md, .txt, .pdf, or .html files into data/knowledge/
# Use subfolders named flogo/ or bw/ for automatic product tagging

# 4. Ingest knowledge into Weaviate
python ingest.py

# 5. Launch TARA
chainlit run chainlit_app.py
# → opens at http://localhost:8000
```

## Docker Compose (recommended for production)

Starts Weaviate + TARA in one command. Ollama runs on the host and is accessed via `host.docker.internal`.

```bash
# Pull Ollama models on the host first
ollama pull deepseek-r1:latest
ollama pull nomic-embed-text

# Start all services
docker-compose up --build

# → TARA at http://localhost:8000
# → Weaviate at http://localhost:8080
```

To use a cloud LLM instead of Ollama:
```bash
LLM_PROVIDER=anthropic LLM_MODEL=claude-sonnet-4-6 LLM_API_KEY=sk-ant-... docker-compose up --build
```

## LLM Providers

Set `LLM_PROVIDER` (and accompanying vars) in your environment or `.env` file:

| `LLM_PROVIDER` | `LLM_MODEL` example | Extra vars |
|---|---|---|
| `ollama` (default) | `deepseek-r1:latest` | `OLLAMA_BASE_URL` |
| `openai` | `gpt-4o` | `LLM_API_KEY` |
| `anthropic` | `claude-sonnet-4-6` | `LLM_API_KEY` |
| `groq` | `llama-3.3-70b-versatile` | `LLM_API_KEY` |
| `ollama-cloud` | `llama3.3:70b-instruct-cloud` | `LLM_API_KEY`, `LLM_API_BASE` |
| `custom` | any OpenAI-compatible model | `LLM_API_KEY`, `LLM_API_BASE` |

You can also switch provider live from the chat settings panel (gear icon ⚙).

## Knowledge Base

Place documents in `data/knowledge/`. Supported formats: `.md` `.txt` `.pdf` `.html`

```
data/knowledge/
├── flogo/          # auto-tagged as product=flogo
│   ├── best_practices.md
│   └── release_notes.pdf
├── bw/             # auto-tagged as product=bw
│   └── kubernetes_deployment.md
└── errors/         # tagged as product=general
    └── common_errors.md
```

Re-ingest after adding files:
```bash
python ingest.py              # reset and rebuild (default)
python ingest.py --no-reset   # append to existing collection
python ingest.py --web        # also fetch TIBCO web docs
```

## Supported File Types for Review

Upload files directly in the chat input bar:

| Extension | Analyzer | Notes |
|-----------|----------|-------|
| `.flogo` | FlogoAnalyzer | 12 static rules (security, resilience, observability) |
| `.bwp`, `.bwp6`, `.process` | BWAnalyzer | BW5/6/BWCE process definitions |
| `.log`, `.txt` | LogAnalyzer | K8s pod logs, on-prem logs |
| `.zip` | analyze_zip | Multi-file project (Flogo + BW mixed) |

## Flogo Rules

| Rule ID | Severity | Description |
|---------|----------|-------------|
| FLOGO-001 | Error | Sensitive data logged (auth tokens, passwords) |
| FLOGO-002 | Error | SSL verification disabled on REST activity |
| FLOGO-003 | Warning | No error handler on flow |
| FLOGO-004 | Warning | SELECT * in JDBC query |
| FLOGO-005 | Error | Hardcoded credentials in activity input |
| FLOGO-006 | Warning | Flow has no links (unreachable activities) |
| FLOGO-007 | Info | No triggers defined |
| FLOGO-008 | Warning | Timeout not set on REST activity |
| FLOGO-009 | Warning | Very large flow (>20 tasks) — consider splitting |
| FLOGO-010 | Info | No correlation ID propagation detected |
| FLOGO-011 | Warning | Log activity maps entire `$flow` or `$activity` object |
| FLOGO-012 | Warning | Hardcoded URL in REST activity |

## Authentication

By default TARA runs without a login (suitable for local dev). To enable password auth:

```bash
# Generate a secret (any random string)
export CHAINLIT_AUTH_SECRET="your-random-secret-here"
export TARA_USERNAME="admin"
export TARA_PASSWORD="changeme"
chainlit run chainlit_app.py
```

In Docker Compose, set these in a `.env` file alongside `docker-compose.yml`.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WEAVIATE_URL` | `http://localhost:8080` | Weaviate instance URL |
| `COLLECTION_NAME` | `TibcoKnowledge` | Weaviate class name |
| `LLM_PROVIDER` | `ollama` | LLM backend (`ollama`, `openai`, `anthropic`, `groq`, `ollama-cloud`, `custom`) |
| `LLM_MODEL` | `deepseek-r1:latest` | Model name for the selected provider |
| `LLM_API_KEY` | _(empty)_ | API key for cloud providers |
| `LLM_API_BASE` | _(empty)_ | Base URL for custom/ollama-cloud providers |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `EMBED_MODEL` | `nomic-embed-text` | Ollama embedding model (always local) |
| `KNOWLEDGE_PATH` | `./data/knowledge` | Local knowledge directory |
| `REQUEST_TIMEOUT` | `180` | LLM request timeout in seconds |
| `CHAINLIT_AUTH_SECRET` | _(empty)_ | Set to enable password authentication |
| `TARA_USERNAME` | `tara` | Login username (when auth is enabled) |
| `TARA_PASSWORD` | `tara` | Login password (when auth is enabled) |

## Extending the Agent

**Add a new Flogo rule:**
```python
from tibco_agent.analyzers.base import Finding, Rule, Severity
from tibco_agent.analyzers.flogo_rules import FlogoContext

class MyRule(Rule):
    id = "CUSTOM-001"
    severity = Severity.WARNING
    category = "custom"

    def check(self, ctx: FlogoContext) -> list[Finding]:
        findings = []
        for flow in ctx.flows:
            if not flow.tasks:
                findings.append(Finding(
                    rule_id=self.id, severity=self.severity,
                    title="Empty Flow", location=f"flow:{flow.name}",
                    message="Flow has no tasks.",
                    recommendation="Add at least one activity.",
                ))
        return findings

from tibco_agent.analyzers.flogo_analyzer import FlogoAnalyzer
analyzer = FlogoAnalyzer()
analyzer.register_rule(MyRule())
```

**Add a new agent tool:**
```python
# tibco_agent/tools/agent_tools.py
def build_my_tool() -> FunctionTool: ...

# tibco_agent/agent/core.py — register it in build_agent()
registry.register(build_my_tool())
```

## Running Tests

```bash
# Smoke test: analyzers + Weaviate connectivity (no LLM required)
python test_analyzers.py

# End-to-end: requires Ollama running
python test_agent.py
```

## Project Structure

```
tibco-ai-agent/
├── chainlit_app.py           # Chainlit UI entry point
├── chainlit.md               # Welcome screen content
├── .chainlit/config.toml     # Chainlit theme and feature config
├── ingest.py                 # Knowledge ingestion script
├── test_analyzers.py         # Analyzer smoke tests
├── Dockerfile                # Container image
├── docker-compose.yml        # Weaviate + TARA stack
├── requirements.txt
├── data/
│   └── knowledge/            # Drop documents here
└── tibco_agent/
    ├── agent/
    │   └── core.py           # LLM setup, prompt assembly, streaming
    ├── analyzers/
    │   ├── base.py           # Rule, Finding, AnalysisReport ABCs
    │   ├── flogo_rules.py    # FLOGO-001…012 rule implementations
    │   ├── flogo_analyzer.py
    │   ├── bw_analyzer.py
    │   ├── log_analyzer.py
    │   └── multi_analyzer.py # ZIP project analysis
    ├── tools/
    │   ├── registry.py       # ToolRegistry singleton
    │   └── agent_tools.py    # LlamaIndex FunctionTool wrappers
    ├── knowledge/
    │   └── weaviate_store.py # Hybrid RAG search
    └── config.py             # Settings (pydantic-settings)
```
