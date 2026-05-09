"""
TIBCO Integration AI Agent — Streamlit UI

Run with:
    streamlit run app.py
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="TIBCO Integration AI Agent",
    page_icon="🔗",
    layout="wide",
)

_QUICK_PROMPTS = [
    ("Error Handling",    "What are the Flogo best practices for error handling and what should every flow include?"),
    ("JDBC Pooling",      "How should I configure JDBC connection pooling in BusinessWorks for high concurrency?"),
    ("Pod Restart",       "My BW pod keeps restarting after deployment. What should I check?"),
    ("Performance K8s",  "What are performance tuning tips for BWCE running on Kubernetes?"),
    ("Mapper Best Practice", "What are the best practices for mapping in Flogo to avoid null errors?"),
    ("EMS Config",        "How should I configure TIBCO EMS connections for resilience in BW?"),
    ("Analyze Flogo",     "Analyze the uploaded .flogo file for issues and recommendations"),
    ("Diagnose Log",      "Diagnose the errors in the uploaded pod log and tell me how to fix them"),
]

# Common Ollama model suggestions shown as placeholder help text
_LLM_MODELS     = "llama3.1:8b · llama3.2:3b · mistral:7b · phi3:mini"
_EMBED_MODELS   = "nomic-embed-text · mxbai-embed-large · all-minilm"


# ── Agent cache ───────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner="Loading agent and knowledge base...")
def _load_agent():
    from tibco_agent.agent.core import build_agent
    return build_agent()


# ── Settings helpers ──────────────────────────────────────────────────────────

def _init_session_settings() -> None:
    """Seed session state from the live config object (once per session)."""
    if st.session_state.get("_settings_seeded"):
        return
    from tibco_agent.config import settings as s
    st.session_state.s_llm_model    = s.llm_model
    st.session_state.s_embed_model  = s.embed_model
    st.session_state.s_ollama_url   = s.ollama_base_url
    st.session_state.s_weaviate_url = s.weaviate_url
    st.session_state.s_collection   = s.collection_name
    st.session_state.s_timeout      = int(s.request_timeout)
    st.session_state._settings_seeded = True


def _apply_settings() -> None:
    """Push session-state values into the live settings object, clear the agent
    cache (so it rebuilds with the new config on the next query), and persist
    changes to .env so they survive a restart."""
    import tibco_agent.config as _cfg

    updates = {
        "llm_model":       st.session_state.s_llm_model.strip(),
        "embed_model":     st.session_state.s_embed_model.strip(),
        "ollama_base_url": st.session_state.s_ollama_url.strip(),
        "weaviate_url":    st.session_state.s_weaviate_url.strip(),
        "collection_name": st.session_state.s_collection.strip(),
        "request_timeout": float(st.session_state.s_timeout),
    }
    _cfg.settings.apply(**updates)
    _load_agent.clear()           # force agent rebuild on next query
    _persist_env(updates)


def _persist_env(updates: dict) -> None:
    """Merge updated values into .env (creating the file if absent)."""
    env_map = {
        "llm_model":       "LLM_MODEL",
        "embed_model":     "EMBED_MODEL",
        "ollama_base_url": "OLLAMA_BASE_URL",
        "weaviate_url":    "WEAVIATE_URL",
        "collection_name": "COLLECTION_NAME",
        "request_timeout": "REQUEST_TIMEOUT",
    }
    env_path = Path(".env")
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []

    env_updates = {env_map[k]: str(v) for k, v in updates.items()}
    written: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in env_updates:
                new_lines.append(f"{key}={env_updates[key]}")
                written.add(key)
                continue
        new_lines.append(line)

    for key, val in env_updates.items():
        if key not in written:
            new_lines.append(f"{key}={val}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


# ── Main UI ───────────────────────────────────────────────────────────────────

def main() -> None:
    st.title("TIBCO Integration AI Agent")
    st.caption(
        "Powered by Ollama (local LLM) + Weaviate vector search. "
        "Specializes in TIBCO BusinessWorks and Flogo Enterprise."
    )

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.header("Upload for Analysis")

        flogo_file = st.file_uploader(
            "Flogo app (.flogo / .json)",
            type=["flogo", "json"],
            help="Upload a .flogo file for static analysis — missing error handlers, timeouts, SSL, etc.",
        )
        log_file = st.file_uploader(
            "Pod log (.log / .txt)",
            type=["log", "txt"],
            help="Upload a Kubernetes pod log from a BW or Flogo container for error diagnosis.",
        )

        flogo_content = flogo_file.read().decode("utf-8") if flogo_file else ""
        log_content   = log_file.read().decode("utf-8")   if log_file   else ""

        if flogo_content:
            st.success(f"Flogo loaded ({len(flogo_content):,} chars)")
        if log_content:
            st.success(f"Log loaded ({len(log_content):,} chars)")

        st.divider()
        st.subheader("Quick Prompts")
        for label, prompt in _QUICK_PROMPTS:
            if st.button(label, use_container_width=True):
                st.session_state.pending_prompt = prompt

        st.divider()

        # ── Settings expander ─────────────────────────────────────────────────
        with st.expander("Settings", expanded=False):
            _init_session_settings()

            st.markdown("**Language Model**")
            st.text_input(
                "LLM Model",
                key="s_llm_model",
                help=f"Ollama model name. Common: {_LLM_MODELS}",
            )
            st.text_input(
                "Embed Model",
                key="s_embed_model",
                help=f"Ollama embedding model. Common: {_EMBED_MODELS}",
            )
            st.text_input(
                "Ollama URL",
                key="s_ollama_url",
                help="Base URL of your Ollama server.",
            )

            st.markdown("**Vector Store**")
            st.text_input(
                "Weaviate URL",
                key="s_weaviate_url",
                help="URL of your Weaviate instance.",
            )
            st.text_input(
                "Collection Name",
                key="s_collection",
                help="Weaviate class name — must start with an uppercase letter.",
            )

            st.markdown("**Performance**")
            st.slider(
                "Request Timeout (s)",
                min_value=30,
                max_value=600,
                step=30,
                key="s_timeout",
                help="Max seconds to wait for an Ollama response.",
            )

            if st.button("Apply & Rebuild Agent", type="primary", use_container_width=True):
                _apply_settings()
                st.success("Settings saved. Agent will rebuild on your next query.")

        if st.button("Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    # ── Chat ──────────────────────────────────────────────────────────────────
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.session_state.pop("pending_prompt", None) or st.chat_input(
        "Ask about TIBCO BW / Flogo..."
    )

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    agent = _load_agent()
                    from tibco_agent.agent.core import ask
                    response = ask(agent, user_input, flogo_content, log_content)
                except RuntimeError as e:
                    response = (
                        f"**Setup required:** {e}\n\n"
                        "Run `python ingest.py` first to build the knowledge base."
                    )
                except Exception as e:
                    response = (
                        f"**Error:** {e}\n\n"
                        "Check that Ollama is running: `ollama serve`\n"
                        "Check that Weaviate is running: `docker-compose up -d`\n"
                        "Models: `ollama pull llama3.1:8b && ollama pull nomic-embed-text`"
                    )
            st.markdown(response)

        st.session_state.messages.append({"role": "assistant", "content": response})


if __name__ == "__main__":
    main()
