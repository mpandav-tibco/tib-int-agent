"""
EMS Config Analyzer — static analysis of TIBCO EMS server configuration files.

Supports:
  - tibemsd.conf  (main EMS server daemon config, key = value format)

Run via chainlit UI by uploading a .conf file, or programmatically:
    report = EMSAnalyzer().analyze(content, source="tibemsd.conf")
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .base import AnalysisReport, Analyzer, Finding, Rule, Severity

# ── Parser ────────────────────────────────────────────────────────────────────

_COMMENT_RE = re.compile(r"#.*$")
_KV_RE = re.compile(r"^\s*(\w[\w.]*)\s*=\s*(.*?)\s*$")
_OBFUSCATED_RE = re.compile(r"\{[A-Z]+\}|#!|ENC\(")


@dataclass
class EMSConfig:
    """Parsed EMS server configuration."""
    params: dict[str, str]          # lowercased key → raw value string
    source: str = "tibemsd.conf"


def _parse_conf(content: str, source: str = "tibemsd.conf") -> EMSConfig:
    params: dict[str, str] = {}
    for line in content.splitlines():
        line = _COMMENT_RE.sub("", line).strip()
        if not line:
            continue
        m = _KV_RE.match(line)
        if m:
            params[m.group(1).lower()] = m.group(2).strip()
    return EMSConfig(params=params, source=source)


# ── Rules ─────────────────────────────────────────────────────────────────────

class EMSAuthorizationRule(Rule):
    id = "EMS-001"
    severity = Severity.ERROR
    category = "security"
    tags = ["authorization", "security", "access-control"]

    def check(self, ctx: EMSConfig) -> list[Finding]:
        val = ctx.params.get("authorization", "disabled").lower()
        if val in {"disabled", "false", "no", "off", "0"}:
            return [Finding(
                rule_id=self.id,
                severity=self.severity,
                title="EMS Authorization Disabled",
                location=f"{ctx.source} / authorization",
                message=(
                    f"`authorization` is set to `{val or 'disabled (default)'}`. "
                    "Any client can connect and send/receive messages without credentials."
                ),
                recommendation=(
                    "Set `authorization = enabled`. Then define user accounts and ACLs in "
                    "users.conf and acl.conf. Use `tibemsadmin` to reload: `adduser`, `grant`."
                ),
                tags=self.tags,
            )]
        return []


class EMSAdminPasswordRule(Rule):
    id = "EMS-002"
    severity = Severity.ERROR
    category = "security"
    tags = ["password", "security", "credentials"]

    def check(self, ctx: EMSConfig) -> list[Finding]:
        # The admin password may appear as `password` (server file) or inline
        val = ctx.params.get("password", None)
        if val is None:
            return []
        if val == "":
            return [Finding(
                rule_id=self.id,
                severity=self.severity,
                title="EMS Admin Password Is Empty",
                location=f"{ctx.source} / password",
                message=(
                    "The admin `password` field is empty. The default TIBCO EMS admin "
                    "account has no password, allowing unauthenticated admin access."
                ),
                recommendation=(
                    "Set a strong password for the admin user. Use `tibemsadmin` to change it: "
                    "`changepw admin <newpassword>`. Store it in a secrets manager."
                ),
                tags=self.tags,
            )]
        if not _OBFUSCATED_RE.search(val):
            return [Finding(
                rule_id=self.id,
                severity=self.severity,
                title="EMS Admin Password Stored in Plain Text",
                location=f"{ctx.source} / password",
                message=(
                    "The admin password appears to be stored as plain text in the config file. "
                    "Anyone with file-system read access can extract it."
                ),
                recommendation=(
                    "Use TIBCO EMS password obfuscation: run "
                    "`tibemsadmin -script obfuscate <password>` and replace the value with "
                    "the `{AES}...` output. Store the obfuscated value in the config."
                ),
                tags=self.tags,
            )]
        return []


class EMSSSLIdentityRule(Rule):
    id = "EMS-003"
    severity = Severity.WARNING
    category = "security"
    tags = ["ssl", "tls", "encryption", "security"]

    def check(self, ctx: EMSConfig) -> list[Finding]:
        has_identity = bool(ctx.params.get("ssl_server_identity"))
        has_key = bool(ctx.params.get("ssl_server_key"))
        if not has_identity or not has_key:
            missing = []
            if not has_identity:
                missing.append("`ssl_server_identity`")
            if not has_key:
                missing.append("`ssl_server_key`")
            return [Finding(
                rule_id=self.id,
                severity=self.severity,
                title="EMS Server SSL Not Configured",
                location=f"{ctx.source} / ssl_server_identity",
                message=(
                    f"SSL is not fully configured — missing: {', '.join(missing)}. "
                    "Without SSL, all EMS traffic (including credentials) is transmitted "
                    "in plain text."
                ),
                recommendation=(
                    "Set `ssl_server_identity` to the server certificate PEM file, "
                    "`ssl_server_key` to the private key PEM, and optionally "
                    "`ssl_server_trusted` to the CA bundle. "
                    "Clients must use `ssl://` URIs."
                ),
                tags=self.tags,
            )]
        return []


class EMSSSLClientCertRule(Rule):
    id = "EMS-004"
    severity = Severity.WARNING
    category = "security"
    tags = ["ssl", "tls", "mutual-tls", "security"]

    def check(self, ctx: EMSConfig) -> list[Finding]:
        val = ctx.params.get("ssl_require_client_cert", "").lower()
        if val not in {"enabled", "true", "yes", "on", "1"}:
            return [Finding(
                rule_id=self.id,
                severity=self.severity,
                title="EMS Client Certificate Authentication Not Required",
                location=f"{ctx.source} / ssl_require_client_cert",
                message=(
                    "`ssl_require_client_cert` is not set to `enabled`. "
                    "Clients can connect over SSL without presenting a certificate, "
                    "making mutual TLS authentication unavailable."
                ),
                recommendation=(
                    "Set `ssl_require_client_cert = enabled` and distribute client certificates "
                    "signed by your internal CA. This ensures only authorised clients connect."
                ),
                tags=self.tags,
            )]
        return []


class EMSMaxMessageMemoryRule(Rule):
    id = "EMS-005"
    severity = Severity.WARNING
    category = "reliability"
    tags = ["memory", "performance", "reliability"]

    def check(self, ctx: EMSConfig) -> list[Finding]:
        if "max_msg_memory" not in ctx.params:
            return [Finding(
                rule_id=self.id,
                severity=self.severity,
                title="EMS max_msg_memory Not Set",
                location=f"{ctx.source} / max_msg_memory",
                message=(
                    "`max_msg_memory` is not configured. EMS will use its built-in default, "
                    "which may allow unbounded memory growth under high message load."
                ),
                recommendation=(
                    "Set `max_msg_memory` to a value appropriate for the host (e.g. `512MB` "
                    "or `2GB`). Use `flow_control = enabled` together with this setting to "
                    "prevent producers from overwhelming the broker."
                ),
                tags=self.tags,
            )]
        return []


class EMSFlowControlRule(Rule):
    id = "EMS-006"
    severity = Severity.WARNING
    category = "reliability"
    tags = ["flow-control", "performance", "reliability"]

    def check(self, ctx: EMSConfig) -> list[Finding]:
        val = ctx.params.get("flow_control", "").lower()
        if val not in {"enabled", "true", "yes", "on", "1"}:
            return [Finding(
                rule_id=self.id,
                severity=self.severity,
                title="EMS Flow Control Not Enabled",
                location=f"{ctx.source} / flow_control",
                message=(
                    "`flow_control` is not enabled. Fast producers can overwhelm slow consumers, "
                    "causing unbounded queue growth and eventual out-of-memory conditions."
                ),
                recommendation=(
                    "Set `flow_control = enabled`. This works together with `max_msg_memory` "
                    "to back-pressure producers when the broker is under memory pressure."
                ),
                tags=self.tags,
            )]
        return []


class EMSBackupServerRule(Rule):
    id = "EMS-007"
    severity = Severity.INFO
    category = "reliability"
    tags = ["high-availability", "failover", "reliability"]

    def check(self, ctx: EMSConfig) -> list[Finding]:
        if "backup_server" not in ctx.params:
            return [Finding(
                rule_id=self.id,
                severity=self.severity,
                title="No EMS Backup Server Configured",
                location=f"{ctx.source} / backup_server",
                message=(
                    "`backup_server` is not set. If this EMS server fails there is no automatic "
                    "failover — clients will lose connectivity until the primary is restarted."
                ),
                recommendation=(
                    "Configure a secondary EMS server and set "
                    "`backup_server = tcp://<host>:<port>`. "
                    "Use a shared `store` directory (NFS/SAN) so the backup inherits message state."
                ),
                tags=self.tags,
            )]
        return []


class EMSListenPortRule(Rule):
    id = "EMS-008"
    severity = Severity.INFO
    category = "configuration"
    tags = ["listen", "port", "configuration"]

    def check(self, ctx: EMSConfig) -> list[Finding]:
        listen = ctx.params.get("listen", "")
        if not listen:
            return [Finding(
                rule_id=self.id,
                severity=self.severity,
                title="EMS Listen Address Not Explicitly Configured",
                location=f"{ctx.source} / listen",
                message=(
                    "No `listen` directive found. EMS will use its built-in default "
                    "(tcp://0.0.0.0:7222), binding on all interfaces."
                ),
                recommendation=(
                    "Explicitly set `listen = tcp://<ip>:7222` (or use `ssl://` for TLS). "
                    "Binding to a specific interface reduces the attack surface."
                ),
                tags=self.tags,
            )]
        if "0.0.0.0" in listen or listen.startswith("tcp://:") or "tcp://7222" == listen:
            return [Finding(
                rule_id=self.id,
                severity=self.severity,
                title="EMS Listening on All Network Interfaces",
                location=f"{ctx.source} / listen",
                message=(
                    f"`listen = {listen}` binds EMS on all network interfaces. "
                    "This exposes the port on interfaces that may not require EMS access."
                ),
                recommendation=(
                    "Bind to a specific internal IP: `listen = tcp://10.0.1.5:7222`. "
                    "Use a firewall to restrict access from unauthorised hosts."
                ),
                tags=self.tags,
            )]
        return []


# ── Analyzer ─────────────────────────────────────────────────────────────────

class EMSAnalyzer(Analyzer):
    """
    Analyzes TIBCO EMS server configuration files (tibemsd.conf).
    Accepts the raw text content of the config file.

    Supports multi-file analysis via analyze_multi({filename: content}).
    """

    def _default_rules(self) -> list[Rule]:
        return [
            EMSAuthorizationRule(),
            EMSAdminPasswordRule(),
            EMSSSLIdentityRule(),
            EMSSSLClientCertRule(),
            EMSMaxMessageMemoryRule(),
            EMSFlowControlRule(),
            EMSBackupServerRule(),
            EMSListenPortRule(),
        ]

    def analyze(self, content: str, source: str = "tibemsd.conf") -> AnalysisReport:
        report = AnalysisReport(source=source, product="ems")
        cfg = _parse_conf(content, source=source)
        report.overview = {
            "param_count": len(cfg.params),
            "has_ssl": bool(cfg.params.get("ssl_server_identity")),
            "authorization": cfg.params.get("authorization", "disabled"),
            "listen": cfg.params.get("listen", "(default tcp://0.0.0.0:7222)"),
            "backup_server": cfg.params.get("backup_server", "(none)"),
        }
        for rule in self._rules:
            report.findings.extend(rule.check(cfg))
        return report
