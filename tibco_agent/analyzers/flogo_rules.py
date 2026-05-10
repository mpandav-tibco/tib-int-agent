from __future__ import annotations

import re as _re
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
    connections: list[dict] = field(default_factory=list)


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
        well_named = [f for f in ctx.flows if "_" in f.name]
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


class TimeoutConfiguredRule(Rule):
    id = "FLOGO-P006"
    severity = Severity.GOOD
    category = "reliability"

    def check(self, ctx: FlogoContext) -> list[Finding]:
        http_tasks = [
            t for flow in ctx.flows for t in flow.tasks
            if _matches(t.activity_ref, _HTTP_REFS)
        ]
        if not http_tasks:
            return []
        all_have_timeout = all(
            (t.input.get("timeout") or t.settings.get("timeout"))
            for t in http_tasks
        )
        if all_have_timeout:
            return [Finding(
                rule_id=self.id, severity=self.severity,
                title="All HTTP activities have timeouts configured",
                location="all HTTP activities",
                message=(
                    f"All {len(http_tasks)} HTTP activity/activities have explicit timeout "
                    "values — prevents hanging threads under sustained load."
                ),
                recommendation="",
            )]
        return []


# ── New issue rules ───────────────────────────────────────────────────────────

class HttpRetryRule(Rule):
    id = "FLOGO-007"
    severity = Severity.WARNING
    category = "reliability"
    tags = ["http", "retry", "resilience"]

    def check(self, ctx: FlogoContext) -> list[Finding]:
        findings = []
        for flow in ctx.flows:
            for task in flow.tasks:
                if not _matches(task.activity_ref, _HTTP_REFS):
                    continue
                has_retry = (
                    task.settings.get("retryCount")
                    or task.settings.get("retry")
                    or task.input.get("retryCount")
                    or task.input.get("maxRetries")
                )
                if not has_retry:
                    findings.append(Finding(
                        rule_id=self.id,
                        severity=self.severity,
                        title="HTTP Activity — No Retry Logic",
                        location=f"flow:{flow.name} / activity:{task.name}",
                        message=(
                            "No retry configuration found. Transient network failures "
                            "surface as immediate errors with no recovery attempt."
                        ),
                        recommendation=(
                            "Set retryCount=3 and retryDelay=1000ms on the REST activity, "
                            "or wrap the call in a Flogo repeat loop with exponential backoff."
                        ),
                        tags=self.tags,
                    ))
        return findings


_CREDENTIAL_HEADER_NAMES = frozenset({
    "authorization", "x-api-key", "x-auth-token", "x-access-token",
    "x-secret", "x-password", "api-key",
})


class HardcodedCredentialRule(Rule):
    id = "FLOGO-008"
    severity = Severity.ERROR
    category = "security"
    tags = ["security", "credentials", "secret"]

    def check(self, ctx: FlogoContext) -> list[Finding]:
        findings = []
        for flow in ctx.flows:
            for task in flow.tasks:
                if not _matches(task.activity_ref, _HTTP_REFS):
                    continue
                headers = task.input.get("headers", {})
                if not isinstance(headers, dict):
                    continue
                for hdr_name, hdr_val in headers.items():
                    val_str = str(hdr_val or "")
                    # Only flag literal values — $activity, $env, $property references are safe
                    if (
                        hdr_name.lower() in _CREDENTIAL_HEADER_NAMES
                        and val_str
                        and not val_str.startswith("$")
                        and len(val_str) > 4
                    ):
                        findings.append(Finding(
                            rule_id=self.id,
                            severity=self.severity,
                            title="Hardcoded Credential in HTTP Header",
                            location=f"flow:{flow.name} / activity:{task.name}",
                            message=(
                                f"Header `{hdr_name}` contains a literal value that looks like "
                                "a hardcoded credential. Literal secrets in .flogo files are "
                                "committed to source control and visible in the container image."
                            ),
                            recommendation=(
                                "Move credentials to Flogo app properties: `$property[API_TOKEN]`. "
                                "In Kubernetes, back the property with a Secret resource."
                            ),
                            tags=self.tags,
                        ))
        return findings


class LargeFlowRule(Rule):
    id = "FLOGO-009"
    severity = Severity.WARNING
    category = "complexity"
    tags = ["complexity", "maintainability", "flow-design"]
    _MAX_TASKS = 15

    def check(self, ctx: FlogoContext) -> list[Finding]:
        findings = []
        for flow in ctx.flows:
            count = len(flow.tasks)
            if count > self._MAX_TASKS:
                findings.append(Finding(
                    rule_id=self.id,
                    severity=self.severity,
                    title="Oversized Flow",
                    location=f"flow:{flow.name}",
                    message=(
                        f"Flow has {count} activities (threshold: {self._MAX_TASKS}). "
                        "Large monolithic flows are hard to unit-test, debug, and maintain."
                    ),
                    recommendation=(
                        "Decompose by responsibility: validation → transformation → "
                        "backend call → response mapping. Each subflow should have a single purpose."
                    ),
                    tags=self.tags,
                ))
        return findings


class LargeLogPayloadRule(Rule):
    """Flag Log activities that map entire objects ($flow, $activity[x].output) rather than specific fields."""
    id = "FLOGO-011"
    severity = Severity.WARNING
    category = "performance"
    tags = ["log", "performance", "payload", "security"]

    # Matches $flow or $activity[name].input / $activity[name].output without a further field path
    _BULK_RE = _re.compile(
        r"\$flow\b|\$activity\[[^\]]+\]\.(input|output)(?!\.[a-zA-Z_])",
        _re.IGNORECASE,
    )

    def check(self, ctx: FlogoContext) -> list[Finding]:
        findings = []
        for flow in ctx.flows:
            for task in flow.tasks:
                if not _matches(task.activity_ref, _LOG_REFS):
                    continue
                msg = str(task.input.get("message", ""))
                if self._BULK_RE.search(msg):
                    findings.append(Finding(
                        rule_id=self.id,
                        severity=self.severity,
                        title="Bulk Object Logged",
                        location=f"flow:{flow.name} / activity:{task.name}",
                        message=(
                            "Log message maps an entire $flow or $activity object. "
                            "This serializes the full object tree — large payloads, "
                            "potential PII exposure, and significant overhead under load."
                        ),
                        recommendation=(
                            "Log only specific fields: `$activity[CallService].output.statusCode` "
                            "instead of `$activity[CallService].output`. "
                            "Use a structured log format with key fields only."
                        ),
                        tags=self.tags,
                    ))
        return findings


class HardcodedUrlRule(Rule):
    """Flag REST activities where the URI is a literal URL instead of an app property reference."""
    id = "FLOGO-012"
    severity = Severity.WARNING
    category = "configuration"
    tags = ["url", "configuration", "portability", "environment"]

    _URL_RE = _re.compile(r"https?://[a-zA-Z0-9]", _re.IGNORECASE)

    def check(self, ctx: FlogoContext) -> list[Finding]:
        findings = []
        for flow in ctx.flows:
            for task in flow.tasks:
                if not _matches(task.activity_ref, _HTTP_REFS):
                    continue
                uri = str(task.input.get("uri", "") or task.input.get("url", ""))
                if self._URL_RE.search(uri) and not uri.strip().startswith("$"):
                    findings.append(Finding(
                        rule_id=self.id,
                        severity=self.severity,
                        title="Hardcoded URL in REST Activity",
                        location=f"flow:{flow.name} / activity:{task.name}",
                        message=(
                            f"URI `{uri[:80]}` is a literal value. "
                            "Hardcoded URLs cannot be changed per environment "
                            "without editing the .flogo file."
                        ),
                        recommendation=(
                            "Move the base URL to a Flogo app property: `$property[PAYMENT_SERVICE_URL]`. "
                            "Inject per environment via Kubernetes ConfigMap or Helm values."
                        ),
                        tags=self.tags,
                    ))
        return findings


class MissingCorrelationIdRule(Rule):
    id = "FLOGO-010"
    severity = Severity.INFO
    category = "observability"
    tags = ["observability", "tracing", "correlation"]

    _CORRELATION_KEYS = frozenset({
        "x-correlation-id", "x-request-id", "x-trace-id", "traceid",
        "correlationid", "correlation_id", "x-b3-traceid", "x-request-id",
    })

    def check(self, ctx: FlogoContext) -> list[Finding]:
        for flow in ctx.flows:
            for task in flow.tasks:
                headers = task.input.get("headers", {})
                if isinstance(headers, dict):
                    for k in headers:
                        if k.lower() in self._CORRELATION_KEYS:
                            return []
                # Also check string representation of all input/settings
                combined = str(task.input).lower() + str(task.settings).lower()
                if any(k in combined for k in self._CORRELATION_KEYS):
                    return []
        return [Finding(
            rule_id=self.id,
            severity=self.severity,
            title="No Correlation ID Propagation",
            location="all flows",
            message=(
                "No correlation/trace header (X-Correlation-ID, X-Request-ID) found "
                "in any HTTP activity. Without this, requests cannot be traced across services."
            ),
            recommendation=(
                "Extract X-Correlation-ID from the trigger input headers and forward it on all "
                "outbound REST calls. Generate a UUID if absent: "
                "`coalesce($trigger.output.headers['X-Correlation-ID'], uuid())`."
            ),
            tags=self.tags,
        )]


# ── FLOGO-013: Missing Pagination Guard ─────────────────────────────────────

_NO_PAGINATION = _re.compile(
    r"\bSELECT\b",
    _re.IGNORECASE,
)
_HAS_PAGINATION = _re.compile(
    r"\b(LIMIT|TOP|ROWNUM|FETCH\s+FIRST|FETCH\s+NEXT)\b",
    _re.IGNORECASE,
)


class MissingPaginationRule(Rule):
    id = "FLOGO-013"
    severity = Severity.WARNING
    category = "performance"
    tags = frozenset({"jdbc", "performance", "pagination"})

    def check(self, ctx: FlogoContext) -> list[Finding]:
        findings = []
        for flow in ctx.flows:
            for task in flow.tasks:
                if not _matches(task.activity_ref, _JDBC_REFS):
                    continue
                query_text = str(task.input.get("query", ""))
                if _NO_PAGINATION.search(query_text) and not _HAS_PAGINATION.search(query_text):
                    findings.append(Finding(
                        rule_id=self.id,
                        severity=self.severity,
                        title="JDBC Query Missing Pagination Guard",
                        location=f"flow:{flow.name}/activity:{task.name}",
                        message=(
                            "JDBC query has no pagination guard — may return unbounded result "
                            "sets and cause memory pressure under load."
                        ),
                        recommendation=(
                            "Add LIMIT (MySQL/PostgreSQL), TOP N (SQL Server), ROWNUM (Oracle), "
                            "or FETCH FIRST N ROWS ONLY (ANSI) to bound result sets."
                        ),
                        tags=self.tags,
                    ))
        return findings


# ── FLOGO-014: Duplicate REST Endpoint Calls ─────────────────────────────────

class DuplicateRestEndpointRule(Rule):
    id = "FLOGO-014"
    severity = Severity.INFO
    category = "performance"
    tags = frozenset({"rest", "performance", "caching"})

    def check(self, ctx: FlogoContext) -> list[Finding]:
        findings = []
        for flow in ctx.flows:
            uri_counts: dict[str, int] = {}
            for task in flow.tasks:
                if not _matches(task.activity_ref, _HTTP_REFS):
                    continue
                uri = str(task.input.get("uri", task.input.get("url", ""))).strip()
                if uri:
                    uri_counts[uri] = uri_counts.get(uri, 0) + 1
            for uri, count in uri_counts.items():
                if count >= 2:
                    findings.append(Finding(
                        rule_id=self.id,
                        severity=self.severity,
                        title="Duplicate REST Endpoint Calls in Flow",
                        location=f"flow:{flow.name}",
                        message=(
                            f"REST endpoint '{uri}' is called {count}× in the same flow. "
                            "Repeated identical calls add latency without benefit."
                        ),
                        recommendation=(
                            "Cache the response in a flow variable after the first call, or "
                            "refactor to batch/combine the requests."
                        ),
                        tags=self.tags,
                    ))
        return findings


# ── FLOGO-015: Duplicate / Localhost Connector ───────────────────────────────

_LOCALHOST_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class DuplicateConnectorRule(Rule):
    id = "FLOGO-015"
    severity = Severity.WARNING
    category = "configuration"
    tags = frozenset({"connector", "configuration", "security"})

    def check(self, ctx: FlogoContext) -> list[Finding]:
        findings: list[Finding] = []
        seen_names: dict[str, str] = {}

        for conn in ctx.connections:
            name = str(conn.get("name", "")).strip()
            name_lower = name.lower()
            if name_lower in seen_names:
                findings.append(Finding(
                    rule_id=self.id,
                    severity=self.severity,
                    title="Duplicate Connector Name",
                    location=f"connection:{name}",
                    message=(
                        f"Connection name '{name}' appears more than once (previous: "
                        f"'{seen_names[name_lower]}'). Duplicate names cause silent shadowing."
                    ),
                    recommendation="Ensure every connector has a unique, descriptive name.",
                    tags=self.tags,
                ))
            else:
                seen_names[name_lower] = name

            host = str(conn.get("settings", {}).get("host", "")).strip()
            if host.lower() in _LOCALHOST_HOSTS or not host:
                label = repr(host) if host else "(empty)"
                findings.append(Finding(
                    rule_id=self.id,
                    severity=self.severity,
                    title="Connector Points to Localhost / Empty Host",
                    location=f"connection:{name}",
                    message=(
                        f"Connector '{name}' has host={label}. "
                        "Localhost addresses break in container / cloud deployments."
                    ),
                    recommendation=(
                        "Replace the host value with a resolvable service name or environment "
                        "variable reference (e.g. `$env[MY_SERVICE_HOST]`)."
                    ),
                    tags=self.tags,
                ))
        return findings
