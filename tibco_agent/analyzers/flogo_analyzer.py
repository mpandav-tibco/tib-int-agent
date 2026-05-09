from __future__ import annotations

import json

from .base import Analyzer, AnalysisReport, Finding, Rule, Severity
from .flogo_rules import (
    FlogoContext, FlogoFlow, FlogoTask,
    HttpSslRule, HttpTimeoutRule, MissingErrorHandlerRule,
    SelectStarRule, SensitiveLogRule, SubflowDepthRule,
    HttpRetryRule, HardcodedCredentialRule, LargeFlowRule, MissingCorrelationIdRule,
    LargeLogPayloadRule, HardcodedUrlRule,
    AppDescriptionRule, FlowNamingConventionRule, DedicatedConnectorRule,
    SeparationOfConcernsRule, ApiVersioningRule, TimeoutConfiguredRule,
    detect_technologies, detect_pattern, extract_endpoints,
)


def _parse_task(raw: dict) -> FlogoTask:
    act = raw.get("activity", {})
    return FlogoTask(
        id=raw.get("id", ""),
        name=raw.get("name", raw.get("id", "unnamed")),
        activity_ref=act.get("ref", ""),
        input=act.get("input", {}),
        settings=act.get("settings", {}),
    )


def _parse_flow(resource: dict) -> FlogoFlow:
    data = resource.get("data", {})
    error_handler = data.get("errorHandler", {})
    return FlogoFlow(
        name=data.get("name", resource.get("id", "unnamed")),
        tasks=[_parse_task(t) for t in data.get("tasks", [])],
        has_error_handler=bool(error_handler),
        error_handler_tasks=[_parse_task(t) for t in error_handler.get("tasks", [])],
    )


def _build_overview(app: dict, flows: list[FlogoFlow]) -> dict:
    triggers = app.get("triggers", [])
    imports  = app.get("imports", [])

    # Trigger port (REST)
    trigger_port = None
    for t in triggers:
        port = t.get("settings", {}).get("port")
        if port:
            trigger_port = port
            break

    return {
        "name":         app.get("name", ""),
        "description":  app.get("description", ""),
        "version":      app.get("version", ""),
        "app_model":    app.get("appModel", ""),
        "pattern":      detect_pattern(triggers, flows),
        "trigger_port": trigger_port,
        "flow_count":   len(flows),
        "endpoints":    extract_endpoints(triggers),
        "technologies": detect_technologies(imports),
    }


class FlogoAnalyzer(Analyzer):
    """
    Analyzes TIBCO Flogo .flogo application files against a pluggable rule set.
    Produces a full architect review: overview, tech stack, strengths, and issues.

    Add custom rules:
        analyzer = FlogoAnalyzer()
        analyzer.register_rule(MyCustomRule())
    Disable a built-in rule:
        analyzer.unregister_rule("FLOGO-003")
    """

    def _default_rules(self) -> list[Rule]:
        return [
            # Error-level
            MissingErrorHandlerRule(),
            HttpTimeoutRule(),
            HardcodedCredentialRule(),
            # Warning-level
            HttpSslRule(),
            SelectStarRule(),
            SensitiveLogRule(),
            HttpRetryRule(),
            LargeFlowRule(),
            LargeLogPayloadRule(),
            HardcodedUrlRule(),
            # Info-level
            SubflowDepthRule(),
            MissingCorrelationIdRule(),
        ]

    def _positive_rules(self) -> list[Rule]:
        return [
            AppDescriptionRule(),
            FlowNamingConventionRule(),
            DedicatedConnectorRule(),
            SeparationOfConcernsRule(),
            ApiVersioningRule(),
            TimeoutConfiguredRule(),
        ]

    def analyze(self, content: str, source: str = "unknown.flogo") -> AnalysisReport:
        try:
            app = json.loads(content)
        except json.JSONDecodeError as e:
            report = AnalysisReport(source=source, product="flogo")
            report.findings.append(Finding(
                rule_id="FLOGO-000",
                severity=Severity.ERROR,
                title="Invalid JSON",
                location="file root",
                message=f"Could not parse as JSON: {e}",
                recommendation="Validate the JSON. Run `flogo build` locally to check for schema errors.",
            ))
            return report

        flows = [_parse_flow(r) for r in app.get("resources", [])]
        ctx = FlogoContext(
            app_name=app.get("name", source),
            flows=flows,
            triggers=app.get("triggers", []),
            raw=app,
        )

        report = AnalysisReport(
            source=source,
            product="flogo",
            overview=_build_overview(app, flows),
        )

        # Issue findings
        for rule in self._rules:
            report.findings.extend(rule.check(ctx))

        # Positive / strength findings
        for rule in self._positive_rules():
            report.positives.extend(rule.check(ctx))

        # Security note on trigger authentication
        for trigger in ctx.triggers:
            auth = trigger.get("settings", {}).get("authenticationType", "None")
            secure = trigger.get("settings", {}).get("secureConnection", False)
            if auth == "None":
                report.observations.append(
                    f"Trigger `{trigger.get('name', trigger.get('id', ''))}` has no authentication "
                    "(authenticationType=None). Consider adding Basic/OAuth2 auth before exposing to external clients."
                )
            if not secure:
                report.observations.append(
                    f"Trigger `{trigger.get('name', trigger.get('id', ''))}` runs over plain HTTP "
                    "(secureConnection=false). Enable TLS for production deployments."
                )

        return report
