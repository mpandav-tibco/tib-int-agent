# TIBCO Integration AI Agent

A local AI agent that understands TIBCO BusinessWorks and Flogo — answers best-practice questions, reviews `.flogo` application files, and diagnoses Kubernetes pod logs. Runs entirely on free, local tools (Ollama + Weaviate + Streamlit).

## Architecture

```
User (Streamlit UI)
      │
      ▼
  ReActAgent  (LlamaIndex + Ollama llama3.1:8b)
      │
      ├── tibco_knowledge_search   RAG over Weaviate (nomic-embed-text)
      ├── analyze_flogo_file       Static rule engine for .flogo JSON
      └── analyze_pod_log          Pattern matcher for K8s pod logs
```

**Key design choices:**
- Retrieval-only RAG (no second LLM call inside the tool) — halves inference latency on local hardware
- Rule engine with `Rule` ABC — add new checks without touching the agent core
- `ToolRegistry` singleton — register new tools without modifying `build_agent()`
- `KnowledgeSource` ABC — plug in new data sources (file, web, API) via a single `load()` method

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.12+ | Runtime |
| [Ollama](https://ollama.ai) | latest | Local LLM inference |
| Weaviate | 1.25+ | Vector store |

**Ollama models required:**
```bash
ollama pull llama3.1:8b       # LLM (~4.9 GB)
ollama pull nomic-embed-text  # Embeddings (~274 MB)
```

## Quick Start

```bash
# 1. Clone and create virtual environment
git clone https://github.com/mpandav-tibco/tib-int-agent.git
cd tib-int-agent
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate    # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
copy .env.example .env          # Windows
# cp .env.example .env          # macOS/Linux
# Edit .env if your Weaviate or Ollama URLs differ from the defaults

# 4. Add knowledge files
# Drop .md, .txt, .pdf, or .html files into data/knowledge/
# Use subfolders named flogo/ or bw/ for automatic product tagging

# 5. Build the knowledge base (ingests into Weaviate)
python ingest.py

# 6. Launch the UI
.venv\Scripts\streamlit.exe run app.py
```

## Knowledge Files

Place documents in `data/knowledge/`. Supported formats: `.md` `.txt` `.pdf` `.html`

```
data/knowledge/
├── flogo/          # auto-tagged as product=flogo
│   ├── best_practices.md
│   └── my-guide.pdf
├── bw/             # auto-tagged as product=bw
│   └── kubernetes_deployment.md
└── errors/         # tagged as product=general
    └── common_errors.md
```

Re-ingest after adding files:
```bash
python ingest.py           # resets and rebuilds
python ingest.py --no-reset  # appends to existing collection
python ingest.py --web       # also fetches TIBCO web docs
```

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
        ...

FlogoAnalyzer().register_rule(MyRule())
```

**Add a new agent tool:**
```python
# tibco_agent/tools/agent_tools.py
def build_my_tool() -> FunctionTool: ...

# tibco_agent/agent/core.py — register it
registry.register(build_my_tool())
```

## Running Tests

```bash
python test_analyzers.py   # smoke test: analyzers + Weaviate check (no LLM required)
python test_agent.py       # end-to-end: requires Ollama running
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `LLM_MODEL` | `llama3.1:8b` | Chat model name |
| `EMBED_MODEL` | `nomic-embed-text` | Embedding model name |
| `WEAVIATE_URL` | `http://localhost:8080` | Weaviate instance URL |
| `COLLECTION_NAME` | `TibcoKnowledge` | Weaviate class name |
| `KNOWLEDGE_PATH` | `./data/knowledge` | Local knowledge directory |
| `REQUEST_TIMEOUT` | `180` | Ollama request timeout (seconds) |
