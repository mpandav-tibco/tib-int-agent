from __future__ import annotations

import re

from .base import AnalysisReport, Finding, Severity
from .log_patterns import DEFAULT_PATTERNS, LogPattern


_SEVERITY_MAP = {
    "ERROR":   Severity.ERROR,
    "WARNING": Severity.WARNING,
    "INFO":    Severity.INFO,
}


class LogAnalysisReport(AnalysisReport):
    """
    AnalysisReport subclass for log analysis.

    Stores full LogPattern objects alongside Findings so to_markdown() can
    render the original rich format (root causes + recommended actions per match)
    while the parent Finding fields remain clean for to_html() / to_pdf().
    """

    def __init__(self, source: str) -> None:
        super().__init__(source=source, product="log")
        self._pattern_info: dict[str, LogPattern] = {}  # rule_id → pattern

    def to_markdown(self) -> str:
        lines = [f"## Log Analysis — `{self.source}`\n"]

        if not self.findings and not self.observations:
            lines.append("No known error patterns detected. The log looks clean.")
            return "\n".join(lines)

        if self.findings:
            lines.append(f"**{len(self.findings)} known issue(s) detected:**\n")
            for i, f in enumerate(self.findings, 1):
                pat = self._pattern_info.get(f.rule_id)
                product = pat.product.upper() if pat else "LOG"
                lines.append(f"### {i}. [{f.rule_id}] {f.title}  (`{product}`)")
                lines.append(f"**Matched at {f.location}:** `{f.message[:200]}`\n")
                if pat and pat.root_causes:
                    lines.append("**Root Causes:**")
                    for rc in pat.root_causes:
                        lines.append(f"- {rc}")
                    lines.append("")
                if pat and pat.fixes:
                    lines.append("**Recommended Actions:**")
                    for fix in pat.fixes:
                        lines.append(f"- {fix}")
                    lines.append("")

        if self.observations:
            lines.append("### Unrecognized Error Lines\n")
            lines.append(
                "These ERROR/FATAL lines did not match known patterns — "
                "share full context for deeper diagnosis:"
            )
            for obs in self.observations[:10]:
                lines.append(f"- `{obs[:180]}`")
            if len(self.observations) > 10:
                lines.append(f"- ... and {len(self.observations) - 10} more")

        return "\n".join(lines)


class LogAnalyzer:
    """
    Analyzes BW / Flogo pod logs against a registry of known error patterns.
    Returns a LogAnalysisReport (subclass of AnalysisReport) so to_html()
    and to_pdf() from the report generator work without special-casing.

    Extend at runtime:
        analyzer = LogAnalyzer()
        analyzer.register_pattern(LogPattern(...))
    """

    def __init__(self) -> None:
        self._patterns: list[LogPattern] = list(DEFAULT_PATTERNS)

    def register_pattern(self, pattern: LogPattern) -> "LogAnalyzer":
        self._patterns.append(pattern)
        return self

    def analyze(self, log_text: str, source: str = "pod.log") -> AnalysisReport:
        report = LogAnalysisReport(source=source)

        if not log_text or not log_text.strip():
            return report

        lines = log_text.splitlines()
        matched_ids: set[str] = set()

        for i, line in enumerate(lines, 1):
            for pattern in self._patterns:
                if pattern.id in matched_ids:
                    continue
                if pattern.regex.search(line):
                    sev = _SEVERITY_MAP.get(pattern.severity, Severity.ERROR)
                    report.findings.append(Finding(
                        rule_id=pattern.id,
                        severity=sev,
                        title=pattern.title,
                        location=f"line {i}",
                        message=line.strip()[:200],
                        recommendation="; ".join(pattern.fixes[:2]),
                        tags=list(pattern.tags) or [pattern.product],
                    ))
                    report._pattern_info[pattern.id] = pattern
                    matched_ids.add(pattern.id)

        report.observations = [
            ln.strip() for ln in lines
            if re.search(r"\bERROR\b|\bFATAL\b|\bException\b|\bpanic\b", ln, re.IGNORECASE)
            and not any(p.regex.search(ln) for p in self._patterns)
        ]
        return report
