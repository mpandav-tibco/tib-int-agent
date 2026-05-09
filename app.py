"""
TIBCO Integration AI Agent — Streamlit UI

Run with:
    streamlit run app.py
"""

import streamlit as st

st.set_page_config(
    page_title="TIBCO Integration AI Agent",
    page_icon="🔗",
    layout="wide",
)

_QUICK_PROMPTS = [
    ("Error Handling", "What are the Flogo best practices for error handling and what should every flow include?"),
    ("JDBC Pooling", "How should I configure JDBC connection pooling in BusinessWorks for high concurrency?"),
    ("Pod Restart", "My BW pod keeps restarting after deployment. What should I check?"),
    ("Performance K8s", "What are performance tuning tips for BWCE running on Kubernetes?"),
    ("Mapper Best Practice", "What are the best practices for mapping in Flogo to avoid null errors?"),
    ("EMS Config", "How should I configure TIBCO EMS connections for resilience in BW?"),
    ("Analyze Flogo", "Analyze the uploaded .flogo file for issues and recommendations"),
    ("Diagnose Log", "Diagnose the errors in the uploaded pod log and tell me how to fix them"),
]


@st.cache_resource(show_spinner="Loading agent and knowledge base...")
def _load_agent():
    from tibco_agent.agent.core import build_agent
    return build_agent()


def main() -> None:
    st.title("TIBCO Integration AI Agent")
    st.caption(
        "Powered by Ollama (local LLM) + ChromaDB vector search. "
        "Specializes in TIBCO BusinessWorks and Flogo Enterprise."
    )

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
        log_content = log_file.read().decode("utf-8") if log_file else ""

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
        with st.expander("Settings"):
            from tibco_agent.config import settings
            st.text(f"LLM: {settings.llm_model}")
            st.text(f"Embed: {settings.embed_model}")
            st.text(f"Ollama: {settings.ollama_base_url}")

        if st.button("Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

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
                        "Models: `ollama pull llama3.1:8b && ollama pull nomic-embed-text`"
                    )
            st.markdown(response)

        st.session_state.messages.append({"role": "assistant", "content": response})


if __name__ == "__main__":
    main()
