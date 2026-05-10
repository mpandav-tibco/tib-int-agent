"""
TARA — TIBCO AI Review Agent — Chainlit UI

Run with:
    chainlit run chainlit_app.py
"""
from __future__ import annotations

import asyncio
import dataclasses
import datetime
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

import chainlit as cl
from chainlit.input_widget import Select, TextInput, Slider

from tibco_agent.agent.core import PROVIDER_MODEL_HINTS, build_prompt, _clean_response
from tibco_agent.config import settings as _cfg
from tibco_agent import feedback as _feedback
from tibco_agent.report.generator import to_html, to_pdf

log = logging.getLogger(__name__)


# ── Optional password auth (activate by setting CHAINLIT_AUTH_SECRET env var) ─

@cl.password_auth_callback
def auth_callback(username: str, password: str) -> Optional[cl.User]:
    """
    Password auth — only enforced when CHAINLIT_AUTH_SECRET is set in the environment.
    Configure credentials via TARA_USERNAME / TARA_PASSWORD env vars (defaults: tara / tara).
    Leave CHAINLIT_AUTH_SECRET unset for local development (no login required).
    """
    expected_user = os.getenv("TARA_USERNAME", "tara")
    expected_pass = os.getenv("TARA_PASSWORD", "tara")
    if os.getenv("CHAINLIT_AUTH_SECRET") and expected_user == "tara" and expected_pass == "tara":
        log.warning(
            "CHAINLIT_AUTH_SECRET is set but default credentials (tara/tara) are in use — "
            "set TARA_USERNAME and TARA_PASSWORD for production deployments."
        )
    if username == expected_user and password == expected_pass:
        return cl.User(identifier=username, metadata={"role": "admin"})
    return None


# ── Suggestion chip starters ──────────────────────────────────────────────────

@cl.set_starters
async def set_starters() -> list[cl.Starter]:
    return [
        cl.Starter(
            label="Review Flogo App",
            message="Review the uploaded .flogo file for issues, security gaps, and production readiness.",
        ),
        cl.Starter(
            label="Review BW Process",
            message="Review the uploaded .bwp BusinessWorks process for fault handling, hardcoded values, and best practices.",
        ),
        cl.Starter(
            label="Diagnose Pod Logs",
            message="Diagnose the errors in the uploaded pod log. Give me the root cause and exact remediation steps for each issue.",
        ),
        cl.Starter(
            label="Pod Won't Start",
            message=(
                "I need structured help troubleshooting a Kubernetes pod that won't start. "
                "Ask me one question at a time: first what error I'm seeing "
                "(CrashLoopBackOff, OOMKilled, Pending, ImagePullBackOff, etc.), "
                "then guide me to the relevant diagnostic output. "
                "Give specific `kubectl` commands. Work toward a root cause."
            ),
        ),
        cl.Starter(
            label="Pre-Deployment Checklist",
            message=(
                "Run me through a pre-deployment checklist for a TIBCO application going to production. "
                "Ask me: Flogo or BW, Kubernetes or on-prem. "
                "Then cover: error handling, timeouts, SSL, credential management, "
                "health probes, resource limits, and observability. Be structured — one area at a time."
            ),
        ),
        cl.Starter(
            label="Review EMS Config",
            message="Review the uploaded tibemsd.conf EMS configuration file for security, reliability, and production readiness issues.",
        ),
        cl.Starter(
            label="EMS Connection Issue",
            message=(
                "I need help diagnosing a TIBCO EMS or messaging problem. "
                "Ask me: is it connection failure, authentication, message loss, or queue depth buildup? "
                "Give targeted diagnostic commands based on my answers."
            ),
        ),
    ]


# ── Agent builder ─────────────────────────────────────────────────────────────

def _build_agent_safe(cfg=None):
    """Build the ReActAgent. Returns (agent, degraded) — agent is None if LLM init fails."""
    try:
        from tibco_agent.agent.core import build_agent
        return build_agent(cfg=cfg), False
    except Exception as exc:
        log.exception("Agent build failed (degraded mode): %s", exc)
        return None, True


# ── Chat start ────────────────────────────────────────────────────────────────

@cl.on_chat_start
async def on_chat_start() -> None:
    await cl.ChatSettings(
        [
            Select(
                id="provider",
                label="LLM Provider",
                values=["ollama", "openai", "anthropic", "groq", "ollama-cloud", "custom"],
                initial_value=_cfg.llm_provider,
            ),
            TextInput(
                id="model",
                label="Model",
                initial=_cfg.llm_model,
                placeholder=PROVIDER_MODEL_HINTS.get(_cfg.llm_provider, ""),
            ),
            TextInput(
                id="api_key",
                label="API Key",
                initial="",
                placeholder="Leave blank for local Ollama",
            ),
            TextInput(
                id="api_base",
                label="API Base URL",
                initial=_cfg.llm_api_base,
                placeholder="For custom / Groq / Ollama Cloud",
            ),
            TextInput(
                id="ollama_url",
                label="Ollama URL",
                initial=_cfg.ollama_base_url,
            ),
            TextInput(
                id="embed_model",
                label="Embed Model",
                initial=_cfg.embed_model,
                placeholder="nomic-embed-text",
            ),
            TextInput(
                id="weaviate_url",
                label="Weaviate URL",
                initial=_cfg.weaviate_url,
            ),
            TextInput(
                id="collection",
                label="Collection Name",
                initial=_cfg.collection_name,
            ),
            Slider(
                id="timeout",
                label="Timeout (s)",
                min=30,
                max=600,
                step=30,
                initial=int(_cfg.request_timeout),
            ),
        ]
    ).send()

    loop = asyncio.get_event_loop()
    agent, degraded = await loop.run_in_executor(None, _build_agent_safe)
    cl.user_session.set("agent", agent)
    cl.user_session.set("session_cfg", None)  # populated by on_settings_update
    cl.user_session.set("flogo_content", "")
    cl.user_session.set("bw_content", "")
    cl.user_session.set("log_content", "")
    cl.user_session.set("chat_history", [])
    cl.user_session.set("zip_markdown", "")
    cl.user_session.set("last_question", "")
    cl.user_session.set("last_response", "")
    cl.user_session.set("tmp_files", [])  # track temp paths for cleanup

    if degraded:
        await cl.Message(
            author="TARA",
            content=(
                "> ⚠️ **Degraded mode** — agent failed to initialise (LLM or Weaviate may be unavailable). "
                "File analysis still works, but KB search and LLM responses are disabled. "
                "Check Settings or server logs."
            ),
        ).send()

    await cl.Message(
        author="TARA",
        content=(
            "## Hi, I'm TARA — your TIBCO AI Review Agent 👋\n\n"
            "I'm an expert assistant for **TIBCO BusinessWorks**, **Flogo Enterprise**, "
            "**EMS**, and **Messaging** (FTL, eFTL, Pulsar).\n\n"
            "**What I can do:**\n\n"
            "| Capability | How to use |\n"
            "|---|---|\n"
            "| Answer TIBCO questions | Just type your question |\n"
            "| Review a Flogo app (38 checks) | Upload a `.flogo` file |\n"
            "| Review a BW process | Upload a `.bwp` or `.xml` file |\n"
            "| Diagnose pod / app logs | Upload a `.log` or `.txt` file |\n"
            "| Analyse Kubernetes manifests | Upload a `.yaml` or `.yml` file |\n"
            "| Review EMS config | Upload a `tibemsd.conf` file |\n"
            "| Analyse a full project | Upload a `.zip` archive |\n\n"
            "**Quick start — click a prompt to begin:**\n\n"
            "- 🔍 *Review the uploaded .flogo file for issues, security gaps, and production readiness.*\n"
            "- 🔍 *Review the uploaded .bwp BusinessWorks process for fault handling and best practices.*\n"
            "- 🩺 *Diagnose the errors in the uploaded pod log. Give root cause and remediation steps.*\n"
            "- 🚀 *Run me through a pre-deployment checklist for a TIBCO application going to production.*\n"
            "- 🔧 *Help me troubleshoot a Kubernetes pod that won't start.*\n"
            "- 📡 *Help me diagnose a TIBCO EMS or messaging connection issue.*\n\n"
            "_Open ⚙ Settings to switch LLM provider or model._"
        ),
    ).send()


# ── Settings update ───────────────────────────────────────────────────────────

@cl.on_settings_update
async def on_settings_update(new_settings: dict) -> None:
    try:
        from tibco_agent.config import Settings as AppSettings
        base = cl.user_session.get("session_cfg") or _cfg
        session_cfg = dataclasses.replace(
            base,
            llm_provider=new_settings.get("provider", base.llm_provider),
            llm_model=new_settings.get("model", base.llm_model),
            llm_api_key=new_settings.get("api_key", "") or "",
            llm_api_base=new_settings.get("api_base", "") or "",
            ollama_base_url=new_settings.get("ollama_url", base.ollama_base_url),
            embed_model=new_settings.get("embed_model", base.embed_model),
            weaviate_url=new_settings.get("weaviate_url", base.weaviate_url),
            collection_name=new_settings.get("collection", base.collection_name),
            request_timeout=float(new_settings.get("timeout", base.request_timeout)),
        )
        cl.user_session.set("session_cfg", session_cfg)
        loop = asyncio.get_event_loop()
        agent, degraded = await loop.run_in_executor(None, lambda: _build_agent_safe(cfg=session_cfg))
        cl.user_session.set("agent", agent)
        status = " ⚠️ (degraded — check logs)" if degraded else ""
        await cl.Message(
            content=f"Settings updated — **{session_cfg.llm_provider}** / `{session_cfg.llm_model}`. Agent rebuilt.{status}"
        ).send()
    except Exception as exc:
        log.exception("Settings update failed: %s", exc)
        await cl.Message(content=f"Settings error: {exc}").send()


# ── Streaming LLM ─────────────────────────────────────────────────────────────

async def _stream_into(prompt: str, out_msg: cl.Message) -> str:
    """
    Stream LLM response token-by-token into out_msg.
    Handles <think>...</think> blocks (deepseek-r1) by filtering them silently.
    Falls back to a blocking call if the provider does not support streaming.
    Returns the final cleaned response string.
    """
    from tibco_agent.agent.core import configure_llm
    from llama_index.core import Settings as LISettings

    loop = asyncio.get_event_loop()
    session_cfg = cl.user_session.get("session_cfg")
    await loop.run_in_executor(None, lambda: configure_llm(session_cfg))
    lm = LISettings.llm

    accumulated = ""
    prev_cleaned_len = 0

    try:
        # astream_complete may be an async generator function or a coroutine
        raw = lm.astream_complete(prompt)
        if asyncio.iscoroutine(raw):
            raw = await raw

        async for chunk in raw:
            token = chunk.delta or getattr(chunk, "text", "") or ""
            if not token:
                continue
            accumulated += token

            # Stream only the clean (non-think) delta
            curr_cleaned = _clean_response(accumulated)
            delta = curr_cleaned[prev_cleaned_len:]
            if delta:
                await out_msg.stream_token(delta)
                prev_cleaned_len = len(curr_cleaned)

        # Flush any trailing clean content not yet streamed
        final_cleaned = _clean_response(accumulated)
        remaining = final_cleaned[prev_cleaned_len:]
        if remaining:
            await out_msg.stream_token(remaining)

        # Do NOT call out_msg.update() here — caller does one final update
        # so Chainlit only renders the full content once (prevents duplication).
        return final_cleaned

    except Exception:
        # Provider does not support streaming — fall back to blocking call
        agent = cl.user_session.get("agent")
        if agent:
            from tibco_agent.agent.core import call_llm
            result = await loop.run_in_executor(None, lambda: call_llm(agent, prompt))
        else:
            result = await loop.run_in_executor(None, lambda: str(lm.complete(prompt)))
        cleaned = _clean_response(result)
        out_msg.content = cleaned
        # Caller handles the final update
        return cleaned


# ── Feedback & export actions ─────────────────────────────────────────────────

@cl.action_callback("thumbs_up")
async def on_thumbs_up(action: cl.Action) -> None:
    q = cl.user_session.get("last_question", "")
    r = cl.user_session.get("last_response", "")
    idx = len(cl.user_session.get("chat_history", [])) // 2
    _feedback.record(idx, "up", q, r)
    await action.remove()


@cl.action_callback("thumbs_down")
async def on_thumbs_down(action: cl.Action) -> None:
    q = cl.user_session.get("last_question", "")
    r = cl.user_session.get("last_response", "")
    idx = len(cl.user_session.get("chat_history", [])) // 2
    _feedback.record(idx, "down", q, r)
    await action.remove()


@cl.action_callback("export_chat")
async def on_export_chat(action: cl.Action) -> None:
    history = cl.user_session.get("chat_history", [])
    lines = [
        "# TARA Chat Export",
        f"*{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
    ]
    for m in history:
        role = "You" if m["role"] == "user" else "TARA"
        lines += [f"**{role}:** {m['content']}", ""]
    md_text = "\n".join(lines)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(md_text)
        tmp_path = f.name
    _track_tmp(tmp_path)
    fname = f"tara-chat-{datetime.date.today()}.md"
    await cl.Message(
        content=f"Chat exported as `{fname}`.",
        elements=[cl.File(name=fname, path=tmp_path, display="side")],
    ).send()


async def _set_msg(m: cl.Message, text: str) -> None:
    """Update a message's content in-place (used for progress updates from threads)."""
    m.content = text
    await m.update()


def _make_actions() -> list:
    """Return fresh Action objects for each message (Chainlit binds them per-message)."""
    return [
        cl.Action(name="thumbs_up",   label="👍", value="up",     description="Mark as helpful",     payload={"action": "up"}),
        cl.Action(name="thumbs_down", label="👎", value="down",   description="Mark as not helpful", payload={"action": "down"}),
        cl.Action(name="export_chat", label="📥 Export", value="export", description="Export chat",   payload={"action": "export"}),
    ]


@cl.on_chat_end
async def on_chat_end() -> None:
    """Remove temporary report files created during this session."""
    paths: list = cl.user_session.get("tmp_files") or []
    for p in paths:
        try:
            Path(p).unlink(missing_ok=True)
        except Exception:
            pass


# ── Report helpers ────────────────────────────────────────────────────────────

def _track_tmp(path: str) -> None:
    """Register a temp file path for cleanup on session end."""
    try:
        paths: list = cl.user_session.get("tmp_files") or []
        paths.append(path)
        cl.user_session.set("tmp_files", paths)
    except Exception:
        pass  # session may not be active during tests


def _make_report_elements(stem: str, md_text: str, html_text: str, pdf_bytes: bytes) -> list:
    elements = []
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(md_text)
        _track_tmp(f.name)
        elements.append(cl.File(name=f"{stem}_report.md", path=f.name, display="side"))
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html_text)
        _track_tmp(f.name)
        elements.append(cl.File(name=f"{stem}_report.html", path=f.name, display="side"))
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".pdf", delete=False) as f:
        f.write(pdf_bytes)
        _track_tmp(f.name)
        elements.append(cl.File(name=f"{stem}_report.pdf", path=f.name, display="side"))
    return elements


def _top_findings_md(report, n: int = 5) -> str:
    findings = sorted(
        report.findings,
        key=lambda f: {"ERROR": 0, "WARNING": 1, "INFO": 2, "GOOD": 3}.get(f.severity.value, 9),
    )
    if not findings:
        return "_No issues detected._"
    return "\n".join(
        f"- **[{f.severity.value}]** {f.title} — `{f.location}`" for f in findings[:n]
    )


# ── File analysis helpers ─────────────────────────────────────────────────────

async def _analyze_flogo(content: str, filename: str) -> None:
    loop = asyncio.get_event_loop()
    async with cl.Step(name=f"Flogo: {filename}", type="tool") as step:
        from tibco_agent.analyzers.flogo_analyzer import FlogoAnalyzer
        report = await loop.run_in_executor(
            None, lambda: FlogoAnalyzer().analyze(content, source=filename)
        )
        step.output = f"{report.error_count} error(s), {report.warning_count} warning(s)"
    cl.user_session.set("flogo_content", content)
    md_text = report.to_markdown()
    html_text = await loop.run_in_executor(None, lambda: to_html(report))
    pdf_bytes = await loop.run_in_executor(None, lambda: to_pdf(report))
    elements = _make_report_elements(Path(filename).stem, md_text, html_text, pdf_bytes)
    await cl.Message(
        content=(
            f"**Flogo Analysis: `{filename}`**\n\n"
            f"Found **{report.error_count} error(s)** and **{report.warning_count} warning(s)**. "
            "Download the full report (MD / HTML / PDF) below, or ask me to review the findings.\n\n"
            f"**Top issues:**\n{_top_findings_md(report)}"
        ),
        elements=elements,
    ).send()


async def _analyze_bw(content: str, filename: str) -> None:
    loop = asyncio.get_event_loop()
    async with cl.Step(name=f"BW: {filename}", type="tool") as step:
        from tibco_agent.analyzers.bw_analyzer import BWAnalyzer
        bwa = BWAnalyzer()
        report = await loop.run_in_executor(
            None, lambda: bwa.analyze(content, source=filename)
        )
        step.output = f"{report.error_count} error(s), {report.warning_count} warning(s)"
    cl.user_session.set("bw_content", content)
    md_text = bwa.report_to_markdown(report)
    html_text = await loop.run_in_executor(None, lambda: to_html(report))
    pdf_bytes = await loop.run_in_executor(None, lambda: to_pdf(report))
    elements = _make_report_elements(Path(filename).stem, md_text, html_text, pdf_bytes)
    await cl.Message(
        content=(
            f"**BW Process Analysis: `{filename}`**\n\n"
            f"Found **{report.error_count} error(s)** and **{report.warning_count} warning(s)**. "
            "Download the full report (MD / HTML / PDF) below, or ask me to review the findings.\n\n"
            f"**Top issues:**\n{_top_findings_md(report)}"
        ),
        elements=elements,
    ).send()


async def _analyze_log(content: str, filename: str) -> None:
    loop = asyncio.get_event_loop()
    async with cl.Step(name=f"Log: {filename}", type="tool") as step:
        from tibco_agent.analyzers.log_analyzer import LogAnalyzer
        report = await loop.run_in_executor(
            None, lambda: LogAnalyzer().analyze(content, source=filename)
        )
        step.output = f"{report.error_count} error(s), {report.warning_count} warning(s)"
    cl.user_session.set("log_content", content)
    md_text = report.to_markdown()
    html_text = await loop.run_in_executor(None, lambda: to_html(report))
    pdf_bytes = await loop.run_in_executor(None, lambda: to_pdf(report))
    elements = _make_report_elements(Path(filename).stem, md_text, html_text, pdf_bytes)
    await cl.Message(
        content=(
            f"**Log Analysis: `{filename}`**\n\n"
            f"Found **{report.error_count} error(s)** and **{report.warning_count} warning(s)**. "
            "Download the full report (MD / HTML / PDF) below, or ask me to diagnose the issues.\n\n"
            f"**Top issues:**\n{_top_findings_md(report)}"
        ),
        elements=elements,
    ).send()


async def _analyze_kube(content: str, filename: str) -> None:
    loop = asyncio.get_event_loop()
    async with cl.Step(name=f"Kubernetes: {filename}", type="tool") as step:
        from tibco_agent.analyzers.kube_analyzer import KubeAnalyzer
        report = await loop.run_in_executor(
            None, lambda: KubeAnalyzer().analyze(content, source=filename)
        )
        step.output = f"{report.error_count} error(s), {report.warning_count} warning(s)"
    md_text = report.to_markdown()
    html_text = await loop.run_in_executor(None, lambda: to_html(report))
    pdf_bytes = await loop.run_in_executor(None, lambda: to_pdf(report))
    elements = _make_report_elements(Path(filename).stem, md_text, html_text, pdf_bytes)
    await cl.Message(
        content=(
            f"**Kubernetes Manifest Analysis: `{filename}`**\n\n"
            f"Found **{report.error_count} error(s)** and **{report.warning_count} warning(s)**. "
            "Download the full report below, or ask me to explain the findings.\n\n"
            f"**Top issues:**\n{_top_findings_md(report)}"
        ),
        elements=elements,
    ).send()


async def _analyze_ems(content: str, filename: str) -> None:
    loop = asyncio.get_event_loop()
    async with cl.Step(name=f"EMS Config: {filename}", type="tool") as step:
        from tibco_agent.analyzers.ems_analyzer import EMSAnalyzer
        report = await loop.run_in_executor(
            None, lambda: EMSAnalyzer().analyze(content, source=filename)
        )
        step.output = f"{report.error_count} error(s), {report.warning_count} warning(s)"
    md_text = report.to_markdown()
    html_text = await loop.run_in_executor(None, lambda: to_html(report))
    pdf_bytes = await loop.run_in_executor(None, lambda: to_pdf(report))
    elements = _make_report_elements(Path(filename).stem, md_text, html_text, pdf_bytes)
    await cl.Message(
        content=(
            f"**EMS Configuration Analysis: `{filename}`**\n\n"
            f"Found **{report.error_count} error(s)** and **{report.warning_count} warning(s)**. "
            "Download the full report below, or ask me to explain the findings.\n\n"
            f"**Top issues:**\n{_top_findings_md(report)}"
        ),
        elements=elements,
    ).send()


async def _analyze_zip(zip_bytes: bytes, filename: str) -> None:
    loop = asyncio.get_event_loop()
    async with cl.Step(name=f"Project: {filename}", type="tool") as step:
        from tibco_agent.analyzers.multi_analyzer import analyze_zip
        result = await loop.run_in_executor(
            None, lambda: analyze_zip(zip_bytes, zip_name=filename)
        )
        step.output = (
            f"{len(result.flogo_reports)} Flogo, {len(result.bw_reports)} BW — "
            f"{result.total_errors} error(s), {result.total_warnings} warning(s)"
        )
    md_text = result.to_markdown()
    cl.user_session.set("zip_markdown", md_text[:6000])
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(md_text)
        tmp_path = f.name
    _track_tmp(tmp_path)
    stem = Path(filename).stem
    cross_note = (
        f"\n**Cross-file issues:** {len(result.cross_flow_issues)} found — ask me to explain them."
        if result.cross_flow_issues
        else ""
    )
    await cl.Message(
        content=(
            f"**Project Analysis: `{filename}`**\n\n"
            f"Analyzed **{len(result.flogo_reports)} Flogo** and **{len(result.bw_reports)} BW** file(s).  \n"
            f"Total: **{result.total_errors} error(s)**, **{result.total_warnings} warning(s)**."
            f"{cross_note}\n\nDownload the full project report (MD), or ask me to review the findings."
        ),
        elements=[cl.File(name=f"{stem}_project_report.md", path=tmp_path, display="side")],
    ).send()


# ── Main message handler ──────────────────────────────────────────────────────

@cl.on_message
async def on_message(message: cl.Message) -> None:
    flogo_content = cl.user_session.get("flogo_content") or ""
    bw_content    = cl.user_session.get("bw_content")    or ""
    log_content   = cl.user_session.get("log_content")   or ""
    chat_history  = cl.user_session.get("chat_history")  or []
    zip_markdown  = cl.user_session.get("zip_markdown")  or ""

    # ── Process file attachments ──────────────────────────────────────────────
    has_files = False
    for element in message.elements:
        if not isinstance(element, cl.File):
            continue
        has_files = True
        try:
            with open(element.path, "r", encoding="utf-8", errors="replace") as fh:
                text_content = fh.read()
        except Exception:
            with open(element.path, "rb") as fh:
                text_content = fh.read().decode("utf-8", errors="replace")

        name = element.name.lower()
        if name.endswith(".flogo") or name.endswith(".json"):
            flogo_content = text_content
            await _analyze_flogo(text_content, element.name)
        elif name.endswith(".bwp") or name.endswith(".xml"):
            bw_content = text_content
            await _analyze_bw(text_content, element.name)
        elif name.endswith(".log") or name.endswith(".txt"):
            log_content = text_content
            await _analyze_log(text_content, element.name)
        elif name.endswith((".yaml", ".yml")):
            await _analyze_kube(text_content, element.name)
        elif name.endswith(".conf"):
            await _analyze_ems(text_content, element.name)
        elif name.endswith(".zip"):
            with open(element.path, "rb") as fh:
                zip_bytes = fh.read()
            await _analyze_zip(zip_bytes, element.name)

    # Re-read from session in case _analyze_* updated them
    flogo_content = cl.user_session.get("flogo_content") or flogo_content
    bw_content    = cl.user_session.get("bw_content")    or bw_content
    log_content   = cl.user_session.get("log_content")   or log_content

    question = (message.content or "").strip()
    if has_files and not question:
        return
    if not question:
        return

    # Inject project ZIP context when no individual files are loaded
    if zip_markdown and not (flogo_content or bw_content or log_content):
        question = question + "\n\n" + zip_markdown

    loop = asyncio.get_event_loop()
    response = ""

    try:
        # ── Show live progress while build_prompt runs in a thread ────────────
        # out_msg is created immediately so the user sees something right away.
        # The on_step callback updates its content from the thread via the event loop.
        out_msg = cl.Message(content="_Searching knowledge base…_", author="TARA")
        await out_msg.send()

        def _on_step(msg: str, _pct: int) -> None:
            try:
                asyncio.run_coroutine_threadsafe(
                    _set_msg(out_msg, f"_{msg}_"),
                    loop,
                )
            except Exception:
                pass

        prompt = await loop.run_in_executor(
            None,
            lambda: build_prompt(
                question,
                flogo_content,
                log_content,
                bw_content,
                on_step=_on_step,
                chat_history=chat_history or None,
            ),
        )

        # ── Clear the progress text and stream the actual response ────────────
        out_msg.content = ""
        await out_msg.update()
        response = await _stream_into(prompt, out_msg)

        # Attach actions without re-setting content.
        # stream_token() already rendered the full response incrementally;
        # re-assigning content before update() causes Chainlit 2.x to
        # append the full text again, making the response appear twice.
        out_msg.actions = _make_actions()
        await out_msg.update()

    except Exception as exc:
        session_cfg = cl.user_session.get("session_cfg") or _cfg
        if session_cfg.llm_provider == "ollama":
            hint = (
                "Check Ollama is running: `ollama serve`\n"
                f"Check model is pulled: `ollama pull {session_cfg.llm_model}`\n"
                "Check Weaviate is running: `docker-compose up -d`"
            )
        else:
            hint = (
                f"Provider: **{session_cfg.llm_provider}** · Model: `{session_cfg.llm_model}`\n\n"
                "- Verify your **API Key** is correct in Settings\n"
                "- Confirm the model name is available for your provider\n"
                "- Check Weaviate is running: `docker-compose up -d`"
            )
        response = f"**Error:** {exc}\n\n{hint}"
        await cl.Message(content=response).send()

    # ── Persist session state ─────────────────────────────────────────────────
    cl.user_session.set("last_question", question)
    cl.user_session.set("last_response", response)
    chat_history.append({"role": "user", "content": question})
    chat_history.append({"role": "assistant", "content": response})
    cl.user_session.set("chat_history", chat_history[-8:])
