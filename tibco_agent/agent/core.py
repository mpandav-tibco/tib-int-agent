from __future__ import annotations

import asyncio
import re
import threading
from typing import Callable

from llama_index.core import Settings
from llama_index.core.agent import ReActAgent
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama

from tibco_agent.config import settings
from tibco_agent.tools.registry import ToolRegistry
from tibco_agent.tools.agent_tools import build_knowledge_tool, build_flogo_tool, build_bw_tool, build_log_tool, search_knowledge

_SYSTEM_PROMPT = """\
You are TARA (TIBCO AI Review Agent), an expert assistant specializing in:
- TIBCO BusinessWorks 5, 6, and BWCE (container edition)
- TIBCO Flogo Enterprise
- TIBCO Enterprise Message Service (EMS) and TIBCO Messaging (FTL, eFTL, Pulsar)
- TIBCO integration patterns, middleware architecture, and cloud-native deployment

Your responsibilities:
1. Answer questions about TIBCO integration and messaging best practices, patterns, and implementation
2. Review .flogo application files and report issues with actionable recommendations
3. Diagnose errors from BW/Flogo/EMS logs from any environment (Kubernetes, on-prem, cloud)
4. Provide performance tuning, troubleshooting, and architectural guidance for TIBCO platforms

Rules:
- Match response length to the question. A specific question ("which pattern?", "how many flows?")
  gets a direct 1–3 sentence answer. A review request ("review this", "is this production-ready?")
  gets a full structured analysis. Never give a full review when a one-liner will do.
- Always format responses in markdown. Never write prose paragraphs when a bullet list is clearer.
  Use `##` / `###` headers when the answer has distinct sections. Use `-` bullet lists for any
  enumeration of features, steps, issues, or options. Use `**bold**` for key terms and
  `` `code` `` for property names, values, commands, config keys, and version numbers.
  A "what are the features" question should always produce a bullet list, not paragraphs.
- You have deep training knowledge about TIBCO products — use it freely for general questions
  about features, patterns, architecture, best practices, and release notes.
- For version-specific questions (e.g. "what's new in Flogo 2.26.3?"), answer directly from
  training knowledge if you know it. Do NOT let KB excerpts about known issues or installation
  override a features question — if the excerpts don't directly answer what was asked, ignore
  them and answer from training. Never hedge with "the documentation doesn't detail this" if
  your training knowledge covers it.
- Only avoid guessing when asked for a specific config value, property name, or error code you
  are not certain about — in those cases say you are not sure rather than inventing a value.
- When the prompt contains a "## App Review" section, treat those findings as authoritative facts.
  Only surface the parts relevant to the question asked.
- Cite the specific flow name, activity name, or log line number when relevant.
- Prioritize errors over warnings. Be concise and actionable.
- If you are not confident, say so. Do not invent configuration values or API names.
- When knowledge base excerpts were provided and informed your answer, end your response with
  a "## Sources" section listing the excerpt labels you drew on, one per line:
  `- [Excerpt N — product | filename]`. Omit this section when you answered from training
  knowledge only and the excerpts were irrelevant or absent.
"""

# ── Intent classification ─────────────────────────────────────────────────────
# Determines how much of the analysis report to surface in the response.
# Runs locally — no extra LLM call.

_REVIEW_SIGNALS = frozenset({
    "review", "analyse", "analyze", "audit", "assess", "evaluate",
    "handled right", "handled correctly", "handled in right",
    "is this right", "is this correct", "is this good", "is this ok",
    "what are the issues", "what's wrong", "whats wrong",
    "all issues", "all problems", "all findings", "any issues", "any problems",
    "tell me all", "comprehensive", "full review",
    "production ready", "production-ready", "ready for production",
    "check this app", "check the app",
})


def _classify_intent(question: str) -> str:
    """Return 'review' for full analysis requests, 'specific' for targeted questions."""
    q = question.lower()
    if any(signal in q for signal in _REVIEW_SIGNALS):
        return "review"
    return "specific"

# deepseek-r1 generates long reasoning chains before the answer; 8192 avoids truncation.
_NUM_CTX = 8192

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

# Preset base URLs for cloud providers
_PROVIDER_BASE_URLS: dict[str, str] = {
    "groq":         "https://api.groq.com/openai/v1",
    "openai":       "https://api.openai.com/v1",
    "ollama-cloud": "https://ollama.com/v1",
}

# Suggested models shown as hints in the UI (imported by app.py)
PROVIDER_MODEL_HINTS: dict[str, str] = {
    "ollama":       "deepseek-r1:latest · llama3.1:8b · mistral:7b",
    "openai":       "gpt-4o · gpt-4o-mini · gpt-3.5-turbo",
    "anthropic":    "claude-opus-4-7 · claude-sonnet-4-6 · claude-haiku-4-5-20251001",
    "groq":         "llama-3.3-70b-versatile · deepseek-r1-distill-llama-70b · llama-3.1-8b-instant",
    "ollama-cloud": "llama3.3:70b-instruct-cloud · deepseek-v3.1:671b-cloud · llama3.1:8b-instruct-cloud",
    "custom":       "model name depends on your provider",
}


def _clean_response(text: str) -> str:
    """Strip <think>...</think> blocks emitted by deepseek-r1 reasoning models."""
    return _THINK_RE.sub("", text).strip()


def _make_llm():
    provider = settings.llm_provider

    if provider == "anthropic":
        from llama_index.llms.anthropic import Anthropic
        return Anthropic(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            max_tokens=4096,
        )

    if provider == "openai":
        from llama_index.llms.openai import OpenAI
        return OpenAI(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            max_tokens=4096,
        )

    if provider in ("groq", "ollama-cloud", "custom"):
        from llama_index.llms.openai_like import OpenAILike
        base = settings.llm_api_base or _PROVIDER_BASE_URLS.get(provider, "")
        return OpenAILike(
            model=settings.llm_model,
            api_key=settings.llm_api_key or "na",
            api_base=base,
            is_chat_model=True,
            max_tokens=4096,
            request_timeout=settings.request_timeout,
        )

    # Default: local Ollama
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
            registry.register(build_bw_tool())
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


def build_prompt(
    question: str,
    flogo_content: str = "",
    log_content: str = "",
    bw_content: str = "",
    on_step: Callable[[str, int], None] | None = None,
    chat_history: list[dict] | None = None,
) -> str:
    """Assemble the full LLM prompt.  on_step(message, pct) is called at each stage."""
    _step = on_step or (lambda _msg, _pct: None)
    parts = [question]

    # Inject the last few conversation turns so the LLM can handle follow-ups
    if chat_history:
        recent = chat_history[-6:]  # Last 3 user+assistant turn pairs
        history_lines = [
            "\n\n## Conversation History",
            "_Prior turns — use for follow-up context only, do not re-answer unless asked._",
        ]
        for msg in recent:
            role = "User" if msg["role"] == "user" else "TARA"
            text = msg["content"][:400].replace("\n", " ").strip()
            history_lines.append(f"**{role}:** {text}")
        parts.append("\n".join(history_lines))

    _step("Searching knowledge base…", 15)
    kb = search_knowledge(question)
    if kb:
        parts.append(
            "\n\n## Knowledge Base Excerpts\n"
            "_Retrieved from ingested TIBCO documentation._\n"
            "- If these excerpts directly answer the question, prefer them and cite them.\n"
            "- If they are only partially relevant, use them as supporting context and fill "
            "the gaps with your training knowledge.\n"
            "- If they are irrelevant to the question, ignore them entirely and answer "
            "confidently from your training knowledge. Never refuse to answer just because "
            "the excerpts are silent — you have broad TIBCO expertise, use it.\n\n" + kb
        )

    intent = _classify_intent(question)

    if bw_content.strip():
        _step("Analyzing BW process…", 38)
        from tibco_agent.analyzers.bw_analyzer import BWAnalyzer
        bw_report = BWAnalyzer().analyze(bw_content)
        bw_analyzer_obj = BWAnalyzer()
        if intent == "review":
            bw_suffix = (
                "\n\n---\n"
                "You are a senior TIBCO BW architect reviewing this process. "
                "Write a comprehensive review: verdict, strengths, critical issues with production impact, "
                "and improvement recommendations. Cite process names and activity names."
            )
        else:
            bw_suffix = (
                "\n\n---\n"
                "The BW analysis above is context. Answer the user's question directly and concisely. "
                "Only surface the parts of the analysis relevant to the question."
            )
        parts.append("\n\n" + bw_analyzer_obj._report_to_markdown(bw_report) + bw_suffix)

    if flogo_content.strip():
        _step("Analyzing application…", 40)
        from tibco_agent.analyzers.flogo_analyzer import FlogoAnalyzer
        report = FlogoAnalyzer().analyze(flogo_content)
        if intent == "review":
            suffix = (
                "\n\n---\n"
                "You are a senior TIBCO Integration architect reviewing this application. "
                "Using the structured analysis above, write a comprehensive review covering:\n"
                "1. **Overall verdict** — one paragraph on whether the implementation is production-ready.\n"
                "2. **What is well implemented** — acknowledge the strengths from the analysis.\n"
                "3. **Critical issues** — explain each error: why it matters in production, not just what it is.\n"
                "4. **Improvements & recommendations** — beyond the detected issues: patterns, scalability, observability, security.\n"
                "Be specific. Cite flow names, activity names, and endpoint paths. "
                "Write as a peer talking to a developer, not as a checklist generator."
            )
        else:
            suffix = (
                "\n\n---\n"
                "The analysis report above is context. Answer the user's specific question directly and concisely — "
                "one short paragraph or a brief list, whichever fits. "
                "Do NOT produce a full review. Only surface the parts of the analysis relevant to the question."
            )
        parts.append("\n\n" + report.to_markdown() + suffix)

    if log_content.strip():
        _step("Analyzing logs…", 55)
        from tibco_agent.analyzers.log_analyzer import LogAnalyzer
        report = LogAnalyzer().analyze(log_content)
        if intent == "review":
            log_suffix = (
                "\n\n---\nDiagnose these pod log findings as a senior site-reliability engineer. "
                "For each issue: explain the root cause, the production impact, and the exact remediation steps. "
                "Cite log line numbers. Prioritise errors over warnings."
            )
        else:
            log_suffix = (
                "\n\n---\n"
                "The log analysis above is context. Answer the user's specific question directly and concisely. "
                "Do NOT list every finding — only surface the parts relevant to the question."
            )
        parts.append("\n\n" + report.to_markdown() + log_suffix)

    _step("Sending to LLM…", 65)
    return "\n".join(parts)


def call_llm(agent: ReActAgent, prompt: str) -> str:
    """Run a pre-built prompt through the agent LLM."""
    loop = _get_loop()
    future = asyncio.run_coroutine_threadsafe(_ask_async(agent, prompt), loop)
    return _clean_response(future.result(timeout=600))


def ask(
    agent: ReActAgent,
    question: str,
    flogo_content: str = "",
    log_content: str = "",
    bw_content: str = "",
    chat_history: list[dict] | None = None,
) -> str:
    prompt = build_prompt(question, flogo_content, log_content, bw_content, chat_history=chat_history)
    return call_llm(agent, prompt)
