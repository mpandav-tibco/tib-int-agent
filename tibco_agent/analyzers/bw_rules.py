from __future__ import annotations

import re
from dataclasses import dataclass
from xml.etree.ElementTree import Element

from .base import Finding, Rule, Severity


# ── Data model ───────────────────────────────────────────────────────────────

@dataclass
class BWActivity:
    tag: str        # local XML tag name
    name: str
    element: Element


@dataclass
class BWProcess:
    name: str
    file_name: str
    activities: list[BWActivity]
    has_fault_handler: bool
    raw: Element


@dataclass
class BWContext:
    processes: list[BWProcess]
    raw_files: dict[str, Element]   # filename → root element


# ── XML helpers ──────────────────────────────────────────────────────────────

def local_tag(element: Element) -> str:
    """Strip XML namespace from tag: {ns}localName → localName."""
    t = element.tag
    return t.split("}", 1)[1] if "}" in t else t


def find_by_local(root: Element, *names: str) -> list[Element]:
    """Recursively find all elements whose local tag is in names."""
    results: list[Element] = []
    for elem in root.iter():
        if local_tag(elem) in names:
            results.append(elem)
    return results


def text_of(element: Element) -> str:
    return (element.text or "").strip()


# ── Reference sets ────────────────────────────────────────────────────────────

# BW6 HTTP / REST invoke activity tags (vary by palette version)
_HTTP_ACTIVITY_TAGS = frozenset({
    "HTTPClientActivity", "RESTActivity", "InvokeRESTAPI",
    "httpClient", "restClient", "invokeRestService",
})

# Tags that indicate an error/fault handler branch
_FAULT_HANDLER_TAGS = frozenset({
    "faultHandlers", "catchAll", "catch", "errorHandlers",
    "onError", "FaultHandler", "ErrorTransitions",
})

# Tags for JDBC query activities
_JDBC_TAGS = frozenset({
    "JDBCQueryActivity", "jdbcQuery", "QueryActivity",
    "callStoredProcedure", "jdbcCall",
})

# Tags that hold endpoint/URL configuration
_URL_CONFIG_TAGS = frozenset({
    "host", "endpointURI", "location", "url", "endpoint",
    "connectionURL", "baseURL", "serviceURL",
})

# Property reference patterns — these are NOT hardcoded
_PROP_RE = re.compile(r"%%|%\w+%|\$module\.|\$\.module\.|#Properties\[")

# Password element tags
_PASSWORD_TAGS = frozenset({"password", "Password", "passwd", "Passwd"})

# Encrypted password prefixes used by BW
_ENCRYPTED_PREFIXES = ("{ENCRYPT}", "{AES}", "OBF:", "{BwEncrypt}")


# ── Rules ─────────────────────────────────────────────────────────────────────

class BWMissingFaultHandlerRule(Rule):
    id = "BWP-001"
    severity = Severity.ERROR
    category = "error-handling"
    tags = ["error-handler", "resilience"]

    def check(self, ctx: BWContext) -> list[Finding]:
        return [
            Finding(
                rule_id=self.id,
                severity=self.severity,
                title="Missing Fault Handler",
                location=f"process:{p.name}",
                message=(
                    "No fault handler (catchAll/catch) defined. Uncaught exceptions "
                    "will surface as unhandled faults with no structured error response."
                ),
                recommendation=(
                    "Add a Catch All or Catch block. Inside it, log the fault with "
                    "$err/errorCode and $err/msg, then send a structured error reply "
                    "or re-throw with a meaningful fault name."
                ),
                tags=self.tags,
            )
            for p in ctx.processes
            if not p.has_fault_handler
        ]


class BWHardcodedUrlRule(Rule):
    id = "BWP-002"
    severity = Severity.WARNING
    category = "configuration"
    tags = ["hardcoded", "url", "configuration"]

    def check(self, ctx: BWContext) -> list[Finding]:
        findings = []
        for p in ctx.processes:
            for elem in find_by_local(p.raw, *_URL_CONFIG_TAGS):
                val = text_of(elem)
                if not val:
                    continue
                # Only flag if it looks like a literal URL (http/https) with no property reference
                if re.search(r"https?://", val) and not _PROP_RE.search(val):
                    findings.append(Finding(
                        rule_id=self.id,
                        severity=self.severity,
                        title="Hardcoded URL / Endpoint",
                        location=f"process:{p.name} / {local_tag(elem)}",
                        message=f"Literal URL `{val[:80]}` found in process config.",
                        recommendation=(
                            "Replace with a module property reference: "
                            "`%%p_EndpointURL%%` (BW5) or a Module Property variable (BW6). "
                            "Set the value per environment in the deployment descriptor."
                        ),
                        tags=self.tags,
                    ))
        return findings


class BWPlainPasswordRule(Rule):
    id = "BWP-003"
    severity = Severity.ERROR
    category = "security"
    tags = ["security", "credentials", "password"]

    def check(self, ctx: BWContext) -> list[Finding]:
        findings = []
        for p in ctx.processes:
            for elem in find_by_local(p.raw, *_PASSWORD_TAGS):
                val = text_of(elem)
                if not val:
                    continue
                if not any(val.startswith(pfx) for pfx in _ENCRYPTED_PREFIXES):
                    findings.append(Finding(
                        rule_id=self.id,
                        severity=self.severity,
                        title="Plain-Text Password in Process",
                        location=f"process:{p.name} / {local_tag(elem)}",
                        message=(
                            "A password element contains a value that does not appear to be "
                            "encrypted. Plain-text credentials stored in process files are "
                            "committed to version control."
                        ),
                        recommendation=(
                            "Encrypt passwords using BW obfuscation (`bwencrypt`) or, "
                            "in BWCE/Kubernetes, back credentials with a Secret resource "
                            "mounted as an environment variable."
                        ),
                        tags=self.tags,
                    ))
        return findings


class BWMissingRetryRule(Rule):
    id = "BWP-004"
    severity = Severity.WARNING
    category = "reliability"
    tags = ["http", "retry", "resilience"]

    def check(self, ctx: BWContext) -> list[Finding]:
        findings = []
        for p in ctx.processes:
            for act in p.activities:
                if act.tag not in _HTTP_ACTIVITY_TAGS:
                    continue
                # Look for retry-related config inside this element
                retry_elems = find_by_local(act.element, "retryCount", "maxRetries", "retryAttempts", "retry")
                has_retry = any(int(text_of(e) or "0") > 0 for e in retry_elems)
                if not has_retry:
                    findings.append(Finding(
                        rule_id=self.id,
                        severity=self.severity,
                        title="HTTP Activity — No Retry Configured",
                        location=f"process:{p.name} / activity:{act.name}",
                        message=(
                            "HTTP/REST activity has no retry count configured. "
                            "Transient failures will immediately propagate as faults."
                        ),
                        recommendation=(
                            "Set retryCount ≥ 3 on the HTTP Client activity. "
                            "Add exponential backoff in the retry delay settings."
                        ),
                        tags=self.tags,
                    ))
        return findings


class BWSelectStarRule(Rule):
    id = "BWP-005"
    severity = Severity.WARNING
    category = "performance"
    tags = ["jdbc", "sql", "performance"]

    def check(self, ctx: BWContext) -> list[Finding]:
        findings = []
        for p in ctx.processes:
            for elem in find_by_local(p.raw, "queryStatement", "statement", "query", "sqlQuery"):
                val = text_of(elem)
                if "SELECT *" in val.upper():
                    findings.append(Finding(
                        rule_id=self.id,
                        severity=self.severity,
                        title="SELECT * in JDBC Query",
                        location=f"process:{p.name} / {local_tag(elem)}",
                        message="SELECT * fetches all columns, wasting network bandwidth and memory.",
                        recommendation="Enumerate only the columns needed: SELECT id, name, status FROM ...",
                        tags=self.tags,
                    ))
        return findings


class BWLargeProcessRule(Rule):
    id = "BWP-006"
    severity = Severity.INFO
    category = "complexity"
    tags = ["complexity", "maintainability"]
    _MAX = 20

    def check(self, ctx: BWContext) -> list[Finding]:
        findings = []
        for p in ctx.processes:
            count = len(p.activities)
            if count > self._MAX:
                findings.append(Finding(
                    rule_id=self.id,
                    severity=self.severity,
                    title="Large Process",
                    location=f"process:{p.name}",
                    message=f"Process has {count} activities (threshold: {self._MAX}). Large processes are harder to test and maintain.",
                    recommendation=(
                        "Extract logical sub-flows into separate called processes. "
                        "Each process should do one thing: validate, transform, or invoke a backend."
                    ),
                    tags=self.tags,
                ))
        return findings


# ── BWP-007: Localhost URL (ERROR) ───────────────────────────────────────────

_LOCALHOST_RE = re.compile(r"https?://(localhost|127\.0\.0\.1)(:\d+)?", re.IGNORECASE)


class BWLocalhostUrlRule(Rule):
    id = "BWP-007"
    severity = Severity.ERROR
    category = "configuration"
    tags = ["hardcoded", "localhost", "configuration"]

    def check(self, ctx: BWContext) -> list[Finding]:
        findings = []
        for p in ctx.processes:
            for elem in find_by_local(p.raw, *_URL_CONFIG_TAGS):
                val = text_of(elem)
                if _LOCALHOST_RE.search(val):
                    findings.append(Finding(
                        rule_id=self.id,
                        severity=self.severity,
                        title="Localhost URL in Process Configuration",
                        location=f"process:{p.name} / {local_tag(elem)}",
                        message=(
                            f"URL `{val[:80]}` references localhost/127.0.0.1. "
                            "This will always fail in container or cloud deployments."
                        ),
                        recommendation=(
                            "Replace with a resolvable service name or module property: "
                            "`%%p_ServiceHost%%` (BW5) / Module Property (BW6)."
                        ),
                        tags=self.tags,
                    ))
        return findings


# ── BWP-008: Missing Substitution Variable ────────────────────────────────────

_SUBST_TAGS = frozenset({
    "host", "port", "jdbcUrl", "connectionString", "username",
    "connectionURL", "baseURL", "serviceURL", "endpoint", "endpointURI",
})
_SUBST_RE = re.compile(r"%\{[^}]+\}%")


class BWMissingSubstVarRule(Rule):
    id = "BWP-008"
    severity = Severity.WARNING
    category = "configuration"
    tags = ["configuration", "substitution", "environment"]

    def check(self, ctx: BWContext) -> list[Finding]:
        findings = []
        for p in ctx.processes:
            for elem in find_by_local(p.raw, *_SUBST_TAGS):
                if local_tag(elem) in _PASSWORD_TAGS:
                    continue  # BWP-003 already covers passwords
                val = text_of(elem)
                if len(val) >= 4 and not _PROP_RE.search(val) and not _SUBST_RE.search(val):
                    findings.append(Finding(
                        rule_id=self.id,
                        severity=self.severity,
                        title="Configuration Value Not Using Substitution Variable",
                        location=f"process:{p.name} / {local_tag(elem)}",
                        message=(
                            f"Element `{local_tag(elem)}` has literal value `{val[:60]}`. "
                            "Hard-coded config values cannot be overridden per environment."
                        ),
                        recommendation=(
                            "Replace with a BW6 module property or a BW5 substitution "
                            "variable (`%%p_VariableName%%`) so the value is set per deployment."
                        ),
                        tags=self.tags,
                    ))
        return findings


# ── Positive / strength rules ──────────────────────────────────────────────────

class BWFaultHandlerPresentRule(Rule):
    id = "BWP-P001"
    severity = Severity.GOOD
    category = "error-handling"

    def check(self, ctx: BWContext) -> list[Finding]:
        guarded = [p for p in ctx.processes if p.has_fault_handler]
        if guarded and len(guarded) == len(ctx.processes):
            return [Finding(
                rule_id=self.id, severity=self.severity,
                title="All processes have fault handlers",
                location="all processes",
                message=f"All {len(guarded)} process(es) define a fault handler — errors will be caught and handled.",
                recommendation="",
            )]
        return []
