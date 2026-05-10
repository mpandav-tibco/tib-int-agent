from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field

from .flogo_analyzer import FlogoAnalyzer
from .bw_analyzer import BWAnalyzer
from .base import AnalysisReport


@dataclass
class ProjectAnalysis:
    """Aggregated result of analyzing a ZIP of TIBCO project files."""
    zip_name: str
    flogo_reports: list[AnalysisReport] = field(default_factory=list)
    bw_reports: list[AnalysisReport] = field(default_factory=list)
    ems_reports: list[AnalysisReport] = field(default_factory=list)
    kube_reports: list[AnalysisReport] = field(default_factory=list)
    log_reports: list[AnalysisReport] = field(default_factory=list)
    cross_flow_issues: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)

    @property
    def total_errors(self) -> int:
        from .base import Severity
        total = 0
        for r in self.flogo_reports + self.bw_reports + self.ems_reports + self.kube_reports + self.log_reports:
            total += sum(1 for f in r.findings if f.severity == Severity.ERROR)
        return total

    @property
    def total_warnings(self) -> int:
        from .base import Severity
        total = 0
        for r in self.flogo_reports + self.bw_reports + self.ems_reports + self.kube_reports + self.log_reports:
            total += sum(1 for f in r.findings if f.severity == Severity.WARNING)
        return total

    def to_markdown(self) -> str:
        lines = [f"## Project Analysis — `{self.zip_name}`\n"]

        counts = []
        if self.flogo_reports:
            counts.append(f"{len(self.flogo_reports)} Flogo app(s)")
        if self.bw_reports:
            counts.append(f"{len(self.bw_reports)} BW process(es)")
        if self.ems_reports:
            counts.append(f"{len(self.ems_reports)} EMS config(s)")
        if self.kube_reports:
            counts.append(f"{len(self.kube_reports)} Kubernetes manifest(s)")
        if self.log_reports:
            counts.append(f"{len(self.log_reports)} log file(s)")

        lines.append(
            f"**Files analyzed:** {', '.join(counts) or 'none'}  \n"
            f"**Total:** {self.total_errors} error(s), {self.total_warnings} warning(s)\n"
        )

        if self.cross_flow_issues:
            lines.append("### Cross-File Issues\n")
            for issue in self.cross_flow_issues:
                lines.append(f"- {issue}")
            lines.append("")

        if self.skipped_files:
            lines.append("### Skipped Files\n")
            for f in self.skipped_files:
                lines.append(f"- `{f}` — unsupported type or parse error")
            lines.append("")

        for report in self.flogo_reports:
            lines.append(report.to_markdown())
            lines.append("")

        for report in self.bw_reports:
            bw_analyzer = BWAnalyzer()
            lines.append(bw_analyzer.report_to_markdown(report))
            lines.append("")

        for report in self.ems_reports:
            lines.append(report.to_markdown())
            lines.append("")

        for report in self.kube_reports:
            lines.append(report.to_markdown())
            lines.append("")

        for report in self.log_reports:
            lines.append(report.to_markdown())
            lines.append("")

        return "\n".join(lines)


def _cross_flow_flogo(reports: list[AnalysisReport]) -> list[str]:
    """Detect cross-file issues in a set of Flogo reports."""
    issues: list[str] = []

    all_flows: dict[str, str] = {}  # flow_name -> source file
    for report in reports:
        for ep in report.overview.get("endpoints", []):
            flow = ep.get("flow", "")
            if flow:
                if flow in all_flows:
                    issues.append(
                        f"Duplicate flow name `{flow}` in `{report.source}` "
                        f"and `{all_flows[flow]}` — may cause routing conflicts."
                    )
                else:
                    all_flows[flow] = report.source

    missing_eh = [r.source for r in reports
                  if any(f.rule_id == "FLOGO-001" for f in r.findings)]
    if missing_eh and len(missing_eh) != len(reports):
        issues.append(
            f"Inconsistent error handling: {len(missing_eh)} of {len(reports)} app(s) "
            f"are missing error handlers ({', '.join(missing_eh[:3])}"
            + (f" and {len(missing_eh)-3} more" if len(missing_eh) > 3 else "") + ")."
        )

    return issues


def analyze_zip(zip_bytes: bytes, zip_name: str = "project.zip") -> ProjectAnalysis:
    """
    Extract and analyze all supported files inside a ZIP archive.
    Supports: .flogo, .bwp, .conf (EMS), .yaml/.yml (Kubernetes), .log/.txt (pod logs).
    Returns a ProjectAnalysis with per-file reports and cross-file issues.
    """
    result = ProjectAnalysis(zip_name=zip_name)
    flogo_analyzer = FlogoAnalyzer()
    bw_analyzer    = BWAnalyzer()

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                if name.startswith("__") or "/." in name or name.endswith("/"):
                    continue

                lower = name.lower()
                try:
                    content_bytes = zf.read(name)
                    content = content_bytes.decode("utf-8", errors="replace")
                except Exception:
                    result.skipped_files.append(name)
                    continue

                short_name = name.split("/")[-1]

                if lower.endswith(".flogo"):
                    report = flogo_analyzer.analyze(content, source=short_name)
                    result.flogo_reports.append(report)

                elif lower.endswith(".bwp"):
                    report = bw_analyzer.analyze(content, source=short_name)
                    result.bw_reports.append(report)

                elif lower.endswith(".conf") or short_name.lower() == "tibemsd.conf":
                    from .ems_analyzer import EMSAnalyzer
                    report = EMSAnalyzer().analyze(content, source=short_name)
                    result.ems_reports.append(report)

                elif lower.endswith((".yaml", ".yml")):
                    from .kube_analyzer import KubeAnalyzer
                    report = KubeAnalyzer().analyze(content, source=short_name)
                    result.kube_reports.append(report)

                elif lower.endswith((".log", ".txt")):
                    from .log_analyzer import LogAnalyzer
                    report = LogAnalyzer().analyze(content, source=short_name)
                    result.log_reports.append(report)

                # Other file types (jars, class files, etc.) silently skipped

    except zipfile.BadZipFile:
        result.skipped_files.append(f"{zip_name} — not a valid ZIP file")
        return result

    result.cross_flow_issues = _cross_flow_flogo(result.flogo_reports)
    return result
