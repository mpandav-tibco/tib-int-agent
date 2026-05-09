from __future__ import annotations

import re
from dataclasses import dataclass, field

from .log_patterns import DEFAULT_PATTERNS, LogPattern


@dataclass
class LogMatch:
    pattern: LogPattern
    matched_line: str
    line_number: int


@dataclass
class LogReport:
    source: str
    matches: list[LogMatch] = field(default_factory=list)
    unmatched_errors: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [f"## Log Analysis — `{self.source}`\n"]

        if not self.matches and not self.unmatched_errors:
            lines.append("No known error patterns detected. The log looks clean.")
            return "\n".join(lines)

        if self.matches:
            lines.append(f"**{len(self.matches)} known issue(s) detected:**\n")
            for i, m in enumerate(self.matches, 1):
                p = m.pattern
                lines.append(f"### {i}. [{p.id}] {p.title}  (`{p.product.upper()}`)")
                lines.append(f"**Matched at line {m.line_number}:** `{m.matched_line[:200]}`\n")
                lines.append("**Root Causes:**")
                for rc in p.root_causes:
                    lines.append(f"- {rc}")
                lines.append("\n**Recommended Actions:**")
                for fix in p.fixes:
                    lines.append(f"- {fix}")
                lines.append("")

        if self.unmatched_errors:
            lines.append("### Unrecognized Error Lines\n")
            lines.append("These ERROR/FATAL lines did not match known patterns — share full context for deeper diagnosis:")
            for line in self.unmatched_errors[:10]:
                lines.append(f"- `{line[:180]}`")
            if len(self.unmatched_errors) > 10:
                lines.append(f"- ... and {len(self.unmatched_errors) - 10} more")

        return "\n".join(lines)


class LogAnalyzer:
    """
    Analyzes BW / Flogo pod logs against a registry of known error patterns.

    Extend at runtime:
        analyzer = LogAnalyzer()
        analyzer.register_pattern(LogPattern(...))
    """

    def __init__(self) -> None:
        self._patterns: list[LogPattern] = list(DEFAULT_PATTERNS)

    def register_pattern(self, pattern: LogPattern) -> "LogAnalyzer":
        self._patterns.append(pattern)
        return self

    def analyze(self, log_text: str, source: str = "pod.log") -> LogReport:
        if not log_text or not log_text.strip():
            report = LogReport(source=source)
            return report

        report = LogReport(source=source)
        lines = log_text.splitlines()
        matched_ids: set[str] = set()

        for i, line in enumerate(lines, 1):
            for pattern in self._patterns:
                if pattern.id in matched_ids:
                    continue
                if pattern.regex.search(line):
                    report.matches.append(LogMatch(
                        pattern=pattern,
                        matched_line=line.strip(),
                        line_number=i,
                    ))
                    matched_ids.add(pattern.id)

        unmatched = [
            l.strip() for l in lines
            if re.search(r"\bERROR\b|\bFATAL\b|\bException\b|\bpanic\b", l, re.IGNORECASE)
            and not any(p.regex.search(l) for p in self._patterns)
        ]
        report.unmatched_errors = unmatched
        return report
