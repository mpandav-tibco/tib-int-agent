"""
TARA — TIBCO AI Review Agent — Streamlit UI

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import html as _html_escape
import threading
import time
from pathlib import Path

import markdown as _md
import streamlit as st

from tibco_agent.report.generator import to_html, to_pdf
from tibco_agent.agent.core import PROVIDER_MODEL_HINTS, build_prompt, call_llm

# ── Chat avatar SVGs ──────────────────────────────────────────────────────────

_TARA_SVG = """
<svg width="40" height="40" viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="th" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#003865"/>
      <stop offset="100%" stop-color="#001f40"/>
    </linearGradient>
  </defs>
  <polygon points="20,1 37.3,10.5 37.3,29.5 20,39 2.7,29.5 2.7,10.5"
           fill="none" stroke="#4a90d9" stroke-width="0.8" opacity="0.5"/>
  <polygon points="20,3 35.4,12 35.4,28 20,37 4.6,28 4.6,12"
           fill="url(#th)" stroke="#0057a8" stroke-width="1.5"/>
  <circle cx="20" cy="3.5" r="2" fill="#0077cc" opacity="0.9"/>
  <circle cx="35.4" cy="12"  r="1.3" fill="#0057a8" opacity="0.7"/>
  <circle cx="35.4" cy="28"  r="1.3" fill="#0057a8" opacity="0.7"/>
  <circle cx="20"   cy="36.5" r="1.3" fill="#0057a8" opacity="0.7"/>
  <text x="20" y="27" text-anchor="middle"
        font-size="16" font-weight="900"
        font-family="Courier New,monospace" fill="#ffffff">T</text>
</svg>"""

_USER_SVG = """
<svg width="40" height="40" viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg">
  <circle cx="20" cy="20" r="19" fill="#0057a8" stroke="#003865" stroke-width="1"/>
  <circle cx="20" cy="14" r="7" fill="rgba(255,255,255,0.90)"/>
  <path d="M4,37 Q4,25 20,25 Q36,25 36,37 Z" fill="rgba(255,255,255,0.90)"/>
</svg>"""


def _chat_bubble_html(role: str, content: str) -> str:
    """Return custom HTML for a single chat message."""
    if role == "user":
        safe = _html_escape.escape(content).replace("\n", "<br>")
        return (
            '<div class="chat-row chat-user">'
            f'<div class="chat-bubble chat-bubble-user">{safe}</div>'
            f'<div class="chat-avatar">{_USER_SVG}</div>'
            '</div>'
        )
    body = _md.markdown(content, extensions=["tables", "fenced_code", "nl2br"])
    return (
        '<div class="chat-row chat-tara">'
        f'<div class="chat-avatar">{_TARA_SVG}</div>'
        f'<div class="chat-bubble chat-bubble-tara">{body}</div>'
        '</div>'
    )


def _render_chat_msg(role: str, content: str) -> None:
    st.markdown(_chat_bubble_html(role, content), unsafe_allow_html=True)


def _thinking_html(text: str, pct: int) -> str:
    """Progress bubble shown while TARA works — live-updated via st.empty()."""
    return (
        '<div class="chat-row chat-tara">'
        f'<div class="chat-avatar">{_TARA_SVG}</div>'
        '<div class="chat-bubble chat-bubble-tara" style="min-width:260px;">'
        f'<span class="chat-thinking">{_html_escape.escape(text)}</span>'
        '<div style="margin-top:10px;background:#e8f0f8;border-radius:6px;height:5px;overflow:hidden;">'
        f'<div style="background:linear-gradient(90deg,#003865,#0077cc);height:5px;border-radius:6px;'
        f'width:{pct}%;transition:width 0.5s ease;box-shadow:0 0 6px rgba(0,87,168,0.35);"></div></div>'
        f'<div style="text-align:right;font-size:0.72rem;color:#4a6080;margin-top:4px;font-weight:500;">'
        f'{pct}%</div>'
        '</div></div>'
    )


st.set_page_config(
    page_title="TARA — TIBCO AI Review Agent",
    page_icon="🔗",
    layout="wide",
)

_AGENTIC_CSS = """
<style>
/* ── Force light rendering in all Streamlit theme modes ───────────── */
:root { color-scheme: light !important; }
html, body { color-scheme: light !important; }

/* ── Clean professional background ────────────────────────────────── */
.stApp {
    background: linear-gradient(160deg, #eef3f9 0%, #e8f0f8 50%, #eef3f9 100%) !important;
    background-size: 200% 200%;
    animation: bgShift 35s ease infinite;
    color-scheme: light !important;
}
@keyframes bgShift {
    0%,100% { background-position: 0% 0%; }
    50%      { background-position: 100% 100%; }
}

/* ── Subtle dot-grid overlay ───────────────────────────────────────── */
.stApp > div:first-child::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image: radial-gradient(rgba(0,56,101,0.055) 1px, transparent 1px);
    background-size: 40px 40px;
    pointer-events: none;
    z-index: 0;
}

/* ── Sidebar ───────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #ffffff !important;
    border-right: 1px solid #d0dff0 !important;
    box-shadow: 2px 0 18px rgba(0,56,101,0.08);
}

/* ── Main content area — capped so it never stretches edge-to-edge ── */
.block-container {
    background: transparent !important;
    max-width: 1080px !important;
    margin-left: auto !important;
    margin-right: auto !important;
    padding-left: 2rem !important;
    padding-right: 2rem !important;
}

/* ── Chat input — centered & constrained at all viewport widths ─────── */
[data-testid="stBottom"] {
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    background: linear-gradient(to top, #eef3f9 60%, transparent) !important;
    padding: 0 24px 16px !important;
    box-sizing: border-box !important;
}
[data-testid="stBottom"] > *,
[data-testid="stBottom"] > div,
[data-testid="stBottom"] form {
    width: 100% !important;
    max-width: 900px !important;
    box-sizing: border-box !important;
}

/* ── Sidebar labels & text ─────────────────────────────────────────── */
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span {
    color: #1a2740 !important;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: #003865 !important;
}

/* ── Chat input ────────────────────────────────────────────────────── */
[data-testid="stChatInputContainer"] {
    background: #ffffff !important;
    border: 1.5px solid #b8d0e8 !important;
    border-radius: 16px !important;
    box-shadow: 0 4px 24px rgba(0,56,101,0.12);
    width: 100% !important;
}
[data-testid="stChatInputContainer"] textarea {
    font-size: 1.08rem !important;
    min-height: 62px !important;
    line-height: 1.65 !important;
    color: #1a2740 !important;
    background: transparent !important;
    padding: 14px 16px !important;
}
[data-testid="stChatInputContainer"] textarea::placeholder {
    color: rgba(0,56,101,0.36) !important;
    font-size: 1.08rem !important;
}

/* ── Buttons ───────────────────────────────────────────────────────── */
.stButton > button {
    background: #ffffff !important;
    border: 1.5px solid #b8d0e8 !important;
    color: #003865 !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    transition: all 0.2s ease !important;
}
.stButton > button:hover {
    background: #0057a8 !important;
    border-color: #0057a8 !important;
    color: #ffffff !important;
    box-shadow: 0 4px 16px rgba(0,87,168,0.22) !important;
    transform: translateY(-1px);
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #0057a8 0%, #003865 100%) !important;
    border: none !important;
    color: #ffffff !important;
    box-shadow: 0 4px 16px rgba(0,87,168,0.28) !important;
}
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #0066cc 0%, #004a80 100%) !important;
    color: #ffffff !important;
}

/* ── Text inputs ───────────────────────────────────────────────────── */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea {
    background: #ffffff !important;
    border: 1.5px solid #c8ddf0 !important;
    color: #1a2740 !important;
    border-radius: 8px !important;
}
.stTextInput > div > div > input:focus {
    border-color: #0057a8 !important;
    box-shadow: 0 0 0 3px rgba(0,87,168,0.10) !important;
}

/* ── Select boxes ──────────────────────────────────────────────────── */
[data-testid="stSelectbox"] > div > div {
    background: #ffffff !important;
    border: 1.5px solid #c8ddf0 !important;
    color: #1a2740 !important;
    border-radius: 8px !important;
}

/* ── Sliders ───────────────────────────────────────────────────────── */
[data-testid="stSlider"] [data-baseweb="slider"] [data-testid="stThumbValue"] {
    color: #003865 !important;
}

/* ── Expanders ─────────────────────────────────────────────────────── */
details > summary,
.streamlit-expanderHeader {
    background: #f5f8fc !important;
    border: 1px solid #d0dff0 !important;
    border-radius: 10px !important;
    color: #003865 !important;
}

/* ── Info / success / warning alerts ──────────────────────────────── */
[data-testid="stNotification"],
div[class*="stAlert"] {
    background: #f0f6ff !important;
    border: 1px solid #c0d8f0 !important;
    border-radius: 10px !important;
    color: #1a2740 !important;
}
div[data-testid="stSuccess"] { border-left: 4px solid #0057a8 !important; }

/* ── Dividers ──────────────────────────────────────────────────────── */
hr { border-color: #d0dff0 !important; }

/* ── Scrollbar ─────────────────────────────────────────────────────── */
::-webkit-scrollbar              { width: 5px; height: 5px; }
::-webkit-scrollbar-track        { background: #eef3f9; }
::-webkit-scrollbar-thumb        { background: #b8d0e8; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover  { background: #0057a8; }

/* ── Custom chat layout ────────────────────────────────────────────── */
.chat-row {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    margin: 10px auto;
    max-width: 860px;
    width: 100%;
}
.chat-user { flex-direction: row-reverse; }
.chat-tara { flex-direction: row; }
.chat-avatar { flex-shrink: 0; width: 40px; height: 40px; }
.chat-bubble {
    max-width: 78%;
    padding: 12px 16px;
    line-height: 1.65;
    font-size: 0.91rem;
    word-break: break-word;
}
.chat-bubble-user {
    background: linear-gradient(135deg, #0057a8 0%, #003865 100%);
    border-radius: 18px 4px 18px 18px;
    color: #ffffff;
    box-shadow: 0 3px 14px rgba(0,87,168,0.22);
}
.chat-bubble-tara {
    background: #ffffff;
    border: 1px solid #d0dff0;
    border-radius: 4px 18px 18px 18px;
    color: #1a2740;
    box-shadow: 0 2px 10px rgba(0,56,101,0.07);
}
/* TARA bubble markdown */
.chat-bubble-tara h2,.chat-bubble-tara h3 {
    color: #003865; border-bottom: 1px solid #d0dff0;
    padding-bottom: 4px; margin: 12px 0 6px;
}
.chat-bubble-tara h4 { color: #0057a8; margin: 8px 0 4px; }
.chat-bubble-tara strong { color: #003865; font-weight: 600; }
.chat-bubble-tara code {
    background: #eef3f9; color: #0057a8;
    border: 1px solid #d0dff0; border-radius: 4px;
    padding: 2px 6px; font-size: 0.87em; font-family: 'Courier New', monospace;
}
.chat-bubble-tara pre {
    background: #f5f8fc; border: 1px solid #d0dff0;
    border-radius: 8px; padding: 12px 14px; overflow-x: auto; margin: 8px 0;
}
.chat-bubble-tara pre code { background: none; padding: 0; color: #003865; border: none; }
.chat-bubble-tara table {
    border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 0.87rem;
}
.chat-bubble-tara th {
    background: #003865; padding: 6px 10px;
    border: 1px solid #b8d0e8; color: #ffffff;
}
.chat-bubble-tara td { padding: 5px 10px; border: 1px solid #d0dff0; color: #1a2740; }
.chat-bubble-tara tr:nth-child(even) { background: #f5f8fc; }
.chat-bubble-tara ul,.chat-bubble-tara ol { padding-left: 18px; margin: 6px 0; }
.chat-bubble-tara li { margin: 4px 0; }
.chat-bubble-tara blockquote {
    border-left: 3px solid #0057a8; margin: 8px 0;
    padding: 4px 12px; background: #f0f6ff; border-radius: 0 6px 6px 0;
    color: #003865;
}
/* Thinking animation */
.chat-thinking {
    font-style: italic; color: #0057a8;
    animation: thinkPulse 1.4s ease-in-out infinite;
}
@keyframes thinkPulse {
    0%,100% { opacity: 0.45; }
    50%      { opacity: 1; }
}
</style>
"""

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
    st.session_state.s_provider     = s.llm_provider
    st.session_state.s_llm_model    = s.llm_model
    st.session_state.s_api_key      = s.llm_api_key
    st.session_state.s_api_base     = s.llm_api_base
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

    provider = st.session_state.s_provider
    required_text = {
        "llm_model":       ("LLM Model",       st.session_state.s_llm_model),
        "embed_model":     ("Embed Model",      st.session_state.s_embed_model),
        "weaviate_url":    ("Weaviate URL",     st.session_state.s_weaviate_url),
        "collection_name": ("Collection Name",  st.session_state.s_collection),
    }
    if provider == "ollama":
        required_text["ollama_base_url"] = ("Ollama URL", st.session_state.s_ollama_url)
    elif provider not in ("custom", "ollama-cloud"):
        required_text["llm_api_key"] = ("API Key", st.session_state.s_api_key)

    errors = [label for _, (label, val) in required_text.items() if not val.strip()]
    if errors:
        st.error(f"Cannot save — required fields are empty: {', '.join(errors)}")
        return False

    updates = {k: v.strip() for k, (_, v) in required_text.items()}
    updates["llm_provider"]    = provider
    updates["llm_api_key"]     = st.session_state.s_api_key.strip()
    updates["llm_api_base"]    = st.session_state.s_api_base.strip()
    updates["ollama_base_url"] = st.session_state.s_ollama_url.strip()
    updates["request_timeout"] = float(st.session_state.s_timeout)

    _cfg.settings.apply(**updates)
    _load_agent.clear()
    _persist_env(updates)
    return True


@st.dialog("Settings", width="large")
def _settings_dialog() -> None:
    """Settings editor shown as a centered modal dialog."""
    _init_session_settings()

    _PROVIDER_LABELS = {
        "ollama":       "Ollama (Local)",
        "ollama-cloud": "Ollama Cloud  —  Cloud-hosted models",
        "openai":       "OpenAI",
        "anthropic":    "Anthropic / Claude",
        "groq":         "Groq  —  Fast & Free Cloud",
        "custom":       "Custom (OpenAI-compatible URL)",
    }

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**LLM Provider**")
        provider = st.selectbox(
            "Provider",
            options=list(_PROVIDER_LABELS.keys()),
            format_func=_PROVIDER_LABELS.get,
            key="s_provider",
        )
    with col_b:
        st.markdown("**Language Model**")
        st.text_input(
            "Model Name", key="s_llm_model",
            help=PROVIDER_MODEL_HINTS.get(provider, ""),
            placeholder=PROVIDER_MODEL_HINTS.get(provider, ""),
        )

    if provider == "ollama":
        st.text_input("Ollama URL", key="s_ollama_url",
                      help="Base URL of your local Ollama server.")
    elif provider == "ollama-cloud":
        st.info(
            "Ollama Cloud runs models remotely at **https://ollama.com/v1** "
            "(OpenAI-compatible API).  \n"
            "Sign in at [ollama.com](https://ollama.com) and generate an API key "
            "under your account settings.  \n"
            "⚠️ Large models (e.g. `671b-cloud`) require a paid subscription — "
            "free-tier models include `llama3.1:8b-instruct-cloud`."
        )
        st.text_input("Ollama Cloud API Key", key="s_api_key", type="password",
                      help="Your ollama.com account API key.")
        st.session_state.s_api_base = "https://ollama.com/v1"
    elif provider == "groq":
        st.info(
            "Groq offers **free** cloud inference for Llama, DeepSeek and more — "
            "typically 10-20× faster than local Ollama.  \n"
            "Get a free API key at [console.groq.com](https://console.groq.com)"
        )
        st.text_input("Groq API Key", key="s_api_key", type="password",
                      help="Starts with gsk_...")
    elif provider == "openai":
        st.text_input("OpenAI API Key", key="s_api_key", type="password",
                      help="Starts with sk-...")
    elif provider == "anthropic":
        st.text_input("Anthropic API Key", key="s_api_key", type="password",
                      help="Starts with sk-ant-...")
    elif provider == "custom":
        col_u, col_k = st.columns(2)
        with col_u:
            st.text_input("Base URL", key="s_api_base",
                          help="OpenAI-compatible API base, e.g. https://your-host/v1")
        with col_k:
            st.text_input("API Key (optional)", key="s_api_key", type="password")

    if provider != "ollama":
        st.session_state.setdefault("s_ollama_url", "http://localhost:11434")
    if provider not in ("groq", "openai", "anthropic", "custom", "ollama-cloud"):
        st.session_state.setdefault("s_api_key", "")
    if provider not in ("custom", "ollama-cloud"):
        st.session_state.setdefault("s_api_base", "")

    st.divider()
    col_e, col_w, col_c = st.columns(3)
    with col_e:
        st.markdown("**Embedding Model**")
        st.text_input("Embed Model", key="s_embed_model",
                      help=f"Ollama embedding model (always local). Common: {_EMBED_MODELS}")
    with col_w:
        st.markdown("**Vector Store**")
        st.text_input("Weaviate URL", key="s_weaviate_url")
        st.text_input("Collection Name", key="s_collection",
                      help="Must start with an uppercase letter.")
    with col_c:
        st.markdown("**Performance**")
        st.slider("Request Timeout (s)", min_value=30, max_value=600, step=30,
                  key="s_timeout")

    st.divider()
    btn1, btn2 = st.columns(2)
    with btn1:
        if st.button("Apply & Rebuild", type="primary", use_container_width=True):
            if _apply_settings():
                st.toast("Settings saved — agent will rebuild on your next query.", icon="✅")
                st.rerun()
    with btn2:
        if st.button("Cancel", use_container_width=True):
            st.session_state._reset_settings = True
            st.rerun()


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
        "llm_provider":    "LLM_PROVIDER",
        "llm_model":       "LLM_MODEL",
        "llm_api_key":     "LLM_API_KEY",
        "llm_api_base":    "LLM_API_BASE",
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
    st.markdown(_AGENTIC_CSS, unsafe_allow_html=True)
    st.markdown("""
<style>
/* ── Mascot layout ────────────────────────────────────────────── */
.mascot-wrap {
    position: relative;
    width: 180px;
    height: 180px;
    margin: 0 auto 24px;
}
/* Pulse rings expanding outward */
.m-pulse { position: absolute; border-radius: 50%; border: 1px solid rgba(0,140,255,0.25); }
.m-pulse-1 { inset: -16px; animation: mRingExpand 3.0s ease-out infinite; }
.m-pulse-2 { inset: -8px;  animation: mRingExpand 3.0s ease-out infinite 0.9s; }
@keyframes mRingExpand {
    0%   { transform: scale(0.85); opacity: 0.7; }
    100% { transform: scale(1.25); opacity: 0; }
}
/* Outer spinning dashed ring */
.m-ring-outer {
    position: absolute;
    inset: 0;
    border-radius: 50%;
    border: 2px dashed rgba(0,87,168,0.40);
    animation: spinCW 14s linear infinite;
}
/* Three node dots on the outer ring */
.m-node {
    position: absolute;
    width: 9px; height: 9px;
    background: #0057a8;
    border-radius: 50%;
    box-shadow: 0 0 8px rgba(0,87,168,0.6), 0 0 16px rgba(0,87,168,0.25);
}
.m-node-1 { top: -4px;  left: calc(50% - 4px); }
.m-node-2 { bottom: -4px; left: calc(50% - 4px); }
.m-node-3 { left: -4px; top: calc(50% - 4px); }
/* Inner counter-spinning ring */
.m-ring-inner {
    position: absolute;
    inset: 24px;
    border-radius: 50%;
    border: 1px dashed rgba(0,56,101,0.45);
    animation: spinCCW 9s linear infinite;
}
.m-node-inner {
    position: absolute;
    width: 6px; height: 6px;
    background: #003865;
    border-radius: 50%;
    box-shadow: 0 0 5px rgba(0,56,101,0.5);
    top: -3px; left: calc(50% - 3px);
}
/* Ambient core glow */
.m-glow {
    position: absolute;
    inset: 36px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(0,87,168,0.15) 0%, transparent 70%);
    animation: glowPulse 3s ease-in-out infinite;
}
/* Hexagonal AI core */
.m-hex {
    position: absolute;
    inset: 40px;
    clip-path: polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%);
    background: linear-gradient(145deg, rgba(0,25,60,0.97) 0%, rgba(0,10,30,0.95) 100%);
    border: none;
    animation: hexGlow 3s ease-in-out infinite;
}
/* Hex border using a layered hex behind */
.m-hex-border {
    position: absolute;
    inset: 37px;
    clip-path: polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%);
    background: linear-gradient(135deg, rgba(0,140,255,0.7), rgba(0,56,101,0.5));
    animation: hexGlow 3s ease-in-out infinite;
}
/* Circuit lines inside hex */
.m-circuit {
    position: absolute;
    inset: 40px;
    clip-path: polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%);
    overflow: hidden;
}
/* AI text */
.m-ai-text {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: 'Courier New', monospace;
    font-size: 30px;
    font-weight: 900;
    background: linear-gradient(135deg, #fff 0%, #90d0ff 50%, #60b4ff 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    filter: drop-shadow(0 0 8px rgba(0,180,255,0.9));
    letter-spacing: 2px;
}
/* Horizontal scan line sweeping top-to-bottom */
.m-scan {
    position: absolute;
    left: 40px; right: 40px;
    height: 2px;
    background: linear-gradient(90deg, transparent, rgba(0,87,168,0.7), transparent);
    top: 40px;
    animation: scanLine 2.5s ease-in-out infinite;
    filter: blur(0.5px);
}
@keyframes scanLine {
    0%   { top: 42px;  opacity: 0; }
    8%   { opacity: 1; }
    92%  { opacity: 1; }
    100% { top: 138px; opacity: 0; }
}
@keyframes spinCW   { to { transform: rotate( 360deg); } }
@keyframes spinCCW  { to { transform: rotate(-360deg); } }
@keyframes glowPulse {
    0%,100% { opacity: 0.4; transform: scale(1);   }
    50%     { opacity: 0.85; transform: scale(1.10); }
}
@keyframes hexGlow {
    0%,100% { filter: drop-shadow(0 0 5px  rgba(0,87,168,0.30)); }
    50%     { filter: drop-shadow(0 0 14px rgba(0,87,168,0.65)); }
}

/* ── Title ────────────────────────────────────────────────────── */
.agent-title {
    text-align: center;
    font-size: 3.8rem;
    font-weight: 900;
    background: linear-gradient(135deg, #002a55 0%, #0057a8 40%, #0077cc 70%, #003865 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0 0 10px 0;
    letter-spacing: -1.5px;
    line-height: 1.05;
    animation: titleGlow 4s ease-in-out infinite;
}
@keyframes titleGlow {
    0%,100% { filter: drop-shadow(0 0 6px  rgba(0,87,168,0.20)); }
    50%     { filter: drop-shadow(0 0 18px rgba(0,87,168,0.50)); }
}

/* ── Status bar ───────────────────────────────────────────────── */
.agent-status {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    color: #4a6e90;
    font-size: 0.78rem;
    letter-spacing: 0.9px;
    text-transform: uppercase;
}
.status-dot {
    width: 8px; height: 8px;
    background: #0ea56e;
    border-radius: 50%;
    flex-shrink: 0;
    animation: dotPulse 2s ease-in-out infinite;
    box-shadow: 0 0 6px #0ea56e;
}
@keyframes dotPulse {
    0%,100% { box-shadow: 0 0 4px #0ea56e; opacity: 1; }
    50%     { box-shadow: 0 0 12px #0ea56e, 0 0 22px rgba(14,165,110,0.22); opacity: 0.65; }
}
</style>

<div style="text-align:center; padding: 32px 0 16px 0;">

  <!-- Techy SVG-style mascot -->
  <div class="mascot-wrap">
    <div class="m-pulse m-pulse-1"></div>
    <div class="m-pulse m-pulse-2"></div>
    <div class="m-ring-outer">
      <div class="m-node m-node-1"></div>
      <div class="m-node m-node-2"></div>
      <div class="m-node m-node-3"></div>
    </div>
    <div class="m-ring-inner">
      <div class="m-node-inner"></div>
    </div>
    <div class="m-glow"></div>
    <div class="m-hex-border"></div>
    <div class="m-hex"></div>
    <div class="m-ai-text">AI</div>
    <div class="m-scan"></div>
  </div>

  <div class="agent-title">TARA</div>
  <div style="text-align:center; color:#4a6e90; font-size:0.95rem; letter-spacing:3px; text-transform:uppercase; margin-bottom:10px; font-weight:500;">
    TIBCO AI Review Agent
  </div>
  <div class="agent-status">
    <span class="status-dot"></span>
    TIBCO Integration Specialist &nbsp;·&nbsp; Intelligent Review &amp; Analysis &nbsp;·&nbsp; Multi-Environment Diagnostics
  </div>

</div>
""", unsafe_allow_html=True)

    # ── Sidebar ───────────────────────────────────────────────────────────────
    flogo_content = ""
    log_content   = ""

    with st.sidebar:
        with st.expander("Upload for Analysis", expanded=True):
            flogo_file = st.file_uploader(
                "Flogo app (.flogo / .json)",
                type=["flogo", "json"],
                help="Upload a .flogo file for static analysis — missing error handlers, timeouts, SSL, etc.",
            )
            log_file = st.file_uploader(
                "Integration log (.log / .txt)",
                type=["log", "txt"],
                help="Upload a BW or Flogo log from any environment (Kubernetes, on-prem, cloud) for error diagnosis.",
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

        with st.expander("Quick Prompts", expanded=False):
            for label, prompt in _QUICK_PROMPTS:
                if st.button(label, use_container_width=True):
                    st.session_state.pending_prompt = prompt

        # ── Settings — opens as centered modal dialog ─────────────────────────
        from tibco_agent.config import settings as _s
        _PROVIDER_SHORT = {
            "ollama": "Ollama", "ollama-cloud": "Ollama Cloud",
            "openai": "OpenAI", "anthropic": "Anthropic",
            "groq": "Groq", "custom": "Custom",
        }
        st.caption(
            f"**{_PROVIDER_SHORT.get(_s.llm_provider, _s.llm_provider)}** · "
            f"`{_s.llm_model}`"
        )
        if st.button("Settings", use_container_width=True):
            _settings_dialog()

        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if st.button("Retry Last", use_container_width=True,
                         help="Remove the last answer and re-send the same question"):
                msgs = st.session_state.get("messages", [])
                last_user = next((m["content"] for m in reversed(msgs) if m["role"] == "user"), None)
                if last_user:
                    if msgs and msgs[-1]["role"] == "assistant":
                        st.session_state.messages = msgs[:-1]
                    st.session_state.pending_prompt = last_user
                st.rerun()
        with btn_col2:
            if st.button("Clear Chat", use_container_width=True):
                st.session_state.messages = []
                st.rerun()

    # ── Chat ──────────────────────────────────────────────────────────────────
    if "messages" not in st.session_state:
        st.session_state.messages = []

    if not st.session_state.messages:
        st.markdown("""
<style>
/* ── Welcome screen ──────────────────────────────────────────────── */
.welcome-wrap {
    max-width: 860px;
    margin: 32px auto 0;
    text-align: center;
    padding: 0 16px;
}
.welcome-heading {
    font-size: 2.6rem;
    font-weight: 800;
    color: #002a55;
    letter-spacing: -1.2px;
    line-height: 1.1;
    margin: 0 0 14px;
}
.welcome-heading span {
    background: linear-gradient(90deg, #003865 0%, #0077cc 60%, #003865 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.welcome-sub {
    font-size: 1.08rem;
    color: #3a5a7a;
    line-height: 1.75;
    max-width: 620px;
    margin: 0 auto 40px;
}
.welcome-cards {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 18px;
    text-align: left;
    margin-bottom: 36px;
}
.w-card {
    background: #ffffff;
    border-radius: 14px;
    padding: 22px 20px 20px;
    box-shadow: 0 4px 24px rgba(0,56,101,0.09);
    border: 1px solid #e2eaf4;
    position: relative;
    overflow: hidden;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    cursor: default;
}
.w-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 4px;
    background: linear-gradient(90deg, #003865, #0077cc);
}
.w-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 10px 32px rgba(0,56,101,0.14);
}
.w-card-icon {
    font-size: 1.7rem;
    margin-bottom: 10px;
    display: block;
}
.w-card-title {
    font-size: 0.97rem;
    font-weight: 700;
    color: #003865;
    margin: 0 0 8px;
}
.w-card-body {
    font-size: 0.85rem;
    color: #4a5568;
    line-height: 1.65;
    margin: 0;
}
</style>

<div class="welcome-wrap">
  <h2 class="welcome-heading"><span>How can I help you today?</span></h2>
  <p class="welcome-sub">
    Your TIBCO integration &amp; messaging expert — review applications, diagnose logs,
    and answer questions across the full TIBCO platform stack, from any environment.
  </p>
  <div class="welcome-cards">
    <div class="w-card">
      <span class="w-card-icon">💬</span>
      <p class="w-card-title">Integration &amp; Messaging Q&amp;A</p>
      <p class="w-card-body">Ask anything — middleware patterns, EMS topics &amp; queues,
        FTL/eFTL, connection pooling, Kubernetes deployment, and platform best practices.</p>
    </div>
    <div class="w-card">
      <span class="w-card-icon">🔍</span>
      <p class="w-card-title">Application Review</p>
      <p class="w-card-body">Upload a TIBCO integration application and receive an
        architect-level review covering errors, missing handlers, security gaps,
        and production readiness.</p>
    </div>
    <div class="w-card">
      <span class="w-card-icon">📋</span>
      <p class="w-card-title">Log Analysis &amp; Diagnostics</p>
      <p class="w-card-body">Upload BW or Flogo logs from any environment — Kubernetes,
        on-prem, or cloud — and get root-cause diagnosis with exact remediation steps.</p>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

    for msg in st.session_state.messages:
        _render_chat_msg(msg["role"], msg["content"])

    user_input = st.session_state.pop("pending_prompt", None) or st.chat_input(
        "Ask TARA about TIBCO BW / Flogo..."
    )

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        _render_chat_msg("user", user_input)

        tara_slot = st.empty()

        def _update(text: str, pct: int) -> None:
            tara_slot.markdown(_thinking_html(text, pct), unsafe_allow_html=True)

        _update("Initializing…", 5)

        try:
            agent = _load_agent()

            # Phase 1 — build prompt with live step updates (runs in main thread)
            prompt = build_prompt(
                user_input, flogo_content, log_content,
                on_step=_update,
            )

            # Phase 2 — LLM call in background thread; poll with fake progress
            result_holder: list[str | None] = [None]
            error_holder:  list[BaseException | None] = [None]

            def _run_llm() -> None:
                try:
                    result_holder[0] = call_llm(agent, prompt)
                except BaseException as exc:  # noqa: BLE001
                    error_holder[0] = exc

            llm_thread = threading.Thread(target=_run_llm, daemon=True)
            llm_thread.start()

            pct = 65
            while llm_thread.is_alive():
                time.sleep(1.2)
                pct = min(pct + 2, 93)
                _update("Waiting for LLM response…", pct)

            llm_thread.join()
            _update("Finalizing…", 99)

            if error_holder[0] is not None:
                raise error_holder[0]
            response = result_holder[0] or ""

        except RuntimeError as e:
            response = (
                f"**Setup required:** {e}\n\n"
                "Run `python ingest.py` first to build the knowledge base."
            )
        except Exception as e:
            from tibco_agent.config import settings as _s
            if _s.llm_provider == "ollama":
                hint = (
                    "Check that Ollama is running: `ollama serve`\n"
                    f"Check that the model is pulled: `ollama pull {_s.llm_model}`\n"
                    "Check that Weaviate is running: `docker-compose up -d`"
                )
            else:
                hint = (
                    f"Provider: **{_s.llm_provider}** · Model: `{_s.llm_model}`\n\n"
                    "- Verify your **API Key** is correct in Settings\n"
                    "- Confirm the model name is available for your provider\n"
                    "- Check that Weaviate is running: `docker-compose up -d`\n"
                    "- If you just installed a new provider package, **restart Streamlit**"
                )
            response = f"**Error:** {e}\n\n{hint}"

        tara_slot.markdown(_chat_bubble_html("assistant", response), unsafe_allow_html=True)
        st.session_state.messages.append({"role": "assistant", "content": response})


if __name__ == "__main__":
    main()
