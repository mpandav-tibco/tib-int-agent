"""Per-rule unit tests for all Flogo analyzer rules.

Each rule has a *_fires test (bad input → finding) and a *_clean test (good input → no finding).
Tests do NOT require Weaviate or Ollama.
"""
from __future__ import annotations

import pytest

from tibco_agent.analyzers.flogo_analyzer import FlogoAnalyzer
from .fixtures import make_flogo, make_task


def _analyze(content: str) -> object:
    return FlogoAnalyzer().analyze(content)


def _ids(report) -> set[str]:
    return {f.rule_id for f in report.findings}


def _pos_ids(report) -> set[str]:
    return {f.rule_id for f in report.positives}


# ── FLOGO-001: MissingErrorHandlerRule ──────────────────────────────────────

def test_flogo001_fires():
    content = make_flogo(has_error_handler=False)
    report = _analyze(content)
    assert "FLOGO-001" in _ids(report)


def test_flogo001_clean():
    content = make_flogo(has_error_handler=True)
    report = _analyze(content)
    assert "FLOGO-001" not in _ids(report)


# ── FLOGO-002: HttpTimeoutRule ───────────────────────────────────────────────

def test_flogo002_fires():
    task = make_task(ref="github.com/project-flogo/contrib/activity/rest",
                     input={"uri": "http://example.com"})
    content = make_flogo(tasks=[task])
    report = _analyze(content)
    assert "FLOGO-002" in _ids(report)


def test_flogo002_clean():
    task = make_task(ref="github.com/project-flogo/contrib/activity/rest",
                     input={"uri": "http://example.com"},
                     settings={"timeout": 30000})
    content = make_flogo(tasks=[task])
    report = _analyze(content)
    assert "FLOGO-002" not in _ids(report)


# ── FLOGO-003: HttpSslRule ───────────────────────────────────────────────────

def test_flogo003_fires():
    task = make_task(ref="github.com/project-flogo/contrib/activity/rest",
                     input={"uri": "http://example.com"},
                     settings={"sslConfig": {"skipVerify": True}})
    content = make_flogo(tasks=[task])
    report = _analyze(content)
    assert "FLOGO-003" in _ids(report)


def test_flogo003_clean():
    task = make_task(ref="github.com/project-flogo/contrib/activity/rest",
                     input={"uri": "https://example.com"})
    content = make_flogo(tasks=[task])
    report = _analyze(content)
    assert "FLOGO-003" not in _ids(report)


# ── FLOGO-004: SelectStarRule ────────────────────────────────────────────────

def test_flogo004_fires():
    task = make_task(ref="github.com/tibco/wi-contrib/activity/jdbc",
                     input={"query": "SELECT * FROM orders"})
    content = make_flogo(tasks=[task])
    report = _analyze(content)
    assert "FLOGO-004" in _ids(report)


def test_flogo004_clean():
    task = make_task(ref="github.com/tibco/wi-contrib/activity/jdbc",
                     input={"query": "SELECT id, name FROM orders"})
    content = make_flogo(tasks=[task])
    report = _analyze(content)
    assert "FLOGO-004" not in _ids(report)


# ── FLOGO-005: SensitiveLogRule ──────────────────────────────────────────────

def test_flogo005_fires():
    task = make_task(ref="#log",
                     input={"message": "$activity.output.password"})
    content = make_flogo(tasks=[task])
    report = _analyze(content)
    assert "FLOGO-005" in _ids(report)


def test_flogo005_clean():
    task = make_task(ref="#log",
                     input={"message": "Order processed successfully"})
    content = make_flogo(tasks=[task])
    report = _analyze(content)
    assert "FLOGO-005" not in _ids(report)


# ── FLOGO-008: HttpRetryRule ─────────────────────────────────────────────────

def test_flogo008_fires():
    task = make_task(ref="github.com/project-flogo/contrib/activity/rest",
                     input={"uri": "http://example.com"})
    content = make_flogo(tasks=[task])
    report = _analyze(content)
    assert "FLOGO-008" in _ids(report)


def test_flogo008_clean():
    task = make_task(ref="github.com/project-flogo/contrib/activity/rest",
                     input={"uri": "http://example.com"},
                     settings={"numRetries": 3})
    content = make_flogo(tasks=[task])
    report = _analyze(content)
    assert "FLOGO-008" not in _ids(report)


# ── FLOGO-009: HardcodedCredentialRule ──────────────────────────────────────

def test_flogo009_fires():
    task = make_task(ref="github.com/project-flogo/contrib/activity/rest",
                     input={"uri": "http://example.com",
                             "headers": {"Authorization": "Bearer hardcoded_secret_token"}})
    content = make_flogo(tasks=[task])
    report = _analyze(content)
    assert "FLOGO-009" in _ids(report)


def test_flogo009_clean():
    task = make_task(ref="github.com/project-flogo/contrib/activity/rest",
                     input={"uri": "http://example.com"})
    content = make_flogo(tasks=[task])
    report = _analyze(content)
    assert "FLOGO-009" not in _ids(report)


# ── FLOGO-010: LargeFlowRule ─────────────────────────────────────────────────

def test_flogo010_fires():
    tasks = [make_task(name=f"task{i}", ref="#log", id=f"task{i}") for i in range(16)]
    content = make_flogo(tasks=tasks)
    report = _analyze(content)
    assert "FLOGO-010" in _ids(report)


def test_flogo010_clean():
    tasks = [make_task(name=f"task{i}", ref="#log", id=f"task{i}") for i in range(5)]
    content = make_flogo(tasks=tasks)
    report = _analyze(content)
    assert "FLOGO-010" not in _ids(report)


# ── FLOGO-011: LargeLogPayloadRule ──────────────────────────────────────────

def test_flogo011_fires():
    task = make_task(ref="#log",
                     input={"message": "$activity.output.ResponseBody"})
    content = make_flogo(tasks=[task])
    report = _analyze(content)
    assert "FLOGO-011" in _ids(report)


def test_flogo011_clean():
    task = make_task(ref="#log",
                     input={"message": "short message"})
    content = make_flogo(tasks=[task])
    report = _analyze(content)
    assert "FLOGO-011" not in _ids(report)


# ── FLOGO-012: HardcodedUrlRule ──────────────────────────────────────────────

def test_flogo012_fires():
    task = make_task(ref="github.com/project-flogo/contrib/activity/rest",
                     input={"uri": "http://192.168.1.100:8080/api/orders"})
    content = make_flogo(tasks=[task])
    report = _analyze(content)
    assert "FLOGO-012" in _ids(report)


def test_flogo012_clean():
    task = make_task(ref="github.com/project-flogo/contrib/activity/rest",
                     input={"uri": "$property[ServiceURL]"})
    content = make_flogo(tasks=[task])
    report = _analyze(content)
    assert "FLOGO-012" not in _ids(report)


# ── FLOGO-013: MissingPaginationRule ─────────────────────────────────────────

def test_flogo013_fires():
    task = make_task(ref="github.com/tibco/wi-contrib/activity/jdbc",
                     input={"query": "SELECT id, name FROM orders WHERE status='open'"})
    content = make_flogo(tasks=[task])
    report = _analyze(content)
    assert "FLOGO-013" in _ids(report)
    finding = next(f for f in report.findings if f.rule_id == "FLOGO-013")
    assert finding.severity.value == "WARNING"


def test_flogo013_clean():
    task = make_task(ref="github.com/tibco/wi-contrib/activity/jdbc",
                     input={"query": "SELECT id, name FROM orders LIMIT 100"})
    content = make_flogo(tasks=[task])
    report = _analyze(content)
    assert "FLOGO-013" not in _ids(report)


def test_flogo013_clean_non_jdbc():
    task = make_task(ref="#rest",
                     input={"query": "SELECT * FROM whatever"})
    content = make_flogo(tasks=[task])
    report = _analyze(content)
    assert "FLOGO-013" not in _ids(report)


# ── FLOGO-014: DuplicateRestEndpointRule ─────────────────────────────────────

def test_flogo014_fires():
    tasks = [
        make_task(name="call1", id="call1", ref="github.com/project-flogo/contrib/activity/rest",
                  input={"uri": "http://example.com/orders"}),
        make_task(name="call2", id="call2", ref="github.com/project-flogo/contrib/activity/rest",
                  input={"uri": "http://example.com/orders"}),
    ]
    content = make_flogo(tasks=tasks)
    report = _analyze(content)
    assert "FLOGO-014" in _ids(report)
    finding = next(f for f in report.findings if f.rule_id == "FLOGO-014")
    assert finding.severity.value == "INFO"


def test_flogo014_clean():
    tasks = [
        make_task(name="call1", id="call1", ref="github.com/project-flogo/contrib/activity/rest",
                  input={"uri": "http://example.com/orders"}),
        make_task(name="call2", id="call2", ref="github.com/project-flogo/contrib/activity/rest",
                  input={"uri": "http://example.com/products"}),
    ]
    content = make_flogo(tasks=tasks)
    report = _analyze(content)
    assert "FLOGO-014" not in _ids(report)


# ── FLOGO-015: DuplicateConnectorRule ────────────────────────────────────────

def test_flogo015_fires_localhost():
    connections = [{"name": "MyDB", "settings": {"host": "localhost"}}]
    content = make_flogo(connections=connections)
    report = _analyze(content)
    assert "FLOGO-015" in _ids(report)


def test_flogo015_fires_duplicate():
    connections = [
        {"name": "MyDB", "settings": {"host": "db.internal"}},
        {"name": "mydb", "settings": {"host": "db2.internal"}},
    ]
    content = make_flogo(connections=connections)
    report = _analyze(content)
    assert "FLOGO-015" in _ids(report)


def test_flogo015_clean():
    connections = [
        {"name": "PrimaryDB", "settings": {"host": "db.internal"}},
        {"name": "SecondaryDB", "settings": {"host": "db2.internal"}},
    ]
    content = make_flogo(connections=connections)
    report = _analyze(content)
    assert "FLOGO-015" not in _ids(report)


# ── FLOGO-P001: AppDescriptionRule (positive) ────────────────────────────────

def test_flogo_p001_fires():
    content = make_flogo(description="A well-described TIBCO Flogo application")
    report = _analyze(content)
    assert "FLOGO-P001" in _pos_ids(report)


def test_flogo_p001_clean():
    content = make_flogo(description="")
    report = _analyze(content)
    assert "FLOGO-P001" not in _pos_ids(report)
