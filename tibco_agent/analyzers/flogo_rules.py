from __future__ import annotations

from dataclasses import dataclass, field

from .base import Finding, Rule, Severity

# ── Data model ──────────────────────────────────────────────────────────────

@dataclass
class FlogoTask:
    id: str
    name: str
    activity_ref: str
    input: dict
    settings: dict


@dataclass
class FlogoFlow:
    name: str
    tasks: list[FlogoTask]
    has_error_handler: bool
    error_handler_tasks: list[FlogoTask]


@dataclass
class FlogoContext:
    app_name: str
    flows: list[FlogoFlow]
    triggers: list[dict]
    raw: dict


# ── Reference sets ───────────────────────────────────────────────────────────

_HTTP_REFS = frozenset({
    "github.com/project-flogo/contrib/activity/rest",
    "github.com/tibco/wi-contrib/activity/rest",
    "#rest",
})
_JDBC_REFS = frozenset({
    "github.com/tibco/wi-contrib/activity/jdbc",
    "#jdbc",
})
_LOG_REFS = frozenset({
    "#log",
    "github.com/project-flogo/contrib/activity/log",
})


def _matches(ref: str, known: frozenset[str]) -> bool:
    return any(ref == k or ref.startswith(k) for k in known)


# ── Rules ────────────────────────────────────────────────────────────────────

class MissingErrorHandlerRule(Rule):
    id = "FLOGO-001"
    severity = Severity.ERROR
    category = "error-handling"
    tags = ["error-handler", "resilience"]

    def check(self, ctx: FlogoContext) -> list[Finding]:
        return [
            Finding(
                rule_id=self.id,
                severity=self.severity,
                title="Missing Error Handler",
                location=f"flow:{flow.name}",
                message="No error handler branch defined. Uncaught exceptions return HTTP 500 with no diagnostic info.",
                recommendation=(
                    "Add an errorHandler branch. In it, add a Return activity that maps "
                    "$error.message and $error.data to the response body with status 500."
                ),
                tags=self.tags,
            )
            for flow in ctx.flows
            if not flow.has_error_handler or not flow.error_handler_tasks
        ]


class HttpTimeoutRule(Rule):
    id = "FLOGO-002"
    severity = Severity.ERROR
    category = "reliability"
    tags = ["http", "timeout", "performance"]

    def check(self, ctx: FlogoContext) -> list[Finding]:
        findings = []
        for flow in ctx.flows:
            for task in flow.tasks:
                if not _matches(task.activity_ref, _HTTP_REFS):
                    continue
                timeout = task.input.get("timeout") or task.settings.get("timeout")
                if not timeout or (isinstance(timeout, (int, float)) and timeout == 0):
                    findings.append(Finding(
                        rule_id=self.id,
                        severity=self.severity,
                        title="HTTP Activity Without Timeout",
                        location=f"flow:{flow.name} / activity:{task.name}",
                        message="No timeout configured. Threads will hang indefinitely under load.",
                        recommendation=(
                            "Set 'timeout' in the activity input: 30000ms (30s) for internal services, "
                            "60000ms (60s) for external APIs."
                        ),
                        tags=self.tags,
                    ))
        return findings


class HttpSslRule(Rule):
    id = "FLOGO-003"
    severity = Severity.WARNING
    category = "security"
    tags = ["http", "ssl", "security"]

    def check(self, ctx: FlogoContext) -> list[Finding]:
        findings = []
        for flow in ctx.flows:
            for task in flow.tasks:
                if not _matches(task.activity_ref, _HTTP_REFS):
                    continue
                skip = task.settings.get("skipSSLVerification") or task.input.get("skipSSLVerification")
                if skip is True or str(skip).lower() == "true":
                    findings.append(Finding(
                        rule_id=self.id,
                        severity=self.severity,
                        title="SSL Verification Disabled",
                        location=f"flow:{flow.name} / activity:{task.name}",
                        message="skipSSLVerification=true disables certificate validation — a security risk in production.",
                        recommendation="Set skipSSLVerification to false and import the CA certificate into the trust store.",
                        tags=self.tags,
                    ))
        return findings


class SelectStarRule(Rule):
    id = "FLOGO-004"
    severity = Severity.WARNING
    category = "performance"
    tags = ["jdbc", "sql", "performance"]

    def check(self, ctx: FlogoContext) -> list[Finding]:
        findings = []
        for flow in ctx.flows:
            for task in flow.tasks:
                if not _matches(task.activity_ref, _JDBC_REFS):
                    continue
                query = str(task.input.get("query", ""))
                if "SELECT *" in query.upper():
                    findings.append(Finding(
                        rule_id=self.id,
                        severity=self.severity,
                        title="SELECT * in JDBC Query",
                        location=f"flow:{flow.name} / activity:{task.name}",
                        message="SELECT * fetches all columns including unused ones, wasting network and memory.",
                        recommendation="Enumerate only required columns: SELECT id, name, status FROM ...",
                        tags=self.tags,
                    ))
        return findings


class SensitiveLogRule(Rule):
    id = "FLOGO-005"
    severity = Severity.WARNING
    category = "security"
    tags = ["log", "security", "pii"]

    _SENSITIVE = frozenset({"password", "token", "secret", "key", "credential", "passwd", "apikey", "api_key"})

    def check(self, ctx: FlogoContext) -> list[Finding]:
        findings = []
        for flow in ctx.flows:
            for task in flow.tasks:
                if not _matches(task.activity_ref, _LOG_REFS):
                    continue
                msg = str(task.input.get("message", "")).lower()
                if any(kw in msg for kw in self._SENSITIVE):
                    findings.append(Finding(
                        rule_id=self.id,
                        severity=self.severity,
                        title="Possible Sensitive Data in Log",
                        location=f"flow:{flow.name} / activity:{task.name}",
                        message="Log message references a field with a security-sensitive name.",
                        recommendation="Review the log expression. Never log passwords, tokens, or credentials. Mask or redact before logging.",
                        tags=self.tags,
                    ))
        return findings


class SubflowDepthRule(Rule):
    id = "FLOGO-006"
    severity = Severity.INFO
    category = "complexity"
    tags = ["complexity", "maintainability"]
    _MAX = 4

    def check(self, ctx: FlogoContext) -> list[Finding]:
        findings = []
        for flow in ctx.flows:
            count = sum(
                1 for t in flow.tasks
                if "subflow" in t.activity_ref.lower() or "flow" in t.activity_ref.lower()
            )
            if count > self._MAX:
                findings.append(Finding(
                    rule_id=self.id,
                    severity=self.severity,
                    title="High Subflow Call Count",
                    location=f"flow:{flow.name}",
                    message=f"Flow calls {count} subflows. High fan-out increases debugging difficulty.",
                    recommendation="Review whether all subflows are necessary. Group related operations or use a shared library pattern.",
                    tags=self.tags,
                ))
        return findings
