"""Per-rule unit tests for all BW analyzer rules.

Each rule has a *_fires test (bad input → finding) and a *_clean test (good input → no finding).
Tests do NOT require Weaviate or Ollama.
"""
from __future__ import annotations

import pytest

from tibco_agent.analyzers.bw_analyzer import BWAnalyzer
from .fixtures import make_bw_process


def _analyze(xml: str, fname: str = "test.bwp") -> object:
    return BWAnalyzer().analyze(xml, source=fname)


def _analyze_multi(files: dict) -> object:
    return BWAnalyzer().analyze_multi(files)


def _ids(report) -> set[str]:
    return {f.rule_id for f in report.findings}


# ── BWP-001: BWMissingFaultHandlerRule ───────────────────────────────────────

def test_bwp001_fires():
    xml = make_bw_process(has_fault_handler=False)
    report = _analyze(xml)
    assert "BWP-001" in _ids(report)
    f = next(x for x in report.findings if x.rule_id == "BWP-001")
    assert f.severity.value == "ERROR"


def test_bwp001_clean():
    xml = make_bw_process(has_fault_handler=True)
    report = _analyze(xml)
    assert "BWP-001" not in _ids(report)


# ── BWP-002: BWHardcodedUrlRule ──────────────────────────────────────────────

def test_bwp002_fires():
    extra = "<url>http://api.example.com/v1/orders</url>"
    xml = make_bw_process(extra_xml=extra)
    report = _analyze(xml)
    assert "BWP-002" in _ids(report)
    f = next(x for x in report.findings if x.rule_id == "BWP-002")
    assert f.severity.value == "WARNING"


def test_bwp002_clean():
    extra = "<url>%%p_ServiceURL%%</url>"
    xml = make_bw_process(extra_xml=extra)
    report = _analyze(xml)
    assert "BWP-002" not in _ids(report)


# ── BWP-003: BWPlainPasswordRule ─────────────────────────────────────────────

def test_bwp003_fires():
    extra = "<password>mysecretpassword</password>"
    xml = make_bw_process(extra_xml=extra)
    report = _analyze(xml)
    assert "BWP-003" in _ids(report)
    f = next(x for x in report.findings if x.rule_id == "BWP-003")
    assert f.severity.value == "ERROR"


def test_bwp003_clean():
    extra = "<password>{ENCRYPT}YWJj</password>"
    xml = make_bw_process(extra_xml=extra)
    report = _analyze(xml)
    assert "BWP-003" not in _ids(report)


# ── BWP-004: BWMissingRetryRule ──────────────────────────────────────────────

def test_bwp004_fires():
    extra = '<HTTPClientActivity name="callApi" id="callApi"/>'
    xml = make_bw_process(extra_xml=extra)
    report = _analyze(xml)
    assert "BWP-004" in _ids(report)


def test_bwp004_clean():
    # No HTTP activity → rule should not fire
    xml = make_bw_process()
    report = _analyze(xml)
    assert "BWP-004" not in _ids(report)


# ── BWP-005: BWSelectStarRule ────────────────────────────────────────────────

def test_bwp005_fires():
    extra = """
    <JDBCQueryActivity name="q1" id="q1">
      <queryStatement>SELECT * FROM customers</queryStatement>
    </JDBCQueryActivity>
    """
    xml = make_bw_process(extra_xml=extra)
    report = _analyze(xml)
    assert "BWP-005" in _ids(report)
    f = next(x for x in report.findings if x.rule_id == "BWP-005")
    assert f.severity.value == "WARNING"


def test_bwp005_clean():
    extra = """
    <JDBCQueryActivity name="q1" id="q1">
      <queryStatement>SELECT id, name FROM customers</queryStatement>
    </JDBCQueryActivity>
    """
    xml = make_bw_process(extra_xml=extra)
    report = _analyze(xml)
    assert "BWP-005" not in _ids(report)


# ── BWP-006: BWLargeProcessRule ──────────────────────────────────────────────

def test_bwp006_fires():
    # 21 named activities
    acts = [f'<Step name="step{i}" id="step{i}"/>' for i in range(21)]
    xml = make_bw_process(extra_xml="\n".join(acts))
    report = _analyze(xml)
    assert "BWP-006" in _ids(report)


def test_bwp006_clean():
    acts = [f'<Step name="step{i}" id="step{i}"/>' for i in range(5)]
    xml = make_bw_process(extra_xml="\n".join(acts))
    report = _analyze(xml)
    assert "BWP-006" not in _ids(report)


# ── BWP-007: BWLocalhostUrlRule ──────────────────────────────────────────────

def test_bwp007_fires():
    extra = "<url>http://localhost:8080/api</url>"
    xml = make_bw_process(extra_xml=extra)
    report = _analyze(xml)
    assert "BWP-007" in _ids(report)
    f = next(x for x in report.findings if x.rule_id == "BWP-007")
    assert f.severity.value == "ERROR"


def test_bwp007_fires_127():
    extra = "<endpointURI>http://127.0.0.1:9090/svc</endpointURI>"
    xml = make_bw_process(extra_xml=extra)
    report = _analyze(xml)
    assert "BWP-007" in _ids(report)


def test_bwp007_clean():
    extra = "<url>http://myservice.internal/api</url>"
    xml = make_bw_process(extra_xml=extra)
    report = _analyze(xml)
    assert "BWP-007" not in _ids(report)


# ── BWP-008: BWMissingSubstVarRule ───────────────────────────────────────────

def test_bwp008_fires():
    extra = "<host>database.company.com</host>"
    xml = make_bw_process(extra_xml=extra)
    report = _analyze(xml)
    assert "BWP-008" in _ids(report)
    f = next(x for x in report.findings if x.rule_id == "BWP-008")
    assert f.severity.value == "WARNING"


def test_bwp008_fires_port():
    extra = "<port>5432</port>"
    xml = make_bw_process(extra_xml=extra)
    report = _analyze(xml)
    assert "BWP-008" in _ids(report)


def test_bwp008_clean_with_subst():
    extra = "<host>%%p_DBHost%%</host>"
    xml = make_bw_process(extra_xml=extra)
    report = _analyze(xml)
    assert "BWP-008" not in _ids(report)


def test_bwp008_clean_password_skipped():
    # BWP-003 handles passwords; BWP-008 must not double-fire on them
    extra = "<password>hardcoded</password>"
    xml = make_bw_process(extra_xml=extra)
    report = _analyze(xml)
    assert "BWP-008" not in _ids(report)


# ── BWP-P001: BWFaultHandlerPresentRule (positive) ───────────────────────────

def test_bwp_p001_fires():
    xml = make_bw_process(has_fault_handler=True)
    report = _analyze(xml)
    pos_ids = {f.rule_id for f in report.positives}
    assert "BWP-P001" in pos_ids


def test_bwp_p001_clean():
    xml = make_bw_process(has_fault_handler=False)
    report = _analyze(xml)
    pos_ids = {f.rule_id for f in report.positives}
    assert "BWP-P001" not in pos_ids
