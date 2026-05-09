"""Quick smoke test — validates analyzers and RAG retrieval without the full UI."""

import io
import sys
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")

from tibco_agent.analyzers.flogo_analyzer import FlogoAnalyzer
from tibco_agent.analyzers.log_analyzer import LogAnalyzer

# ── Sample .flogo with intentional issues ────────────────────────────────────

SAMPLE_FLOGO = """{
  "name": "order-processor",
  "type": "flogo:app",
  "version": "1.0.0",
  "appModel": "1.1.0",
  "triggers": [
    {
      "id": "receive_http_message",
      "ref": "#rest",
      "name": "Receive HTTP Message"
    }
  ],
  "resources": [
    {
      "id": "flow:processOrder",
      "data": {
        "name": "processOrder",
        "tasks": [
          {
            "id": "log_request",
            "name": "LogRequest",
            "activity": {
              "ref": "github.com/project-flogo/contrib/activity/log",
              "input": {
                "message": "Processing order with token=$trigger.content.authToken"
              }
            }
          },
          {
            "id": "call_payment",
            "name": "CallPaymentService",
            "activity": {
              "ref": "github.com/project-flogo/contrib/activity/rest",
              "input": {
                "method": "POST",
                "uri": "http://payment-service/charge"
              },
              "settings": {
                "skipSSLVerification": true
              }
            }
          },
          {
            "id": "query_db",
            "name": "QueryOrderDB",
            "activity": {
              "ref": "github.com/tibco/wi-contrib/activity/jdbc",
              "input": {
                "query": "SELECT * FROM orders WHERE id = ?"
              }
            }
          }
        ],
        "links": []
      }
    }
  ]
}"""

# ── Sample pod log with errors ────────────────────────────────────────────────

SAMPLE_LOG = """2024-01-15T10:23:45Z INFO  Starting flogo application order-processor
2024-01-15T10:23:46Z INFO  Registered trigger: Receive HTTP Message on port 8080
2024-01-15T10:24:01Z ERROR activity.EvalError: NullPointerException at flow:processOrder/activity:CallPaymentService
2024-01-15T10:24:02Z ERROR dial tcp 10.96.4.22:5432: connect: connection refused
2024-01-15T10:25:30Z WARN  Readiness probe failed: HTTP probe failed with statuscode: 503
2024-01-15T10:26:00Z ERROR OOMKilled
"""


def run_tests():
    print("=" * 60)
    print("TEST 1: Flogo Analyzer")
    print("=" * 60)
    analyzer = FlogoAnalyzer()
    report = analyzer.analyze(SAMPLE_FLOGO, source="order-processor.flogo")
    print(report.to_markdown())
    assert report.error_count >= 2, f"Expected >=2 errors, got {report.error_count}"
    print(f"\n[PASS] Found {report.error_count} errors, {report.warning_count} warnings")

    print("\n" + "=" * 60)
    print("TEST 2: Log Analyzer")
    print("=" * 60)
    log_analyzer = LogAnalyzer()
    log_report = log_analyzer.analyze(SAMPLE_LOG, source="order-processor.log")
    print(log_report.to_markdown())
    assert len(log_report.matches) >= 3, f"Expected >=3 matches, got {len(log_report.matches)}"
    print(f"\n[PASS] Found {len(log_report.matches)} error pattern(s)")

    print("\n" + "=" * 60)
    print("TEST 3: RAG Knowledge Search (Weaviate)")
    print("=" * 60)
    try:
        import weaviate
        from tibco_agent.config import settings
        client = weaviate.Client(settings.weaviate_url)
        result = client.query.aggregate(settings.collection_name).with_meta_count().do()
        count = result["data"]["Aggregate"][settings.collection_name][0]["meta"]["count"]
        print(f"Weaviate class '{settings.collection_name}': {count} chunks")
        assert count > 0, "Collection is empty"
        print(f"[PASS] Knowledge base ready with {count} chunks")
    except Exception as e:
        print(f"[FAIL] Weaviate: {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("TEST 4: Rule extensibility — add custom rule")
    print("=" * 60)
    from tibco_agent.analyzers.base import Finding, Rule, Severity
    from tibco_agent.analyzers.flogo_rules import FlogoContext

    class NoReturnInMainFlowRule(Rule):
        id = "CUSTOM-001"
        severity = Severity.WARNING
        category = "custom"

        def check(self, ctx: FlogoContext) -> list[Finding]:
            findings = []
            for flow in ctx.flows:
                has_return = any("return" in t.activity_ref.lower() for t in flow.tasks)
                if not has_return:
                    findings.append(Finding(
                        rule_id=self.id, severity=self.severity,
                        title="No Return Activity",
                        location=f"flow:{flow.name}",
                        message="Flow has no explicit Return activity.",
                        recommendation="Add a Return activity to explicitly set the response body and status code.",
                    ))
            return findings

    custom_analyzer = FlogoAnalyzer()
    custom_analyzer.register_rule(NoReturnInMainFlowRule())
    custom_report = custom_analyzer.analyze(SAMPLE_FLOGO, source="test.flogo")
    custom_findings = [f for f in custom_report.findings if f.rule_id == "CUSTOM-001"]
    assert len(custom_findings) >= 1, "Custom rule did not fire"
    print(f"[PASS] Custom rule 'CUSTOM-001' fired on {len(custom_findings)} flow(s)")
    print("       Custom rule registration works correctly")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
    print("\nRun the UI:  .venv\\Scripts\\streamlit.exe run app.py")


if __name__ == "__main__":
    run_tests()
