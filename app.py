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

  <div class="agent-title">TIBCO Integration AI Agent</div>
  <div class="agent-status">
    <span class="status-dot"></span>
    Ollama &nbsp;·&nbsp; Weaviate Vector Search &nbsp;·&nbsp; BW &amp; Flogo Specialist
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
