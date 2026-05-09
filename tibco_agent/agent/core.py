from __future__ import annotations

import asyncio
import threading

from llama_index.core import Settings
from llama_index.core.agent import ReActAgent
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama

from tibco_agent.config import settings
from tibco_agent.tools.registry import ToolRegistry
from tibco_agent.tools.agent_tools import build_knowledge_tool, build_flogo_tool, build_log_tool

_SYSTEM_PROMPT = """\
You are a TIBCO Integration expert assistant specializing in:
- TIBCO BusinessWorks 5, 6, and BWCE (container edition)
- TIBCO Flogo Enterprise

Your responsibilities:
1. Answer questions about BW/Flogo best practices, patterns, and implementation
2. Review .flogo application files and report issues with actionable recommendations
3. Diagnose errors from Kubernetes pod logs of BW/Flogo containers
4. Provide performance tuning, troubleshooting, and architectural guidance

Rules:
- Always use the provided tools for knowledge lookups. Do not answer from memory for specific error codes, property names, or config values.
- When the prompt already contains a "## Static Analysis Results" or "## Log Analysis Results" section, treat those findings as authoritative facts. Do NOT re-describe the app structure or log content — go straight to what needs to be fixed and why.
- Structure your answer: lead with a one-line verdict, then list issues by severity (Errors first, then Warnings), then give concrete next steps.
- Cite the specific flow name, activity name, or log line number for every issue.
- Prioritize errors over warnings. Be concise and actionable.
- If you are not confident, say so. Do not invent configuration values or API names.
"""

# num_ctx limits the KV cache — reduces RAM from ~20GB to ~5GB for llama3.1:8b
_NUM_CTX = int(settings.request_timeout)  # reuse slot; default via env NUM_CTX
_NUM_CTX = 4096


def _make_llm() -> Ollama:
    return Ollama(
        model=settings.llm_model,
        base_url=settings.ollama_base_url,
        request_timeout=settings.request_timeout,
        context_window=_NUM_CTX,
        additional_kwargs={"options": {"num_ctx": _NUM_CTX}},
    )


def configure_llm() -> None:
    Settings.llm = _make_llm()
    Settings.embed_model = OllamaEmbedding(
        model_name=settings.embed_model,
        base_url=settings.ollama_base_url,
    )


def build_agent(registry: ToolRegistry | None = None) -> ReActAgent:
    configure_llm()

    if registry is None:
        registry = ToolRegistry.get()
        if len(registry) == 0:
            registry.register(build_knowledge_tool())
            registry.register(build_flogo_tool())
            registry.register(build_log_tool())

    # LlamaIndex 0.14+ uses workflow-based agents — constructor replaces from_tools()
    return ReActAgent(
        tools=registry.all_tools(),
        llm=Settings.llm,
        system_prompt=_SYSTEM_PROMPT,
        verbose=False,
        timeout=600.0,
    )


# Persistent event loop — avoids "Event loop is closed" on repeated calls.
# Runs in a background thread so it never conflicts with Streamlit or asyncio.run().
_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: threading.Thread | None = None
_loop_lock = threading.Lock()


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop, _loop_thread
    with _loop_lock:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
            _loop_thread = threading.Thread(target=_loop.run_forever, daemon=True)
            _loop_thread.start()
    return _loop


async def _ask_async(agent: ReActAgent, prompt: str) -> str:
    handler = agent.run(prompt)
    result = await handler
    return str(result)


def ask(agent: ReActAgent, question: str, flogo_content: str = "", log_content: str = "") -> str:
    # Run analyzers eagerly when files are uploaded — injecting structured findings
    # directly into the prompt is far more reliable than asking the LLM to call a
    # tool, especially with smaller local models like llama3.1:8b.
    parts = [question]

    if flogo_content.strip():
        from tibco_agent.analyzers.flogo_analyzer import FlogoAnalyzer
        report = FlogoAnalyzer().analyze(flogo_content)   # full content — LLM sees the report, not the raw JSON
        parts.append(
            "\n\n## Static Analysis Results (uploaded .flogo file)\n\n"
            + report.to_markdown()
            + "\n\n---\n"
            "You are a senior TIBCO Integration architect reviewing this application. "
            "Using the structured analysis above, write a comprehensive review covering:\n"
            "1. **Overall verdict** — one paragraph on whether the implementation is production-ready.\n"
            "2. **What is well implemented** — acknowledge the strengths from the analysis.\n"
            "3. **Critical issues** — explain each error: why it matters in production, not just what it is.\n"
            "4. **Improvements & recommendations** — beyond the detected issues: patterns, scalability, observability, security.\n"
            "Be specific. Cite flow names, activity names, and endpoint paths. "
            "Write as a peer talking to a developer, not as a checklist generator."
        )

    if log_content.strip():
        from tibco_agent.analyzers.log_analyzer import LogAnalyzer
        report = LogAnalyzer().analyze(log_content)   # full content
        parts.append(
            "\n\n## Log Analysis Results (uploaded pod log)\n\n"
            + report.to_markdown()
            + "\n\n---\nUsing the findings above, answer the user's question directly. "
            "Lead with root cause, then give concrete remediation steps with log line references. "
            "Do NOT re-describe the log content."
        )

    loop = _get_loop()
    future = asyncio.run_coroutine_threadsafe(_ask_async(agent, "\n".join(parts)), loop)
    return future.result(timeout=600)
