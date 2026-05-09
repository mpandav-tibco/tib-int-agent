"""
TARA — TIBCO AI Review Agent — Chainlit UI

Run with:
    chainlit run chainlit_app.py
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import chainlit as cl

from tibco_agent.agent.core import PROVIDER_MODEL_HINTS, build_prompt, call_llm
from tibco_agent.config import settings as _cfg
from tibco_agent import feedback as _feedback
from tibco_agent.report.generator import to_html, to_pdf


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
            label="EMS Connection Issue",
            message=(
                "I need help diagnosing a TIBCO EMS or messaging problem. "
                "Ask me: is it connection failure, authentication, message loss, or queue depth buildup? "
                "Give targeted diagnostic commands based on my answers."
            ),
        ),
    ]


# ── Agent builder ─────────────────────────────────────────────────────────────

def _build_agent_safe():
    """Build the ReActAgent. Returns None if Weaviate / KB is unavailable."""
    try:
        from tibco_agent.agent.core import build_agent
        return build_agent()
    except Exception:
        return None


# ── Chat start ────────────────────────────────────────────────────────────────

@cl.on_chat_start
async def on_chat_start() -> None:
    await cl.ChatSettings(
        [
            cl.Select(
                id="provider",
                label="LLM Provider",
                values=["ollama", "openai", "anthropic", "groq", "ollama-cloud", "custom"],
                initial_value=_cfg.llm_provider,
            ),
            cl.TextInput(
                id="model",
                label="Model",
                initial=_cfg.llm_model,
                placeholder=PROVIDER_MODEL_HINTS.get(_cfg.llm_provider, ""),
            ),
            cl.TextInput(
                id="api_key",
                label="API Key",
                initial="",
                placeholder="Leave blank for local Ollama",
            ),
            cl.TextInput(
                id="api_base",
                label="API Base URL",
                initial=_cfg.llm_api_base,
                placeholder="For custom / Groq / Ollama Cloud",
            ),
            cl.TextInput(
                id="ollama_url",
                label="Ollama URL",
                initial=_cfg.ollama_base_url,
            ),
            cl.TextInput(
                id="embed_model",
                label="Embed Model",
                initial=_cfg.embed_model,
                placeholder="nomic-embed-text",
            ),
            cl.TextInput(
                id="weaviate_url",
                label="Weaviate URL",
                initial=_cfg.weaviate_url,
            ),
            cl.TextInput(
                id="collection",
                label="Collection Name",
                initial=_cfg.collection_name,
            ),
            cl.Slider(
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
    agent = await loop.run_in_executor(None, _build_agent_safe)
    cl.user_session.set("agent", agent)
    cl.user_session.set("flogo_content", "")
    cl.user_session.set("bw_content", "")
    cl.user_session.set("log_content", "")
    cl.user_session.set("chat_history", [])
    cl.user_session.set("zip_markdown", "")


# ── Settings update ───────────────────────────────────────────────────────────

@cl.on_settings_update
async def on_settings_update(new_settings: dict) -> None:
    try:
        _cfg.apply(
            llm_provider=new_settings.get("provider", _cfg.llm_provider),
            llm_model=new_settings.get("model", _cfg.llm_model),
            llm_api_key=new_settings.get("api_key", "") or "",
            llm_api_base=new_settings.get("api_base", "") or "",
            ollama_base_url=new_settings.get("ollama_url", _cfg.ollama_base_url),
            embed_model=new_settings.get("embed_model", _cfg.embed_model),
            weaviate_url=new_settings.get("weaviate_url", _cfg.weaviate_url),
            collection_name=new_settings.get("collection", _cfg.collection_name),
            request_timeout=float(new_settings.get("timeout", _cfg.request_timeout)),
        )
        loop = asyncio.get_event_loop()
        agent = await loop.run_in_executor(None, _build_agent_safe)
        cl.user_session.set("agent", agent)
        await cl.Message(
            content=f"Settings updated — **{_cfg.llm_provider}** / `{_cfg.llm_model}`. Agent rebuilt."
        ).send()
    except Exception as exc:
        await cl.Message(content=f"Settings error: {exc}").send()


# ── Report helpers ────────────────────────────────────────────────────────────

def _make_report_elements(stem: str, md_text: str, html_text: str, pdf_bytes: bytes) -> list:
    """Write report content to temp files and return cl.File elements."""
    elements = []

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(md_text)
        elements.append(cl.File(name=f"{stem}_report.md", path=f.name, display="side"))

    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html_text)
        elements.append(cl.File(name=f"{stem}_report.html", path=f.name, display="side"))

    with tempfile.NamedTemporaryFile(mode="wb", suffix=".pdf", delete=False) as f:
        f.write(pdf_bytes)
        elements.append(cl.File(name=f"{stem}_report.pdf", path=f.name, display="side"))

    return elements


def _top_findings_md(report, n: int = 5) -> str:
    """Return a short bullet list of the most severe findings."""
    findings = sorted(
        report.findings,
        key=lambda f: ({"ERROR": 0, "WARNING": 1, "INFO": 2, "GOOD": 3}.get(f.severity.value, 9)),
    )
    if not findings:
        return "_No issues detected._"
    return "\n".join(
        f"- **[{f.severity.value}]** {f.title} — `{f.location}`"
        for f in findings[:n]
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
            f"Download the full report (MD / HTML / PDF) below, "
            f"or ask me to review the findings.\n\n"
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

    md_text = bwa._report_to_markdown(report)
    html_text = await loop.run_in_executor(None, lambda: to_html(report))
    pdf_bytes = await loop.run_in_executor(None, lambda: to_pdf(report))
    elements = _make_report_elements(Path(filename).stem, md_text, html_text, pdf_bytes)

    await cl.Message(
        content=(
            f"**BW Process Analysis: `{filename}`**\n\n"
            f"Found **{report.error_count} error(s)** and **{report.warning_count} warning(s)**. "
            f"Download the full report (MD / HTML / PDF) below, "
            f"or ask me to review the findings.\n\n"
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
            f"Download the full report (MD / HTML / PDF) below, "
            f"or ask me to diagnose the issues.\n\n"
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

    stem = Path(filename).stem
    elements = [cl.File(name=f"{stem}_project_report.md", path=tmp_path, display="side")]

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
            f"{cross_note}\n\n"
            "Download the full project report (MD), or ask me to review the findings."
        ),
        elements=elements,
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

        elif name.endswith(".zip"):
            with open(element.path, "rb") as fh:
                zip_bytes = fh.read()
            await _analyze_zip(zip_bytes, element.name)

    # Re-read from session in case _analyze_* updated them
    flogo_content = cl.user_session.get("flogo_content") or flogo_content
    bw_content    = cl.user_session.get("bw_content")    or bw_content
    log_content   = cl.user_session.get("log_content")   or log_content

    # If only files with no text question, stop here
    question = (message.content or "").strip()
    if has_files and not question:
        return
    if not question:
        return

    # Inject project ZIP context when no individual files are loaded
    if zip_markdown and not (flogo_content or bw_content or log_content):
        question = question + "\n\n" + zip_markdown

    agent = cl.user_session.get("agent")

    # ── Build prompt + run LLM ────────────────────────────────────────────────
    thinking = cl.Message(content="Searching knowledge base and building context…")
    await thinking.send()

    loop = asyncio.get_event_loop()

    try:
        async with cl.Step(name="Knowledge Base Search", type="retrieval") as kb_step:
            prompt = await loop.run_in_executor(
                None,
                lambda: build_prompt(
                    question,
                    flogo_content,
                    log_content,
                    bw_content,
                    chat_history=chat_history or None,
                ),
            )
            kb_step.output = "Context assembled"

        async with cl.Step(name="LLM", type="llm") as llm_step:
            if agent is None:
                # Fallback: direct LLM call without agent tools
                from tibco_agent.agent.core import configure_llm
                from llama_index.core import Settings as LISettings
                await loop.run_in_executor(None, configure_llm)
                response = await loop.run_in_executor(
                    None, lambda: str(LISettings.llm.complete(prompt))
                )
            else:
                response = await loop.run_in_executor(
                    None, lambda: call_llm(agent, prompt)
                )
            llm_step.output = f"{len(response)} chars"

    except Exception as exc:
        if _cfg.llm_provider == "ollama":
            hint = (
                "Check that Ollama is running: `ollama serve`\n"
                f"Check that the model is pulled: `ollama pull {_cfg.llm_model}`\n"
                "Check that Weaviate is running: `docker-compose up -d`"
            )
        else:
            hint = (
                f"Provider: **{_cfg.llm_provider}** · Model: `{_cfg.llm_model}`\n\n"
                "- Verify your **API Key** is correct in Settings\n"
                "- Confirm the model name is available for your provider\n"
                "- Check that Weaviate is running: `docker-compose up -d`"
            )
        response = f"**Error:** {exc}\n\n{hint}"

    thinking.content = response
    await thinking.update()

    # Persist feedback with msg index approximation
    msg_idx = len(chat_history) // 2
    _feedback.record(msg_idx, "", question, response)

    # Persist chat history (last 8 messages = 4 turns)
    chat_history.append({"role": "user", "content": question})
    chat_history.append({"role": "assistant", "content": response})
    cl.user_session.set("chat_history", chat_history[-8:])
