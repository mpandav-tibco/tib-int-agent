"""
TIBCO Integration AI Agent — Streamlit UI

Run with:
    streamlit run app.py
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from tibco_agent.report.generator import to_html, to_pdf

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
    """Seed session state from the live config object.

    Runs once on first load. Set st.session_state._reset_settings = True
    before calling st.rerun() to force a re-seed on the next pass
    (used by Cancel and Edit buttons). Never modifies widget keys while
    widgets are already instantiated — avoids the Streamlit APIException.
    """
    reset = st.session_state.pop("_reset_settings", False)
    if st.session_state.get("_settings_seeded") and not reset:
        return
    from tibco_agent.config import settings as s
    st.session_state.s_llm_model    = s.llm_model
    st.session_state.s_embed_model  = s.embed_model
    st.session_state.s_ollama_url   = s.ollama_base_url
    st.session_state.s_weaviate_url = s.weaviate_url
    st.session_state.s_collection   = s.collection_name
    st.session_state.s_timeout      = int(s.request_timeout)
    st.session_state._settings_seeded = True


def _apply_settings() -> bool:
    """Validate, push session-state values into the live settings object, clear
    the agent cache, and persist to .env.  Returns False if validation fails."""
    import tibco_agent.config as _cfg

    required_text = {
        "llm_model":       ("LLM Model",       st.session_state.s_llm_model),
        "embed_model":     ("Embed Model",      st.session_state.s_embed_model),
        "ollama_base_url": ("Ollama URL",       st.session_state.s_ollama_url),
        "weaviate_url":    ("Weaviate URL",     st.session_state.s_weaviate_url),
        "collection_name": ("Collection Name",  st.session_state.s_collection),
    }
    errors = [label for _, (label, val) in required_text.items() if not val.strip()]
    if errors:
        st.error(f"Cannot save — required fields are empty: {', '.join(errors)}")
        return False

    updates = {k: v.strip() for k, (_, v) in required_text.items()}
    updates["request_timeout"] = float(st.session_state.s_timeout)

    _cfg.settings.apply(**updates)
    _load_agent.clear()
    _persist_env(updates)
    return True


def _render_download_buttons() -> None:
    """Render MD / HTML / PDF download buttons for any available analysis report."""
    reports = []
    if "flogo_report" in st.session_state:
        reports.append(("Flogo", st.session_state.flogo_report))
    if "log_report" in st.session_state:
        reports.append(("Log", st.session_state.log_report))
    if not reports:
        return

    with st.expander("Download Report", expanded=True):
        for label, report in reports:
            st.markdown(f"**{label}:** `{report.source}`")
            col_md, col_html, col_pdf = st.columns(3)
            stem = Path(report.source).stem
            with col_md:
                st.download_button(
                    "MD",
                    data=report.to_markdown().encode("utf-8"),
                    file_name=f"{stem}_report.md",
                    mime="text/markdown",
                    use_container_width=True,
                    key=f"dl_md_{label}",
                )
            with col_html:
                st.download_button(
                    "HTML",
                    data=to_html(report).encode("utf-8"),
                    file_name=f"{stem}_report.html",
                    mime="text/html",
                    use_container_width=True,
                    key=f"dl_html_{label}",
                )
            with col_pdf:
                st.download_button(
                    "PDF",
                    data=to_pdf(report),
                    file_name=f"{stem}_report.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key=f"dl_pdf_{label}",
                )


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
            from tibco_agent.analyzers.flogo_analyzer import FlogoAnalyzer
            st.session_state.flogo_report = FlogoAnalyzer().analyze(
                flogo_content, source=flogo_file.name
            )
        else:
            st.session_state.pop("flogo_report", None)

        if log_content:
            st.success(f"Log loaded ({len(log_content):,} chars)")
            from tibco_agent.analyzers.log_analyzer import LogAnalyzer
            st.session_state.log_report = LogAnalyzer().analyze(
                log_content, source=log_file.name
            )
        else:
            st.session_state.pop("log_report", None)

        _render_download_buttons()

        st.divider()
        st.subheader("Quick Prompts")
        for label, prompt in _QUICK_PROMPTS:
            if st.button(label, use_container_width=True):
                st.session_state.pending_prompt = prompt

        st.divider()

        # ── Settings expander ─────────────────────────────────────────────────
        _init_session_settings()
        edit_mode = st.session_state.get("_settings_edit_mode", False)
        expanded  = st.session_state.get("_settings_expanded", False)

        with st.expander("Settings", expanded=expanded):
            if not edit_mode:
                # ── Read-only view ────────────────────────────────────────────
                from tibco_agent.config import settings as s
                st.text_input("LLM Model",       value=s.llm_model,        disabled=True)
                st.text_input("Embed Model",      value=s.embed_model,      disabled=True)
                st.text_input("Ollama URL",       value=s.ollama_base_url,  disabled=True)
                st.text_input("Weaviate URL",     value=s.weaviate_url,     disabled=True)
                st.text_input("Collection Name",  value=s.collection_name,  disabled=True)
                st.text_input("Request Timeout",  value=f"{int(s.request_timeout)}s", disabled=True)

                if st.button("Edit Settings", use_container_width=True):
                    st.session_state._reset_settings     = True  # re-seed before widgets render
                    st.session_state._settings_edit_mode = True
                    st.session_state._settings_expanded  = True
                    st.rerun()

            else:
                # ── Edit view ─────────────────────────────────────────────────
                st.markdown("**Language Model**")
                st.text_input("LLM Model",    key="s_llm_model",
                              help=f"Ollama model name. Common: {_LLM_MODELS}")
                st.text_input("Embed Model",  key="s_embed_model",
                              help=f"Ollama embedding model. Common: {_EMBED_MODELS}")
                st.text_input("Ollama URL",   key="s_ollama_url",
                              help="Base URL of your Ollama server.")

                st.markdown("**Vector Store**")
                st.text_input("Weaviate URL",    key="s_weaviate_url",
                              help="URL of your Weaviate instance.")
                st.text_input("Collection Name", key="s_collection",
                              help="Weaviate class name — must start with an uppercase letter.")

                st.markdown("**Performance**")
                st.slider("Request Timeout (s)", min_value=30, max_value=600, step=30,
                          key="s_timeout", help="Max seconds to wait for an Ollama response.")

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Apply & Rebuild", type="primary", use_container_width=True):
                        if _apply_settings():
                            st.session_state._settings_edit_mode = False
                            st.session_state._settings_expanded  = False
                            st.toast("Settings saved — agent will rebuild on your next query.",
                                     icon="✅")
                            st.rerun()
                with col2:
                    if st.button("Cancel", use_container_width=True):
                        st.session_state._reset_settings     = True  # re-seed on next rerun
                        st.session_state._settings_edit_mode = False
                        st.session_state._settings_expanded  = True
                        st.rerun()

        if st.button("Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    # ── Chat ──────────────────────────────────────────────────────────────────
    if "messages" not in st.session_state:
        st.session_state.messages = []

    if not st.session_state.messages:
        st.markdown("<div style='height: 40px'></div>", unsafe_allow_html=True)
        col_l, col_c, col_r = st.columns([1, 2, 1])
        with col_c:
            st.markdown(
                "<h3 style='text-align:center; color:#003865;'>How can I help you today?</h3>",
                unsafe_allow_html=True,
            )
            st.markdown(
                "<p style='text-align:center; color:#666; margin-bottom:32px;'>"
                "Ask anything about TIBCO BusinessWorks or Flogo — or use the sidebar to upload "
                "a <code>.flogo</code> file for review or a pod log for diagnosis.</p>",
                unsafe_allow_html=True,
            )
        c1, c2, c3 = st.columns(3)
        with c1:
            st.info("**Knowledge Q&A**\n\nAsk about BW/Flogo configuration, patterns, error codes, and best practices.")
        with c2:
            st.info("**App Review**\n\nUpload a `.flogo` file → architect-level review: errors, warnings, and strengths.")
        with c3:
            st.info("**Log Diagnosis**\n\nUpload a K8s pod log → root-cause analysis with exact remediation steps.")
        st.markdown("<div style='height: 40px'></div>", unsafe_allow_html=True)

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
