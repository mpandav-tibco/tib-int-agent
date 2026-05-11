from __future__ import annotations

import logging
import re
import time
from typing import Callable

from llama_index.core import Settings
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama

from tibco_agent.config import settings as _default_settings
from tibco_agent.config import Settings as AppSettings
from tibco_agent.tools.agent_tools import search_knowledge

log = logging.getLogger(__name__)

# Keep backward-compatible alias used by other modules (e.g. pipeline.py)
settings = _default_settings

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
- IMPORTANT — brand names: TIBCO is a business unit of Cloud Software Group (CSG). Products must
  always be named with their TIBCO brand: "TIBCO BusinessWorks" (NOT "webMethods BW"),
  "TIBCO Flogo Enterprise" (NOT "webMethods Flogo"), "TIBCO EMS" (NOT "webMethods Messaging").
  Never substitute "webMethods" for "TIBCO" in any product name. TIBCO and webMethods are
  separate business units within CSG — they are not the same thing.
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


def _make_llm(cfg: AppSettings | None = None):
    cfg = cfg or _default_settings
    provider = cfg.llm_provider

    if provider == "anthropic":
        from llama_index.llms.anthropic import Anthropic
        return Anthropic(
            model=cfg.llm_model,
            api_key=cfg.llm_api_key,
            max_tokens=4096,
        )

    if provider == "openai":
        from llama_index.llms.openai import OpenAI
        return OpenAI(
            model=cfg.llm_model,
            api_key=cfg.llm_api_key,
            max_tokens=4096,
        )

    if provider in ("groq", "ollama-cloud", "custom"):
        from llama_index.llms.openai_like import OpenAILike
        base = cfg.llm_api_base or _PROVIDER_BASE_URLS.get(provider, "")
        return OpenAILike(
            model=cfg.llm_model,
            api_key=cfg.llm_api_key or "na",
            api_base=base,
            is_chat_model=True,
            max_tokens=4096,
            request_timeout=cfg.request_timeout,
        )

    # Default: local Ollama
    return Ollama(
        model=cfg.llm_model,
        base_url=cfg.ollama_base_url,
        request_timeout=cfg.request_timeout,
        context_window=_NUM_CTX,
        additional_kwargs={"options": {"num_ctx": _NUM_CTX}},
    )


def _make_embed_model(cfg: AppSettings):
    """Return the appropriate embedding model for the configured provider."""
    if cfg.llm_provider == "openai":
        from llama_index.embeddings.openai import OpenAIEmbedding
        log.info("Using OpenAIEmbedding (text-embedding-3-small) for provider=openai")
        return OpenAIEmbedding(
            model="text-embedding-3-small",
            api_key=cfg.llm_api_key,
        )
    if cfg.llm_provider not in ("ollama",):
        log.warning(
            "Provider '%s' has no native embedding model — falling back to Ollama at %s. "
            "Ensure Ollama is running with: ollama pull %s",
            cfg.llm_provider, cfg.ollama_base_url, cfg.embed_model,
        )
    return OllamaEmbedding(
        model_name=cfg.embed_model,
        base_url=cfg.ollama_base_url,
    )


def configure_llm(cfg: AppSettings | None = None) -> None:
    cfg = cfg or _default_settings
    log.info("configure_llm: provider=%s model=%s", cfg.llm_provider, cfg.llm_model)
    Settings.llm = _make_llm(cfg)
    Settings.embed_model = _make_embed_model(cfg)


_HISTORY_CHAR_LIMIT = 6000  # ~1500 tokens — covers ~3 full diagnostic turns


def _trim_history(history: list[dict]) -> list[dict]:
    """Return the most-recent turns that fit within the char budget."""
    trimmed: list[dict] = []
    used = 0
    for msg in reversed(history):
        chunk = len(msg.get("content", ""))
        if used + chunk > _HISTORY_CHAR_LIMIT and trimmed:
            break
        trimmed.insert(0, msg)
        used += chunk
    return trimmed


def build_prompt(
    question: str,
    flogo_content: str = "",
    log_content: str = "",
    bw_content: str = "",
    on_step: Callable[[str, int], None] | None = None,
    chat_history: list[dict] | None = None,
    collection_name: str = "",
    agent_name: str = "",
    vector_db: str = "",
    vector_db_url: str = "",
    vector_db_api_key: str = "",
) -> str:
    """Assemble the full LLM prompt.  on_step(message, pct) is called at each stage.

    collection_name: vector store collection to search (empty → global default).
    vector_db/url/api_key: per-agent store overrides (empty → global settings).
    agent_name: used to personalise the assistant label in injected history.
    """
    _step = on_step or (lambda _msg, _pct: None)
    t0 = time.perf_counter()
    log.debug("build_prompt: question=%r flogo=%d bw=%d log=%d history=%d col=%r",
              question[:60], len(flogo_content), len(bw_content), len(log_content),
              len(chat_history or []), collection_name)
    parts = [question]

    # Inject the most-recent turns (char-budget trimmed) for follow-up context
    if chat_history:
        recent = _trim_history(chat_history)
        assistant_label = agent_name or "TARA"
        history_lines = [
            "\n\n## Conversation History",
            "_Prior turns — use for follow-up context only, do not re-answer unless asked._",
        ]
        for msg in recent:
            role = "User" if msg["role"] == "user" else assistant_label
            text = msg["content"][:400].replace("\n", " ").strip()
            history_lines.append(f"**{role}:** {text}")
        parts.append("\n".join(history_lines))

    _step("Searching knowledge base…", 15)
    kb = search_knowledge(question, collection_name, vector_db, vector_db_url, vector_db_api_key)
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
        bw_analyzer = BWAnalyzer()
        bw_report = bw_analyzer.analyze(bw_content)
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
        parts.append("\n\n" + bw_analyzer.report_to_markdown(bw_report) + bw_suffix)

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
    result = "\n".join(parts)
    log.info("build_prompt: chars=%d elapsed=%.1fs", len(result), time.perf_counter() - t0)
    return result


def call_llm(prompt: str, system_prompt: str = "") -> str:
    """Send a pre-built prompt to the configured LLM and return the cleaned response.

    system_prompt: agent-specific persona injected before the user prompt.
    Falls back to _SYSTEM_PROMPT when empty (preserves TARA's default behaviour).
    """
    sp = system_prompt.strip() or _SYSTEM_PROMPT
    full_prompt = f"{sp}\n\n{prompt}"
    log.debug("call_llm: prompt_len=%d system_prompt_len=%d", len(prompt), len(sp))
    t0 = time.perf_counter()
    result = _clean_response(str(Settings.llm.complete(full_prompt)))
    log.info("call_llm: response_len=%d elapsed=%.1fs", len(result), time.perf_counter() - t0)
    return result


def ask(
    question: str,
    flogo_content: str = "",
    log_content: str = "",
    bw_content: str = "",
    chat_history: list[dict] | None = None,
    system_prompt: str = "",
    collection_name: str = "",
    agent_name: str = "",
    vector_db: str = "",
    vector_db_url: str = "",
    vector_db_api_key: str = "",
) -> str:
    prompt = build_prompt(
        question, flogo_content, log_content, bw_content,
        chat_history=chat_history,
        collection_name=collection_name,
        agent_name=agent_name,
        vector_db=vector_db,
        vector_db_url=vector_db_url,
        vector_db_api_key=vector_db_api_key,
    )
    return call_llm(prompt, system_prompt=system_prompt)
