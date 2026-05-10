from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

from .base import AnalysisReport, Analyzer, Finding, Rule, Severity


# ── Data model ───────────────────────────────────────────────────────────────

@dataclass
class KubeContainer:
    name: str
    image: str
    has_readiness_probe: bool
    has_liveness_probe: bool
    has_resource_limits: bool
    has_resource_requests: bool
    runs_as_root: bool  # True when runAsNonRoot is absent or False


@dataclass
class KubeManifest:
    kind: str
    name: str
    namespace: str
    containers: list[KubeContainer] = field(default_factory=list)


@dataclass
class KubeContext:
    manifests: list[KubeManifest]
    source: str


# ── Helpers ───────────────────────────────────────────────────────────────────

_IMAGE_TAG_RE = re.compile(r":.+$")


def _parse_containers(spec: dict) -> list[KubeContainer]:
    containers = spec.get("containers", []) + spec.get("initContainers", [])
    result: list[KubeContainer] = []
    for c in containers:
        image = str(c.get("image", ""))
        # Tag is absent or literally "latest"
        tag_match = _IMAGE_TAG_RE.search(image)
        tag = tag_match.group(0)[1:] if tag_match else ""

        sec_ctx = c.get("securityContext", {}) or {}
        runs_as_root = not sec_ctx.get("runAsNonRoot", False)

        resources = c.get("resources", {}) or {}
        result.append(KubeContainer(
            name=c.get("name", "unnamed"),
            image=image,
            has_readiness_probe=bool(c.get("readinessProbe")),
            has_liveness_probe=bool(c.get("livenessProbe")),
            has_resource_limits=bool(resources.get("limits")),
            has_resource_requests=bool(resources.get("requests")),
            runs_as_root=runs_as_root,
        ))
    return result


def _parse_manifest(doc: dict) -> KubeManifest | None:
    kind = doc.get("kind", "")
    if kind not in {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "Pod"}:
        return None
    meta = doc.get("metadata", {}) or {}
    name = meta.get("name", "unnamed")
    namespace = meta.get("namespace", "")

    # Locate the pod spec — varies by kind
    if kind == "CronJob":
        spec = (doc.get("spec", {}) or {}).get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec", {}) or {}
    elif kind in {"Job", "Deployment", "StatefulSet", "DaemonSet"}:
        spec = (doc.get("spec", {}) or {}).get("template", {}).get("spec", {}) or {}
    else:
        spec = doc.get("spec", {}) or {}

    return KubeManifest(
        kind=kind,
        name=name,
        namespace=namespace,
        containers=_parse_containers(spec),
    )


# ── Rules ─────────────────────────────────────────────────────────────────────

class KubeLatestImageRule(Rule):
    id = "KUBE-001"
    severity = Severity.ERROR
    category = "reliability"
    tags = ["image", "tag", "reliability"]

    def check(self, ctx: KubeContext) -> list[Finding]:
        findings = []
        for m in ctx.manifests:
            for c in m.containers:
                image = c.image
                tag_match = _IMAGE_TAG_RE.search(image)
                tag = tag_match.group(0)[1:] if tag_match else ""
                if not tag or tag == "latest":
                    findings.append(Finding(
                        rule_id=self.id,
                        severity=self.severity,
                        title="Image Uses 'latest' or Has No Tag",
                        location=f"{m.kind}/{m.name} > container:{c.name}",
                        message=(
                            f"Image `{image}` uses {'`latest`' if tag == 'latest' else 'no tag'}. "
                            "Untagged or `latest` images make deployments non-reproducible and "
                            "can silently pull incompatible versions."
                        ),
                        recommendation=(
                            "Pin to an immutable digest or explicit version tag "
                            "(e.g. `myimage:1.4.2` or `myimage@sha256:abc...`)."
                        ),
                        tags=self.tags,
                    ))
        return findings


class KubeMissingReadinessProbeRule(Rule):
    id = "KUBE-002"
    severity = Severity.ERROR
    category = "reliability"
    tags = ["probe", "readiness", "reliability"]

    def check(self, ctx: KubeContext) -> list[Finding]:
        findings = []
        for m in ctx.manifests:
            for c in m.containers:
                if not c.has_readiness_probe:
                    findings.append(Finding(
                        rule_id=self.id,
                        severity=self.severity,
                        title="Missing readinessProbe",
                        location=f"{m.kind}/{m.name} > container:{c.name}",
                        message=(
                            "No `readinessProbe` defined. Kubernetes will route traffic to the "
                            "container before it is ready to serve requests, causing errors."
                        ),
                        recommendation=(
                            "Add a `readinessProbe` (HTTP GET, TCP, or exec) that returns success "
                            "only when the application can handle traffic."
                        ),
                        tags=self.tags,
                    ))
        return findings


class KubeMissingLivenessProbeRule(Rule):
    id = "KUBE-003"
    severity = Severity.WARNING
    category = "reliability"
    tags = ["probe", "liveness", "reliability"]

    def check(self, ctx: KubeContext) -> list[Finding]:
        findings = []
        for m in ctx.manifests:
            for c in m.containers:
                if not c.has_liveness_probe:
                    findings.append(Finding(
                        rule_id=self.id,
                        severity=self.severity,
                        title="Missing livenessProbe",
                        location=f"{m.kind}/{m.name} > container:{c.name}",
                        message=(
                            "No `livenessProbe` defined. A stuck or deadlocked container will not "
                            "be restarted automatically."
                        ),
                        recommendation=(
                            "Add a `livenessProbe` that checks application health. "
                            "Use a separate endpoint from the readiness probe if possible."
                        ),
                        tags=self.tags,
                    ))
        return findings


class KubeMissingResourceLimitsRule(Rule):
    id = "KUBE-004"
    severity = Severity.ERROR
    category = "reliability"
    tags = ["resources", "limits", "reliability"]

    def check(self, ctx: KubeContext) -> list[Finding]:
        findings = []
        for m in ctx.manifests:
            for c in m.containers:
                if not c.has_resource_limits:
                    findings.append(Finding(
                        rule_id=self.id,
                        severity=self.severity,
                        title="Missing Resource Limits",
                        location=f"{m.kind}/{m.name} > container:{c.name}",
                        message=(
                            "No `resources.limits` defined. An unconstrained container can consume "
                            "all node resources and cause cascading failures."
                        ),
                        recommendation=(
                            "Set `resources.limits.cpu` and `resources.limits.memory` appropriate "
                            "for the workload. Start with 2× the observed average usage."
                        ),
                        tags=self.tags,
                    ))
        return findings


class KubeMissingResourceRequestsRule(Rule):
    id = "KUBE-005"
    severity = Severity.WARNING
    category = "reliability"
    tags = ["resources", "requests", "reliability"]

    def check(self, ctx: KubeContext) -> list[Finding]:
        findings = []
        for m in ctx.manifests:
            for c in m.containers:
                if not c.has_resource_requests:
                    findings.append(Finding(
                        rule_id=self.id,
                        severity=self.severity,
                        title="Missing Resource Requests",
                        location=f"{m.kind}/{m.name} > container:{c.name}",
                        message=(
                            "No `resources.requests` defined. The scheduler cannot make informed "
                            "placement decisions, leading to over-scheduled nodes."
                        ),
                        recommendation=(
                            "Set `resources.requests.cpu` and `resources.requests.memory` to "
                            "match expected baseline consumption."
                        ),
                        tags=self.tags,
                    ))
        return findings


class KubeRunsAsRootRule(Rule):
    id = "KUBE-006"
    severity = Severity.WARNING
    category = "security"
    tags = ["security", "rootless", "best-practice"]

    def check(self, ctx: KubeContext) -> list[Finding]:
        findings = []
        for m in ctx.manifests:
            for c in m.containers:
                if c.runs_as_root:
                    findings.append(Finding(
                        rule_id=self.id,
                        severity=self.severity,
                        title="Container May Run as Root",
                        location=f"{m.kind}/{m.name} > container:{c.name}",
                        message=(
                            "`securityContext.runAsNonRoot` is not set to `true`. The container "
                            "may run as root (UID 0), increasing the blast radius of a compromise."
                        ),
                        recommendation=(
                            "Set `securityContext.runAsNonRoot: true` and specify a non-zero "
                            "`runAsUser` UID. Rebuild the image to run as a non-root user if needed."
                        ),
                        tags=self.tags,
                    ))
        return findings


class KubeMissingNamespaceRule(Rule):
    id = "KUBE-007"
    severity = Severity.INFO
    category = "configuration"
    tags = ["namespace", "configuration"]

    def check(self, ctx: KubeContext) -> list[Finding]:
        findings = []
        for m in ctx.manifests:
            if not m.namespace:
                findings.append(Finding(
                    rule_id=self.id,
                    severity=self.severity,
                    title="No Namespace Specified",
                    location=f"{m.kind}/{m.name}",
                    message=(
                        "No `metadata.namespace` defined. The manifest will be applied to the "
                        "current kubectl context namespace, which may not be the intended target."
                    ),
                    recommendation=(
                        "Explicitly set `metadata.namespace` to avoid accidental deployment "
                        "to the wrong namespace."
                    ),
                    tags=self.tags,
                ))
        return findings


# ── Analyzer ─────────────────────────────────────────────────────────────────

class KubeAnalyzer(Analyzer):
    """
    Analyzes Kubernetes YAML manifests (Deployment, StatefulSet, DaemonSet,
    Job, CronJob, Pod) against security and reliability best practices.
    Accepts multi-document YAML (--- separated).
    """

    def _default_rules(self) -> list[Rule]:
        return [
            KubeLatestImageRule(),
            KubeMissingReadinessProbeRule(),
            KubeMissingResourceLimitsRule(),
            KubeMissingLivenessProbeRule(),
            KubeMissingResourceRequestsRule(),
            KubeRunsAsRootRule(),
            KubeMissingNamespaceRule(),
        ]

    def analyze(self, content: str, source: str = "unknown.yaml") -> AnalysisReport:
        report = AnalysisReport(source=source, product="kubernetes")
        manifests: list[KubeManifest] = []

        try:
            docs = list(yaml.safe_load_all(content))
        except yaml.YAMLError as e:
            report.findings.append(Finding(
                rule_id="KUBE-000",
                severity=Severity.ERROR,
                title="YAML Parse Error",
                location="file root",
                message=f"Could not parse YAML: {e}",
                recommendation="Validate the YAML with `kubectl apply --dry-run=client -f <file>`.",
            ))
            return report

        for doc in docs:
            if not isinstance(doc, dict):
                continue
            m = _parse_manifest(doc)
            if m is not None:
                manifests.append(m)

        if not manifests:
            report.observations.append(
                "No supported workload kinds found (Deployment, StatefulSet, DaemonSet, Job, CronJob, Pod)."
            )
            return report

        ctx = KubeContext(manifests=manifests, source=source)
        report.overview = {
            "manifest_count": len(manifests),
            "kinds": list({m.kind for m in manifests}),
            "namespaces": list({m.namespace for m in manifests if m.namespace}),
        }

        for rule in self._rules:
            report.findings.extend(rule.check(ctx))

        return report
