"""Per-rule unit tests for the EMS config analyzer.

Each rule has a *_fires test (bad config → finding) and a *_clean test (good config → no finding).
Tests do NOT require Weaviate, Ollama, or a live EMS server.
"""
from __future__ import annotations

import pytest

from tibco_agent.analyzers.ems_analyzer import EMSAnalyzer


def _analyze(conf: str, source: str = "tibemsd.conf"):
    return EMSAnalyzer().analyze(conf, source=source)


def _ids(report) -> set[str]:
    return {f.rule_id for f in report.findings}


# ── EMS-001: EMSAuthorizationRule ────────────────────────────────────────────

def test_ems001_fires_disabled():
    conf = "authorization = disabled\n"
    report = _analyze(conf)
    assert "EMS-001" in _ids(report)
    f = next(x for x in report.findings if x.rule_id == "EMS-001")
    assert f.severity.value == "ERROR"


def test_ems001_fires_missing():
    # No authorization line at all → defaults to disabled
    report = _analyze("")
    assert "EMS-001" in _ids(report)


def test_ems001_clean():
    conf = "authorization = enabled\n"
    report = _analyze(conf)
    assert "EMS-001" not in _ids(report)


# ── EMS-002: EMSAdminPasswordRule ────────────────────────────────────────────

def test_ems002_fires_empty():
    conf = "password = \n"
    report = _analyze(conf)
    assert "EMS-002" in _ids(report)
    f = next(x for x in report.findings if x.rule_id == "EMS-002")
    assert f.severity.value == "ERROR"


def test_ems002_fires_plaintext():
    conf = "password = mysecretpassword\n"
    report = _analyze(conf)
    assert "EMS-002" in _ids(report)


def test_ems002_clean_obfuscated():
    conf = "password = {AES}AbCdEfGhIjKlMn==\n"
    report = _analyze(conf)
    assert "EMS-002" not in _ids(report)


def test_ems002_clean_no_key():
    # No password line at all → rule should not fire (key absent means not configured here)
    conf = "authorization = enabled\n"
    report = _analyze(conf)
    assert "EMS-002" not in _ids(report)


# ── EMS-003: EMSSSLIdentityRule ──────────────────────────────────────────────

def test_ems003_fires_missing():
    conf = "authorization = enabled\n"
    report = _analyze(conf)
    assert "EMS-003" in _ids(report)
    f = next(x for x in report.findings if x.rule_id == "EMS-003")
    assert f.severity.value == "WARNING"


def test_ems003_clean():
    conf = (
        "ssl_server_identity = /etc/ems/server.cert.pem\n"
        "ssl_server_key = /etc/ems/server.key.pem\n"
    )
    report = _analyze(conf)
    assert "EMS-003" not in _ids(report)


# ── EMS-004: EMSSSLClientCertRule ────────────────────────────────────────────

def test_ems004_fires():
    conf = "ssl_server_identity = cert.pem\nssl_server_key = key.pem\n"
    report = _analyze(conf)
    assert "EMS-004" in _ids(report)
    f = next(x for x in report.findings if x.rule_id == "EMS-004")
    assert f.severity.value == "WARNING"


def test_ems004_clean():
    conf = (
        "ssl_server_identity = cert.pem\n"
        "ssl_server_key = key.pem\n"
        "ssl_require_client_cert = enabled\n"
    )
    report = _analyze(conf)
    assert "EMS-004" not in _ids(report)


# ── EMS-005: EMSMaxMessageMemoryRule ─────────────────────────────────────────

def test_ems005_fires():
    conf = "authorization = enabled\n"
    report = _analyze(conf)
    assert "EMS-005" in _ids(report)
    f = next(x for x in report.findings if x.rule_id == "EMS-005")
    assert f.severity.value == "WARNING"


def test_ems005_clean():
    conf = "max_msg_memory = 512MB\n"
    report = _analyze(conf)
    assert "EMS-005" not in _ids(report)


# ── EMS-006: EMSFlowControlRule ──────────────────────────────────────────────

def test_ems006_fires():
    conf = "max_msg_memory = 512MB\n"
    report = _analyze(conf)
    assert "EMS-006" in _ids(report)
    f = next(x for x in report.findings if x.rule_id == "EMS-006")
    assert f.severity.value == "WARNING"


def test_ems006_clean():
    conf = "flow_control = enabled\n"
    report = _analyze(conf)
    assert "EMS-006" not in _ids(report)


# ── EMS-007: EMSBackupServerRule ─────────────────────────────────────────────

def test_ems007_fires():
    conf = "authorization = enabled\n"
    report = _analyze(conf)
    assert "EMS-007" in _ids(report)
    f = next(x for x in report.findings if x.rule_id == "EMS-007")
    assert f.severity.value == "INFO"


def test_ems007_clean():
    conf = "backup_server = tcp://ems-backup.internal:7222\n"
    report = _analyze(conf)
    assert "EMS-007" not in _ids(report)


# ── EMS-008: EMSListenPortRule ───────────────────────────────────────────────

def test_ems008_fires_all_interfaces():
    conf = "listen = tcp://0.0.0.0:7222\n"
    report = _analyze(conf)
    assert "EMS-008" in _ids(report)


def test_ems008_fires_missing():
    conf = "authorization = enabled\n"
    report = _analyze(conf)
    assert "EMS-008" in _ids(report)


def test_ems008_clean():
    conf = "listen = tcp://10.0.1.5:7222\n"
    report = _analyze(conf)
    assert "EMS-008" not in _ids(report)


# ── Comment and blank line handling ──────────────────────────────────────────

def test_parser_ignores_comments():
    conf = (
        "# This is a comment\n"
        "authorization = enabled  # inline comment\n"
        "\n"
        "max_msg_memory = 1GB\n"
    )
    report = _analyze(conf)
    assert "EMS-001" not in _ids(report)
    assert "EMS-005" not in _ids(report)


# ── Full "good" config passes all security-level rules ────────────────────────

def test_full_secure_config():
    conf = (
        "authorization = enabled\n"
        "password = {AES}SomeLongObfuscatedString==\n"
        "ssl_server_identity = /etc/ems/server.cert.pem\n"
        "ssl_server_key = /etc/ems/server.key.pem\n"
        "ssl_require_client_cert = enabled\n"
        "max_msg_memory = 2GB\n"
        "flow_control = enabled\n"
        "backup_server = tcp://ems-backup.internal:7222\n"
        "listen = tcp://10.0.1.5:7222\n"
    )
    report = _analyze(conf)
    errors = [f for f in report.findings if f.severity.value == "ERROR"]
    assert not errors, f"Unexpected errors: {[f.rule_id for f in errors]}"
