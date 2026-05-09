"""End-to-end agent test — requires Ollama running with llama3.1:8b and nomic-embed-text."""

import io
import sys
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("Loading agent (first load is slower — sets up LLM + RAG)...")
from tibco_agent.agent.core import build_agent, ask

agent = build_agent()
print("Agent ready.\n")

TESTS = [
    {
        "label": "Knowledge Q&A — best practice",
        "question": "What are the most important best practices for error handling in TIBCO Flogo flows?",
        "flogo": "",
        "log": "",
    },
    {
        "label": "File Analysis — .flogo with issues",
        "question": "Review this Flogo file and tell me all the issues you find.",
        "flogo": """{
  "name": "test-app",
  "type": "flogo:app",
  "version": "1.0.0",
  "triggers": [{"id": "http", "ref": "#rest"}],
  "resources": [{
    "id": "flow:main",
    "data": {
      "name": "main",
      "tasks": [{
        "id": "call_api",
        "name": "CallExternalAPI",
        "activity": {
          "ref": "github.com/project-flogo/contrib/activity/rest",
          "input": {"method": "GET", "uri": "https://api.example.com/data"},
          "settings": {"skipSSLVerification": true}
        }
      }]
    }
  }]
}""",
        "log": "",
    },
]

for i, t in enumerate(TESTS, 1):
    print(f"\n{'='*60}")
    print(f"TEST {i}: {t['label']}")
    print("=" * 60)
    print(f"Q: {t['question'][:80]}...")
    print("\nA:")
    response = ask(agent, t["question"], t["flogo"], t["log"])
    print(response[:1500])
    print("..." if len(response) > 1500 else "")

print("\n\nAll agent tests complete.")
print("Launch UI:  .venv\\Scripts\\streamlit.exe run app.py")
