"""
TARA — TIBCO AI Review Agent — Streamlit UI

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import html as _html_escape
from pathlib import Path

import markdown as _md
import streamlit as st

from tibco_agent.report.generator import to_html, to_pdf
from tibco_agent.agent.core import PROVIDER_MODEL_HINTS

# ── Chat avatar SVGs ──────────────────────────────────────────────────────────

_TARA_SVG = """
<svg width="40" height="40" viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="th" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0d3a6b"/>
      <stop offset="100%" stop-color="#020d1a"/>
    </linearGradient>
  </defs>
  <polygon points="20,1 37.3,10.5 37.3,29.5 20,39 2.7,29.5 2.7,10.5"
           fill="none" stroke="#0055bb" stroke-width="0.8" opacity="0.55"/>
  <polygon points="20,3 35.4,12 35.4,28 20,37 4.6,28 4.6,12"
           fill="url(#th)" stroke="#0077dd" stroke-width="1.5"/>
  <line x1="7" y1="20" x2="33" y2="20" stroke="#0099ff" stroke-width="0.8" opacity="0.35"/>
  <circle cx="20" cy="3.5" r="2" fill="#0099ff" opacity="0.85"/>
  <circle cx="35.4" cy="12"  r="1.3" fill="#0066cc" opacity="0.55"/>
  <circle cx="35.4" cy="28"  r="1.3" fill="#0066cc" opacity="0.55"/>
  <circle cx="20"   cy="36.5" r="1.3" fill="#0066cc" opacity="0.55"/>
  <text x="20" y="27" text-anchor="middle"
        font-size="16" font-weight="900"
        font-family="Courier New,monospace" fill="#5bbeff">T</text>
</svg>"""

_USER_SVG = """
<svg width="40" height="40" viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg">
  <circle cx="20" cy="20" r="19" fill="rgba(0,35,70,0.75)"
          stroke="rgba(0,90,170,0.4)" stroke-width="1.5"/>
  <circle cx="20" cy="14" r="7" fill="rgba(0,90,170,0.65)"/>
  <path d="M4,37 Q4,25 20,25 Q36,25 36,37 Z" fill="rgba(0,90,170,0.65)"/>
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

st.set_page_config(
    page_title="TARA — TIBCO AI Review Agent",
    page_icon="🔗",
    layout="wide",
)

_AGENTIC_CSS = """
<style>
/* ── Animated gradient background ─────────────────────────────────── */
.stApp {
    background: linear-gradient(-45deg, #03060f, #060d1a, #0a1628, #071020);
    background-size: 400% 400%;
    animation: bgGradient 22s ease infinite;
}
@keyframes bgGradient {
    0%   { background-position: 0% 50%; }
    50%  { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}

/* ── Dot-grid overlay ──────────────────────────────────────────────── */
.stApp > div:first-child::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image: radial-gradient(rgba(0,87,168,0.13) 1px, transparent 1px);
    background-size: 38px 38px;
    pointer-events: none;
    z-index: 0;
}

/* ── Ambient glow orbs ─────────────────────────────────────────────── */
.stApp > div:first-child::after {
    content: '';
    position: fixed;
    width: 700px; height: 700px;
    background: radial-gradient(circle, rgba(0,87,168,0.09) 0%, transparent 68%);
    top: -180px; right: -180px;
    border-radius: 50%;
    animation: orb 28s ease-in-out infinite;
    pointer-events: none;
    z-index: 0;
}
@keyframes orb {
    0%, 100% { transform: translate(0,0) scale(1); }
    33%       { transform: translate(-70px, 90px) scale(1.06); }
    66%       { transform: translate(50px, -70px) scale(0.94); }
}

/* ── Sidebar ───────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: rgba(4, 9, 20, 0.88) !important;
    border-right: 1px solid rgba(0,87,168,0.22) !important;
    backdrop-filter: blur(14px);
    box-shadow: 4px 0 32px rgba(0,40,90,0.45);
}

/* ── Main content area ─────────────────────────────────────────────── */
.block-container { background: transparent !important; }

/* ── Chat messages ─────────────────────────────────────────────────── */
[data-testid="stChatMessage"] {
    background: rgba(8,18,36,0.55) !important;
    border: 1px solid rgba(0,87,168,0.17) !important;
    border-radius: 14px !important;
    backdrop-filter: blur(10px);
    box-shadow: 0 4px 28px rgba(0,0,0,0.35);
    transition: border-color 0.25s ease, box-shadow 0.25s ease;
}
[data-testid="stChatMessage"]:hover {
    border-color: rgba(0,87,168,0.38) !important;
    box-shadow: 0 4px 32px rgba(0,87,168,0.15);
}

/* ── Chat input ────────────────────────────────────────────────────── */
[data-testid="stChatInputContainer"] {
    background: rgba(6,13,26,0.82) !important;
    border: 1px solid rgba(0,87,168,0.28) !important;
    border-radius: 14px !important;
    backdrop-filter: blur(12px);
    box-shadow: 0 0 24px rgba(0,87,168,0.12);
}
[data-testid="stChatInputContainer"] textarea {
    font-size: 1.05rem !important;
    min-height: 54px !important;
    line-height: 1.6 !important;
    color: #d0e8ff !important;
}
[data-testid="stChatInputContainer"] textarea::placeholder {
    color: rgba(130,180,240,0.55) !important;
    font-size: 1.05rem !important;
}

/* ── Buttons ───────────────────────────────────────────────────────── */
.stButton > button {
    background: rgba(0,40,80,0.38) !important;
    border: 1px solid rgba(0,87,168,0.32) !important;
    color: #c2d9f8 !important;
    border-radius: 8px !important;
    transition: all 0.2s ease !important;
    backdrop-filter: blur(6px);
}
.stButton > button:hover {
    background: rgba(0,87,168,0.50) !important;
    border-color: rgba(0,140,255,0.6) !important;
    box-shadow: 0 0 18px rgba(0,87,168,0.45) !important;
    transform: translateY(-1px);
    color: #fff !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #0057a8 0%, #003865 100%) !important;
    border: 1px solid rgba(0,140,255,0.4) !important;
    box-shadow: 0 0 22px rgba(0,87,168,0.35) !important;
}

/* ── Text inputs / sliders ─────────────────────────────────────────── */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea {
    background: rgba(4,9,20,0.75) !important;
    border: 1px solid rgba(0,87,168,0.25) !important;
    color: #c2d9f8 !important;
    border-radius: 8px !important;
}
.stTextInput > div > div > input:focus {
    border-color: rgba(0,140,255,0.55) !important;
    box-shadow: 0 0 12px rgba(0,87,168,0.25) !important;
}

/* ── Expanders ─────────────────────────────────────────────────────── */
details > summary,
.streamlit-expanderHeader {
    background: rgba(6,13,26,0.55) !important;
    border: 1px solid rgba(0,87,168,0.2) !important;
    border-radius: 10px !important;
    color: #c2d9f8 !important;
}

/* ── Info / success / warning cards ───────────────────────────────── */
[data-testid="stNotification"],
div[class*="stAlert"] {
    background: rgba(0,40,80,0.25) !important;
    border: 1px solid rgba(0,87,168,0.22) !important;
    border-radius: 10px !important;
    backdrop-filter: blur(8px);
}

/* ── Dividers ──────────────────────────────────────────────────────── */
hr { border-color: rgba(0,87,168,0.18) !important; }

/* ── Scrollbar ─────────────────────────────────────────────────────── */
::-webkit-scrollbar              { width: 5px; height: 5px; }
::-webkit-scrollbar-track        { background: rgba(4,9,20,0.4); }
::-webkit-scrollbar-thumb        { background: rgba(0,87,168,0.38); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover  { background: rgba(0,120,220,0.65); }

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
    background: rgba(0,45,100,0.5);
    border: 1px solid rgba(0,110,200,0.35);
    border-radius: 18px 4px 18px 18px;
    color: #d0e8ff;
}
.chat-bubble-tara {
    background: rgba(6,14,32,0.65);
    border: 1px solid rgba(0,87,168,0.25);
    border-radius: 4px 18px 18px 18px;
    color: #c0ddf8;
    backdrop-filter: blur(6px);
}
/* TARA bubble markdown styles */
.chat-bubble-tara h2,.chat-bubble-tara h3 {
    color: #5bbeff; border-bottom: 1px solid rgba(0,87,168,0.25);
    padding-bottom: 4px; margin: 12px 0 6px;
}
.chat-bubble-tara h4 { color: #7acfff; margin: 8px 0 4px; }
.chat-bubble-tara strong { color: #90d0ff; font-weight: 600; }
.chat-bubble-tara code {
    background: rgba(0,20,50,0.7); color: #60c4ff;
    border-radius: 4px; padding: 2px 6px;
    font-size: 0.87em; font-family: 'Courier New', monospace;
}
.chat-bubble-tara pre {
    background: rgba(2,8,20,0.8); border: 1px solid rgba(0,87,168,0.25);
    border-radius: 8px; padding: 12px 14px; overflow-x: auto; margin: 8px 0;
}
.chat-bubble-tara pre code { background: none; padding: 0; color: #a0d4ff; }
.chat-bubble-tara table {
    border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 0.87rem;
}
.chat-bubble-tara th {
    background: rgba(0,56,101,0.5); padding: 6px 10px;
    border: 1px solid rgba(0,87,168,0.3); color: #90d0ff;
}
.chat-bubble-tara td { padding: 5px 10px; border: 1px solid rgba(0,87,168,0.2); }
.chat-bubble-tara tr:nth-child(even) { background: rgba(0,30,60,0.2); }
.chat-bubble-tara ul,.chat-bubble-tara ol { padding-left: 18px; margin: 6px 0; }
.chat-bubble-tara li { margin: 4px 0; }
.chat-bubble-tara blockquote {
    border-left: 3px solid rgba(0,140,255,0.5); margin: 8px 0;
    padding: 4px 12px; background: rgba(0,40,80,0.2); border-radius: 0 6px 6px 0;
}
/* TARA thinking animation */
.chat-thinking { font-style: italic; color: #7aafd4;
    animation: thinkPulse 1.4s ease-in-out infinite; }
@keyframes thinkPulse {
    0%,100% { opacity: 0.4; }
    50%     { opacity: 1;   }
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
    elif provider != "custom":
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
    border: 2px dashed rgba(0,140,255,0.45);
    animation: spinCW 14s linear infinite;
}
/* Three node dots on the outer ring */
.m-node {
    position: absolute;
    width: 9px; height: 9px;
    background: #0099ff;
    border-radius: 50%;
    box-shadow: 0 0 10px #0099ff, 0 0 20px rgba(0,153,255,0.4);
}
.m-node-1 { top: -4px;  left: calc(50% - 4px); }
.m-node-2 { bottom: -4px; left: calc(50% - 4px); }
.m-node-3 { left: -4px; top: calc(50% - 4px); }
/* Inner counter-spinning ring */
.m-ring-inner {
    position: absolute;
    inset: 24px;
    border-radius: 50%;
    border: 1px dashed rgba(0,87,168,0.5);
    animation: spinCCW 9s linear infinite;
}
.m-node-inner {
    position: absolute;
    width: 6px; height: 6px;
    background: #60b4ff;
    border-radius: 50%;
    box-shadow: 0 0 6px #60b4ff;
    top: -3px; left: calc(50% - 3px);
}
/* Ambient core glow */
.m-glow {
    position: absolute;
    inset: 36px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(0,140,255,0.22) 0%, transparent 70%);
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
    background: linear-gradient(90deg, transparent, rgba(0,220,255,0.8), transparent);
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
    0%,100% { opacity: 0.5; transform: scale(1);   }
    50%     { opacity: 1;   transform: scale(1.12); }
}
@keyframes hexGlow {
    0%,100% { filter: drop-shadow(0 0 6px  rgba(0,140,255,0.4)); }
    50%     { filter: drop-shadow(0 0 16px rgba(0,180,255,0.85)); }
}

/* ── Title ────────────────────────────────────────────────────── */
.agent-title {
    text-align: center;
    font-size: 3.8rem;
    font-weight: 900;
    background: linear-gradient(135deg, #c8e8ff 0%, #60b4ff 35%, #0088ff 65%, #e0f2ff 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0 0 10px 0;
    letter-spacing: -1.5px;
    line-height: 1.05;
    animation: titleGlow 4s ease-in-out infinite;
}
@keyframes titleGlow {
    0%,100% { filter: drop-shadow(0 0 8px  rgba(0,140,255,0.25)); }
    50%     { filter: drop-shadow(0 0 22px rgba(0,180,255,0.65)); }
}

/* ── Status bar ───────────────────────────────────────────────── */
.agent-status {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    color: #6a9fc8;
    font-size: 0.78rem;
    letter-spacing: 0.9px;
    text-transform: uppercase;
}
.status-dot {
    width: 8px; height: 8px;
    background: #00e676;
    border-radius: 50%;
    flex-shrink: 0;
    animation: dotPulse 2s ease-in-out infinite;
    box-shadow: 0 0 8px #00e676;
}
@keyframes dotPulse {
    0%,100% { box-shadow: 0 0 5px #00e676; opacity: 1; }
    50%     { box-shadow: 0 0 16px #00e676, 0 0 30px rgba(0,230,118,0.3); opacity: 0.65; }
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
  <div style="text-align:center; color:#5a90be; font-size:0.95rem; letter-spacing:3px; text-transform:uppercase; margin-bottom:10px; font-weight:500;">
    TIBCO AI Review Agent
  </div>
  <div class="agent-status">
    <span class="status-dot"></span>
    TIBCO Integration Specialist &nbsp;·&nbsp; Intelligent Review &amp; Analysis &nbsp;·&nbsp; Multi-Environment Diagnostics
  </div>

</div>
""", unsafe_allow_html=True)

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.header("Upload for Analysis")

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
                _RO_LABELS = {
                    "ollama": "Ollama (Local)", "openai": "OpenAI",
                    "anthropic": "Anthropic / Claude",
                    "groq": "Groq  —  Fast & Free Cloud",
                    "custom": "Custom (OpenAI-compatible URL)",
                }
                st.text_input("Provider",        value=_RO_LABELS.get(s.llm_provider, s.llm_provider), disabled=True)
                st.text_input("LLM Model",       value=s.llm_model,        disabled=True)
                if s.llm_api_key:
                    st.text_input("API Key",     value="••••••••",          disabled=True)
                if s.llm_provider == "ollama":
                    st.text_input("Ollama URL",  value=s.ollama_base_url,  disabled=True)
                if s.llm_api_base:
                    st.text_input("Base URL",    value=s.llm_api_base,     disabled=True)
                st.text_input("Embed Model",     value=s.embed_model,      disabled=True)
                st.text_input("Weaviate URL",    value=s.weaviate_url,     disabled=True)
                st.text_input("Collection Name", value=s.collection_name,  disabled=True)
                st.text_input("Request Timeout", value=f"{int(s.request_timeout)}s", disabled=True)

                if st.button("Edit Settings", use_container_width=True):
                    st.session_state._reset_settings     = True  # re-seed before widgets render
                    st.session_state._settings_edit_mode = True
                    st.session_state._settings_expanded  = True
                    st.rerun()

            else:
                # ── Edit view ─────────────────────────────────────────────────
                _PROVIDER_LABELS = {
                    "ollama":    "Ollama (Local)",
                    "openai":    "OpenAI",
                    "anthropic": "Anthropic / Claude",
                    "groq":      "Groq  —  Fast & Free Cloud",
                    "custom":    "Custom (OpenAI-compatible URL)",
                }
                st.markdown("**LLM Provider**")
                provider = st.selectbox(
                    "Provider",
                    options=list(_PROVIDER_LABELS.keys()),
                    format_func=_PROVIDER_LABELS.get,
                    key="s_provider",
                )

                st.markdown("**Language Model**")
                st.text_input(
                    "Model Name", key="s_llm_model",
                    help=PROVIDER_MODEL_HINTS.get(provider, ""),
                    placeholder=PROVIDER_MODEL_HINTS.get(provider, ""),
                )

                if provider == "ollama":
                    st.text_input("Ollama URL", key="s_ollama_url",
                                  help="Base URL of your local Ollama server.")
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
                    st.text_input("Base URL", key="s_api_base",
                                  help="OpenAI-compatible API base, e.g. https://your-host/v1")
                    st.text_input("API Key (optional)", key="s_api_key", type="password")

                # Ollama URL field not relevant for cloud providers — keep state in sync
                if provider != "ollama":
                    st.session_state.setdefault("s_ollama_url",
                                                "http://localhost:11434")
                if provider not in ("groq", "openai", "anthropic", "custom"):
                    st.session_state.setdefault("s_api_key", "")
                if provider != "custom":
                    st.session_state.setdefault("s_api_base", "")

                st.markdown("**Embedding Model**")
                st.text_input("Embed Model", key="s_embed_model",
                              help=f"Ollama embedding model (always local). Common: {_EMBED_MODELS}")

                st.markdown("**Vector Store**")
                st.text_input("Weaviate URL",    key="s_weaviate_url",
                              help="URL of your Weaviate instance.")
                st.text_input("Collection Name", key="s_collection",
                              help="Weaviate class name — must start with an uppercase letter.")

                st.markdown("**Performance**")
                st.slider("Request Timeout (s)", min_value=30, max_value=600, step=30,
                          key="s_timeout", help="Max seconds to wait for a model response.")

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
        st.markdown("<div style='height: 32px'></div>", unsafe_allow_html=True)
        col_l, col_c, col_r = st.columns([1, 3, 1])
        with col_c:
            st.markdown(
                "<h2 style='text-align:center; color:#d0e8ff; font-size:1.9rem; font-weight:700;"
                " letter-spacing:-0.5px; margin-bottom:12px;'>How can I help you today?</h2>",
                unsafe_allow_html=True,
            )
            st.markdown(
                "<p style='text-align:center; color:#8ab8dc; font-size:1.05rem; line-height:1.7;"
                " margin-bottom:36px;'>"
                "Your TIBCO integration and messaging expert — review applications, diagnose logs, "
                "and answer questions across the full TIBCO platform stack, from any environment. "
                "Upload files via the sidebar or ask a question directly.</p>",
                unsafe_allow_html=True,
            )
        c1, c2, c3 = st.columns(3)
        with c1:
            st.info(
                "**Integration & Messaging Q&A**\n\n"
                "Ask anything about TIBCO integration and messaging — middleware patterns, "
                "EMS topics and queues, FTL/eFTL, connection pooling, Kubernetes deployment, "
                "error handling, and platform best practices."
            )
        with c2:
            st.info(
                "**Application Review**\n\n"
                "Upload a TIBCO integration application — receive an architect-level review "
                "covering errors, warnings, missing handlers, security gaps, and overall "
                "production readiness."
            )
        with c3:
            st.info(
                "**Log Analysis & Diagnostics**\n\n"
                "Upload integration or messaging logs from any environment — get root-cause "
                "diagnosis, production impact assessment, and exact remediation steps."
            )
        st.markdown("<div style='height: 32px'></div>", unsafe_allow_html=True)

    for msg in st.session_state.messages:
        _render_chat_msg(msg["role"], msg["content"])

    user_input = st.session_state.pop("pending_prompt", None) or st.chat_input(
        "Ask TARA about TIBCO BW / Flogo..."
    )

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        _render_chat_msg("user", user_input)

        # Show animated TARA thinking placeholder
        tara_slot = st.empty()
        tara_slot.markdown(
            '<div class="chat-row chat-tara">'
            f'<div class="chat-avatar">{_TARA_SVG}</div>'
            '<div class="chat-bubble chat-bubble-tara chat-thinking">'
            'TARA is thinking…</div></div>',
            unsafe_allow_html=True,
        )

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
