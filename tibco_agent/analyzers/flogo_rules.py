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


# ── Technology detection ─────────────────────────────────────────────────────

_TECH_PATTERNS: list[tuple[str, str]] = [
    ("mpandav-tibco/flogo-extensions/vectordb", "Weaviate Vector DB (custom flogo-extensions connector)"),
    ("project-flogo/contrib/activity/rest",      "HTTP/REST client (project-flogo)"),
    ("tibco/flogo-general",                       "TIBCO Flogo General activities"),
    ("tibco/wi-contrib",                          "TIBCO Wi-Contrib activities"),
    ("project-flogo/contrib/activity/jdbc",       "JDBC database connector"),
    ("tibco/wi-ems",                              "TIBCO EMS messaging"),
    ("project-flogo/contrib/trigger/kafka",       "Apache Kafka trigger"),
    ("project-flogo/contrib/trigger/timer",       "Timer / scheduled trigger"),
    ("project-flogo/contrib/function",            "Flogo built-in functions"),
    ("tibco/wi-aws",                              "AWS connector"),
    ("tibco/wi-azure",                            "Azure connector"),
]


def detect_technologies(imports: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for imp in imports:
        for pattern, label in _TECH_PATTERNS:
            if pattern in imp and label not in seen:
                seen.add(label)
                result.append(label)
    return result or ["Standard Flogo activities"]


def detect_pattern(triggers: list[dict], flows: list["FlogoFlow"]) -> str:
    refs = " ".join(t.get("ref", "") for t in triggers).lower()
    if "rest" in refs or "http" in refs:
        return "REST API Gateway" if len(flows) >= 3 else "REST Microservice"
    if "kafka" in refs:
        return "Event-Driven Service (Kafka)"
    if "ems" in refs:
        return "Event-Driven Service (TIBCO EMS)"
    if "timer" in refs:
        return "Scheduled / Batch Processing"
    return "Flogo Application"


def extract_endpoints(triggers: list[dict]) -> list[dict]:
    endpoints = []
    for trigger in triggers:
        for handler in trigger.get("handlers", []):
            s = handler.get("settings", {})
            flow_uri = (
                handler.get("action", {})
                .get("settings", {})
                .get("flowURI", "")
                .replace("res://flow:", "")
            )
            endpoints.append({
                "method":      s.get("Method", "POST"),
                "path":        s.get("Path", "/"),
                "flow":        flow_uri,
                "description": handler.get("description", ""),
            })
    return endpoints


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


# ── Positive / strength rules (Severity.GOOD) ────────────────────────────────

class AppDescriptionRule(Rule):
    id = "FLOGO-P001"
    severity = Severity.GOOD
    category = "quality"

    def check(self, ctx: FlogoContext) -> list[Finding]:
        desc = ctx.raw.get("description", "").strip()
        if desc:
            return [Finding(
                rule_id=self.id, severity=self.severity,
                title="App has a description",
                location="app root",
                message=f'Documentation present: "{desc[:100]}"',
                recommendation="",
            )]
        return []


class FlowNamingConventionRule(Rule):
    id = "FLOGO-P002"
    severity = Severity.GOOD
    category = "quality"

    def check(self, ctx: FlogoContext) -> list[Finding]:
        if not ctx.flows:
            return []
        well_named = [f for f in ctx.flows if "_" in f.name or f.name.islower()]
        if len(well_named) == len(ctx.flows):
            return [Finding(
                rule_id=self.id, severity=self.severity,
                title="Consistent flow naming convention",
                location="all flows",
                message=f"All {len(ctx.flows)} flows follow snake_case naming — improves readability and searchability.",
                recommendation="",
            )]
        return []


class DedicatedConnectorRule(Rule):
    id = "FLOGO-P003"
    severity = Severity.GOOD
    category = "architecture"

    def check(self, ctx: FlogoContext) -> list[Finding]:
        connectors = [i for i in ctx.raw.get("imports", []) if "connector" in i.lower()]
        if connectors:
            return [Finding(
                rule_id=self.id, severity=self.severity,
                title="Uses dedicated connector(s)",
                location="app imports",
                message=(
                    f"{len(connectors)} dedicated connector(s) detected. "
                    "Using typed connectors instead of raw HTTP calls provides schema validation, "
                    "connection pooling, and centralised credential management."
                ),
                recommendation="",
            )]
        return []


class SeparationOfConcernsRule(Rule):
    id = "FLOGO-P004"
    severity = Severity.GOOD
    category = "architecture"

    def check(self, ctx: FlogoContext) -> list[Finding]:
        names = [f.name.lower() for f in ctx.flows]
        has_write = any(kw in n for n in names for kw in ("ingest", "create", "write", "upload", "insert"))
        has_read  = any(kw in n for n in names for kw in ("query", "search", "read", "get", "fetch"))
        if has_write and has_read and len(ctx.flows) >= 2:
            return [Finding(
                rule_id=self.id, severity=self.severity,
                title="Read and write operations are separated",
                location="flow design",
                message=(
                    "Ingest (write) and query (read) paths are implemented as distinct flows. "
                    "This enables independent scaling, testing, and error handling per operation type."
                ),
                recommendation="",
            )]
        return []


class ApiVersioningRule(Rule):
    id = "FLOGO-P005"
    severity = Severity.GOOD
    category = "api-design"

    def check(self, ctx: FlogoContext) -> list[Finding]:
        # Check trigger has an API version set
        for trigger in ctx.triggers:
            version = trigger.get("settings", {}).get("apiVersion", "")
            if version and version != "1.0.0":
                return [Finding(
                    rule_id=self.id, severity=self.severity,
                    title="API versioning configured",
                    location=f"trigger:{trigger.get('name', trigger.get('id', ''))}",
                    message=f"Trigger exposes API version {version}, enabling controlled deprecation.",
                    recommendation="",
                )]
        return []
