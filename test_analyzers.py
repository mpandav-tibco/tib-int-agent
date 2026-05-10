"""Quick smoke test — validates analyzers and RAG retrieval without the full UI."""

import io
import sys
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")

from tibco_agent.analyzers.flogo_analyzer import FlogoAnalyzer
from tibco_agent.analyzers.log_analyzer import LogAnalyzer
from tibco_agent.analyzers.bw_analyzer import BWAnalyzer
from tibco_agent.analyzers.multi_analyzer import analyze_zip

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


SAMPLE_BWP = """<?xml version="1.0" encoding="UTF-8"?>
<process:ProcessDefinition xmlns:process="http://ns.tibco.com/bw/process"
    name="ProcessPayment" id="ProcessPayment">
  <activity name="InvokePaymentAPI" id="http1">
    <type>com.tibco.plugin.http.HTTPActivityUI</type>
    <config>
      <Url>http://payment.internal/api/charge</Url>
      <password>s3cr3t_literal</password>
    </config>
  </activity>
  <activity name="QueryOrders" id="jdbc1">
    <type>com.tibco.jdbc.JDBCQueryActivity</type>
    <config>
      <statement>SELECT * FROM orders WHERE customer_id = ?</statement>
    </config>
  </activity>
</process:ProcessDefinition>
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
    print("TEST 3: BW Analyzer")
    print("=" * 60)
    bw_analyzer = BWAnalyzer()
    bw_report = bw_analyzer.analyze(SAMPLE_BWP, source="ProcessPayment.bwp")
    print(bw_analyzer._report_to_markdown(bw_report))
    assert bw_report.error_count >= 1, f"Expected >=1 BW errors, got {bw_report.error_count}"
    print(f"\n[PASS] BW Analyzer found {bw_report.error_count} error(s), {bw_report.warning_count} warning(s)")

    print("\n" + "=" * 60)
    print("TEST 4: Multi-file ZIP Analysis")
    print("=" * 60)
    import io, zipfile
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("order-processor.flogo", SAMPLE_FLOGO)
        zf.writestr("ProcessPayment.bwp", SAMPLE_BWP)
    zip_bytes = zip_buffer.getvalue()
    project = analyze_zip(zip_bytes, zip_name="test-project.zip")
    print(project.to_markdown())
    assert len(project.flogo_reports) == 1, "Expected 1 Flogo report"
    assert len(project.bw_reports) == 1, "Expected 1 BW report"
    assert project.total_errors >= 1, "Expected >=1 errors in project"
    print(f"[PASS] ZIP analysis: {len(project.flogo_reports)} Flogo, {len(project.bw_reports)} BW, "
          f"{project.total_errors} error(s), {project.total_warnings} warning(s)")

    print("\n" + "=" * 60)
    print("TEST 5: New Flogo rules (FLOGO-011, FLOGO-012)")
    print("=" * 60)
    SAMPLE_FLOGO_NEW_RULES = """{
  "name": "test-new-rules",
  "type": "flogo:app",
  "version": "1.0.0",
  "appModel": "1.1.0",
  "triggers": [{"id": "t1", "ref": "#rest"}],
  "resources": [{
    "id": "flow:main",
    "data": {
      "name": "main",
      "tasks": [
        {"id": "log1", "name": "LogAll", "activity": {
          "ref": "github.com/project-flogo/contrib/activity/log",
          "input": {"message": "$flow"}}},
        {"id": "rest1", "name": "CallPayment", "activity": {
          "ref": "github.com/project-flogo/contrib/activity/rest",
          "input": {"method": "POST", "uri": "http://payment-svc/charge", "timeout": 30000}}}
      ]
    }
  }]
}"""
    new_rule_report = FlogoAnalyzer().analyze(SAMPLE_FLOGO_NEW_RULES, source="test.flogo")
    rule_ids = {f.rule_id for f in new_rule_report.findings}
    assert "FLOGO-011" in rule_ids, f"FLOGO-011 did not fire; got {rule_ids}"
    assert "FLOGO-012" in rule_ids, f"FLOGO-012 did not fire; got {rule_ids}"
    print(f"[PASS] FLOGO-011 and FLOGO-012 fired correctly (rules: {rule_ids})")

    print("\n" + "=" * 60)
    print("TEST 6: RAG Knowledge Search (Weaviate)")
    print("=" * 60)
    try:
        import weaviate
        from tibco_agent.config import settings
        url = settings.weaviate_url
        bare = url.removeprefix("https://").removeprefix("http://")
        host, _, port_str = bare.partition(":")
        port = int(port_str) if port_str.isdigit() else 8080
        with weaviate.connect_to_custom(
            http_host=host or "localhost",
            http_port=port,
            http_secure=url.startswith("https://"),
            grpc_host=host or "localhost",
            grpc_port=50051,
            grpc_secure=False,
        ) as client:
            collection = client.collections.get(settings.collection_name)
            agg = collection.aggregate.over_all(total_count=True)
            count = agg.total_count or 0
        print(f"Weaviate collection '{settings.collection_name}': {count} chunks")
        assert count > 0, "Collection is empty"
        print(f"[PASS] Knowledge base ready with {count} chunks")
    except Exception as e:
        print(f"[FAIL] Weaviate: {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("TEST 7: Rule extensibility — add custom rule")
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
    print("\nRun the UI:  chainlit run chainlit_app.py")


if __name__ == "__main__":
    run_tests()
