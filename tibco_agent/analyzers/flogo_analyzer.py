from __future__ import annotations

import json

from .base import Analyzer, AnalysisReport, Finding, Rule, Severity
from .flogo_rules import (
    FlogoContext, FlogoFlow, FlogoTask,
    HttpSslRule, HttpTimeoutRule, MissingErrorHandlerRule,
    SelectStarRule, SensitiveLogRule, SubflowDepthRule,
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


class FlogoAnalyzer(Analyzer):
    """
    Analyzes TIBCO Flogo .flogo application files against a pluggable rule set.

    Add custom rules:
        analyzer = FlogoAnalyzer()
        analyzer.register_rule(MyCustomRule())
    Disable a built-in rule:
        analyzer.unregister_rule("FLOGO-003")
    """

    def _default_rules(self) -> list[Rule]:
        return [
            MissingErrorHandlerRule(),
            HttpTimeoutRule(),
            HttpSslRule(),
            SelectStarRule(),
            SensitiveLogRule(),
            SubflowDepthRule(),
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

        report = AnalysisReport(source=source, product="flogo")
        report.observations.append(
            f"App: **{ctx.app_name}** — {len(ctx.triggers)} trigger(s), {len(ctx.flows)} flow(s)"
        )

        for rule in self._rules:
            report.findings.extend(rule.check(ctx))

        return report
