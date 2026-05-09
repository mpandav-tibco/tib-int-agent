from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


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
    findings: list[Finding] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.WARNING)

    def to_markdown(self) -> str:
        lines = [f"## Analysis Report — `{self.source}` ({self.product.upper()})\n"]
        errors = [f for f in self.findings if f.severity == Severity.ERROR]
        warnings = [f for f in self.findings if f.severity == Severity.WARNING]
        infos = [f for f in self.findings if f.severity == Severity.INFO]

        if not self.findings:
            lines.append("No issues found. All configured checks passed.")
        else:
            lines.append(
                f"**Summary:** {len(errors)} error(s), {len(warnings)} warning(s), {len(infos)} info\n"
            )
            for group, label in [(errors, "Errors"), (warnings, "Warnings"), (infos, "Info")]:
                if group:
                    lines.append(f"### {label}\n")
                    for i, f in enumerate(group, 1):
                        lines.append(f"**{i}. [{f.rule_id}] {f.title}**")
                        lines.append(f"- Location: `{f.location}`")
                        lines.append(f"- {f.message}")
                        lines.append(f"- **Fix:** {f.recommendation}\n")

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
