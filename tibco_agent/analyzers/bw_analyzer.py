from __future__ import annotations

import xml.etree.ElementTree as ET

from .base import Analyzer, AnalysisReport, Finding, Rule, Severity
from .bw_rules import (
    BWActivity, BWContext, BWProcess,
    BWMissingFaultHandlerRule, BWHardcodedUrlRule, BWPlainPasswordRule,
    BWMissingRetryRule, BWSelectStarRule, BWLargeProcessRule,
    BWLocalhostUrlRule, BWMissingSubstVarRule,
    BWFaultHandlerPresentRule,
    find_by_local, local_tag, _FAULT_HANDLER_TAGS, _HTTP_ACTIVITY_TAGS,
)

# Tags that represent "leaf" activities (not structural containers)
_CONTAINER_TAGS = frozenset({
    "process", "Process", "sequence", "Sequence", "flow", "Flow",
    "scope", "Scope", "faultHandlers", "catchAll", "catch",
    "compensationHandler", "terminationHandler",
    "forEach", "ForEach", "while", "While", "repeatUntil",
})


def _is_activity(elem) -> bool:
    tag = local_tag(elem)
    return tag not in _CONTAINER_TAGS and not tag.startswith("{")


def _parse_process(root: ET.Element, file_name: str) -> BWProcess:
    """Extract structured data from a BW6 .bwp XML root element."""
    # Process name: from name attribute or file name
    proc_name = root.get("name") or root.get("id") or file_name.replace(".bwp", "")

    # Collect activities — immediate/non-container descendants only
    activities: list[BWActivity] = []
    for elem in root.iter():
        tag = local_tag(elem)
        if tag in _CONTAINER_TAGS:
            continue
        name_attr = elem.get("name") or elem.get("id") or tag
        # Only collect elements that look like palette activities (have a name or id)
        if elem.get("name") or elem.get("id"):
            activities.append(BWActivity(tag=tag, name=name_attr, element=elem))

    # Deduplicate by element identity (iter() visits the same element tree once)
    seen: set[int] = set()
    unique_activities: list[BWActivity] = []
    for act in activities:
        eid = id(act.element)
        if eid not in seen:
            seen.add(eid)
            unique_activities.append(act)

    # Fault handler detection — look for any fault/error handler element
    has_fault = bool(find_by_local(root, *_FAULT_HANDLER_TAGS))

    return BWProcess(
        name=proc_name,
        file_name=file_name,
        activities=unique_activities,
        has_fault_handler=has_fault,
        raw=root,
    )


def _build_overview(ctx: BWContext) -> dict:
    total_acts = sum(len(p.activities) for p in ctx.processes)
    guarded = sum(1 for p in ctx.processes if p.has_fault_handler)
    http_count = sum(
        1 for p in ctx.processes
        for a in p.activities if a.tag in _HTTP_ACTIVITY_TAGS
    )
    return {
        "process_count":  len(ctx.processes),
        "activity_count": total_acts,
        "http_count":     http_count,
        "guarded_count":  guarded,
        "processes":      [p.name for p in ctx.processes],
    }


def _overview_to_markdown(ov: dict, source: str) -> str:
    lines = [
        f"## BW Process Review — `{source}`\n",
        "### Overview\n",
        f"**Processes:** {ov['process_count']}  ",
        f"**Total activities:** {ov['activity_count']}  ",
        f"**HTTP/REST activities:** {ov['http_count']}  ",
        f"**Processes with fault handler:** {ov['guarded_count']} / {ov['process_count']}\n",
    ]
    if ov.get("processes"):
        lines.append("**Processes found:**")
        for name in ov["processes"]:
            lines.append(f"- `{name}`")
        lines.append("")
    return "\n".join(lines)


class BWAnalyzer(Analyzer):
    """
    Analyzes TIBCO BusinessWorks 6 / BWCE `.bwp` XML process files.
    Accepts a single .bwp XML string or a dict of {filename: xml_string} for multi-file.

    Add custom rules:
        analyzer = BWAnalyzer()
        analyzer.register_rule(MyRule())
    """

    def _default_rules(self) -> list[Rule]:
        return [
            BWMissingFaultHandlerRule(),
            BWPlainPasswordRule(),
            BWLocalhostUrlRule(),
            BWHardcodedUrlRule(),
            BWMissingSubstVarRule(),
            BWMissingRetryRule(),
            BWSelectStarRule(),
            BWLargeProcessRule(),
        ]

    def _positive_rules(self) -> list[Rule]:
        return [BWFaultHandlerPresentRule()]

    def analyze(self, content: str, source: str = "unknown.bwp") -> AnalysisReport:
        """Analyze a single BW process XML string."""
        return self.analyze_multi({source: content}, project_name=source)

    def analyze_multi(
        self,
        files: dict[str, str],
        project_name: str = "BW Project",
    ) -> AnalysisReport:
        """Analyze multiple BW process files together."""
        report = AnalysisReport(source=project_name, product="bw")
        processes: list[BWProcess] = []

        for fname, xml_content in files.items():
            try:
                root = ET.fromstring(xml_content)
            except ET.ParseError as e:
                report.findings.append(Finding(
                    rule_id="BWP-000",
                    severity=Severity.ERROR,
                    title="XML Parse Error",
                    location=fname,
                    message=f"Could not parse XML: {e}",
                    recommendation="Validate the .bwp file in TIBCO Business Studio.",
                ))
                continue
            processes.append(_parse_process(root, fname))

        if not processes:
            return report

        ctx = BWContext(processes=processes, raw_files={})
        report.overview = _build_overview(ctx)

        for rule in self._rules:
            report.findings.extend(rule.check(ctx))

        for rule in self._positive_rules():
            report.positives.extend(rule.check(ctx))

        return report

    def report_to_markdown(self, report: AnalysisReport) -> str:
        ov = report.overview
        lines = [_overview_to_markdown(ov, report.source)]

        if report.positives:
            lines.append("### Strengths\n")
            for i, p in enumerate(report.positives, 1):
                lines.append(f"**{i}. [{p.rule_id}] {p.title}**")
                lines.append(f"- {p.message}\n")

        errors   = [f for f in report.findings if f.severity == Severity.ERROR]
        warnings = [f for f in report.findings if f.severity == Severity.WARNING]
        infos    = [f for f in report.findings if f.severity == Severity.INFO]

        if report.findings:
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
            lines.append("### Issues\n\nNo issues found. All checks passed.\n")

        return "\n".join(lines)
