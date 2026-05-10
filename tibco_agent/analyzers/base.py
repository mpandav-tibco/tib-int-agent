from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    ERROR   = "ERROR"
    WARNING = "WARNING"
    INFO    = "INFO"
    GOOD    = "GOOD"    # positive / strength finding


@dataclass
class Finding:
    rule_id: str
    severity: Severity
    title: str
    location: str
    message: str
    recommendation: str
    tags: list[str] = field(default_factory=list)


@dataclass
class AnalysisReport:
    source: str
    product: str
    # Optional structured overview — populated by the analyzer, not rules
    overview: dict = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    positives: list[Finding] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.WARNING)

    def to_markdown(self) -> str:
        lines: list[str] = []
        ov = self.overview

        # ── Header ────────────────────────────────────────────────────────────
        lines.append(f"## App Review — `{self.source}`\n")

        # ── Overview ──────────────────────────────────────────────────────────
        if ov:
            lines.append("### Overview\n")
            if ov.get("description"):
                lines.append(f"> {ov['description']}\n")
            meta = []
            if ov.get("version"):
                meta.append(f"**Version:** {ov['version']}")
            if ov.get("pattern"):
                meta.append(f"**Pattern:** {ov['pattern']}")
            if ov.get("trigger_port"):
                meta.append(f"**Trigger:** REST on port {ov['trigger_port']}")
            flow_count = ov.get("flow_count", 0)
            ep_count = len(ov.get("endpoints", []))
            if flow_count:
                meta.append(f"**Flows:** {flow_count}")
            if ep_count:
                meta.append(f"**Endpoints:** {ep_count}")
            if meta:
                lines.append("  \n".join(meta) + "\n")

            # Endpoint table
            endpoints = ov.get("endpoints", [])
            if endpoints:
                lines.append("#### API Endpoints\n")
                lines.append("| Method | Path | Flow | Notes |")
                lines.append("|--------|------|------|-------|")
                for ep in endpoints:
                    lines.append(
                        f"| {ep['method']} | `{ep['path']}` | `{ep['flow']}` | {ep['description'][:70]} |"
                    )
                lines.append("")

            # Tech stack
            tech = ov.get("technologies", [])
            if tech:
                lines.append("#### Technology Stack\n")
                for t in tech:
                    lines.append(f"- {t}")
                lines.append("")

        # ── Strengths ─────────────────────────────────────────────────────────
        if self.positives:
            lines.append("### Strengths\n")
            for i, p in enumerate(self.positives, 1):
                lines.append(f"**{i}. [{p.rule_id}] {p.title}**")
                lines.append(f"- {p.message}\n")

        # ── Issues ────────────────────────────────────────────────────────────
        errors   = [f for f in self.findings if f.severity == Severity.ERROR]
        warnings = [f for f in self.findings if f.severity == Severity.WARNING]
        infos    = [f for f in self.findings if f.severity == Severity.INFO]

        if self.findings:
            lines.append(
                f"### Issues — {len(errors)} error(s), {len(warnings)} warning(s)"
                + (f", {len(infos)} info" if infos else "") + "\n"
            )
            for group, label in [(errors, "Errors"), (warnings, "Warnings"), (infos, "Info")]:
                if group:
                    lines.append(f"#### {label}\n")
                    for i, f in enumerate(group, 1):
                        lines.append(f"**{i}. [{f.rule_id}] {f.title}**")
                        lines.append(f"- Location: `{f.location}`")
                        lines.append(f"- {f.message}")
                        lines.append(f"- **Fix:** {f.recommendation}\n")
        else:
            lines.append("### Issues\n")
            lines.append("No issues found. All configured checks passed.\n")

        # ── Observations ──────────────────────────────────────────────────────
        if self.observations:
            lines.append("### Observations\n")
            for obs in self.observations:
                lines.append(f"- {obs}")

        return "\n".join(lines)


class Rule(ABC):
    id: str = ""
    severity: Severity = Severity.WARNING
    category: str = "general"
    tags: list[str] = []

    @abstractmethod
    def check(self, context: Any) -> list[Finding]:
        ...


class Analyzer(ABC):
    def __init__(self) -> None:
        self._rules: list[Rule] = self._default_rules()

    def register_rule(self, rule: Rule) -> "Analyzer":
        self._rules.append(rule)
        return self

    def unregister_rule(self, rule_id: str) -> "Analyzer":
        self._rules = [r for r in self._rules if r.id != rule_id]
        return self

    @abstractmethod
    def _default_rules(self) -> list[Rule]:
        ...

    @abstractmethod
    def analyze(self, content: str, source: str = "unknown") -> AnalysisReport:
        ...
