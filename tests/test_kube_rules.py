"""Per-rule unit tests for the Kubernetes manifest analyzer.

Tests do NOT require Weaviate, Ollama, or a live cluster.
"""
from __future__ import annotations

from tibco_agent.analyzers.kube_analyzer import KubeAnalyzer

_MINIMAL_DEPLOY = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
  namespace: production
spec:
  template:
    spec:
      containers:
        - name: app
          image: myimage:1.2.3
          readinessProbe:
            httpGet:
              path: /health
              port: 8080
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
          securityContext:
            runAsNonRoot: true
"""


def _analyze(yaml_str: str):
    return KubeAnalyzer().analyze(yaml_str, source="test.yaml")


def _ids(report) -> set[str]:
    return {f.rule_id for f in report.findings}


def _deploy(overrides: str) -> str:
    return f"""\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
  namespace: production
spec:
  template:
    spec:
      containers:
        - name: app
{overrides}
"""


# ── KUBE-001: Latest image tag ────────────────────────────────────────────────

def test_kube001_fires_latest():
    report = _analyze(_deploy("          image: myimage:latest"))
    assert "KUBE-001" in _ids(report)
    f = next(x for x in report.findings if x.rule_id == "KUBE-001")
    assert f.severity.value == "ERROR"


def test_kube001_fires_no_tag():
    report = _analyze(_deploy("          image: myimage"))
    assert "KUBE-001" in _ids(report)


def test_kube001_clean():
    report = _analyze(_MINIMAL_DEPLOY)
    assert "KUBE-001" not in _ids(report)


# ── KUBE-002: Missing readinessProbe ─────────────────────────────────────────

def test_kube002_fires():
    report = _analyze(_deploy("          image: myimage:1.0"))
    assert "KUBE-002" in _ids(report)
    f = next(x for x in report.findings if x.rule_id == "KUBE-002")
    assert f.severity.value == "ERROR"


def test_kube002_clean():
    report = _analyze(_MINIMAL_DEPLOY)
    assert "KUBE-002" not in _ids(report)


# ── KUBE-003: Missing livenessProbe ──────────────────────────────────────────

def test_kube003_fires():
    yaml = _deploy(
        "          image: myimage:1.0\n"
        "          readinessProbe:\n"
        "            httpGet:\n"
        "              path: /health\n"
        "              port: 8080\n"
    )
    report = _analyze(yaml)
    assert "KUBE-003" in _ids(report)
    f = next(x for x in report.findings if x.rule_id == "KUBE-003")
    assert f.severity.value == "WARNING"


def test_kube003_clean():
    report = _analyze(_MINIMAL_DEPLOY)
    assert "KUBE-003" not in _ids(report)


# ── KUBE-004: Missing resource limits ────────────────────────────────────────

def test_kube004_fires():
    yaml = _deploy(
        "          image: myimage:1.0\n"
        "          resources:\n"
        "            requests:\n"
        "              cpu: 100m\n"
    )
    report = _analyze(yaml)
    assert "KUBE-004" in _ids(report)
    f = next(x for x in report.findings if x.rule_id == "KUBE-004")
    assert f.severity.value == "ERROR"


def test_kube004_clean():
    report = _analyze(_MINIMAL_DEPLOY)
    assert "KUBE-004" not in _ids(report)


# ── KUBE-005: Missing resource requests ──────────────────────────────────────

def test_kube005_fires():
    yaml = _deploy(
        "          image: myimage:1.0\n"
        "          resources:\n"
        "            limits:\n"
        "              cpu: 500m\n"
    )
    report = _analyze(yaml)
    assert "KUBE-005" in _ids(report)
    f = next(x for x in report.findings if x.rule_id == "KUBE-005")
    assert f.severity.value == "WARNING"


def test_kube005_clean():
    report = _analyze(_MINIMAL_DEPLOY)
    assert "KUBE-005" not in _ids(report)


# ── KUBE-006: Runs as root ────────────────────────────────────────────────────

def test_kube006_fires_no_security_context():
    report = _analyze(_deploy("          image: myimage:1.0"))
    assert "KUBE-006" in _ids(report)
    f = next(x for x in report.findings if x.rule_id == "KUBE-006")
    assert f.severity.value == "WARNING"


def test_kube006_fires_run_as_root_false():
    yaml = _deploy(
        "          image: myimage:1.0\n"
        "          securityContext:\n"
        "            runAsNonRoot: false\n"
    )
    report = _analyze(yaml)
    assert "KUBE-006" in _ids(report)


def test_kube006_clean():
    report = _analyze(_MINIMAL_DEPLOY)
    assert "KUBE-006" not in _ids(report)


# ── KUBE-007: No namespace ───────────────────────────────────────────────────

def test_kube007_fires():
    yaml = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
spec:
  template:
    spec:
      containers:
        - name: app
          image: myimage:1.0
"""
    report = _analyze(yaml)
    assert "KUBE-007" in _ids(report)
    f = next(x for x in report.findings if x.rule_id == "KUBE-007")
    assert f.severity.value == "INFO"


def test_kube007_clean():
    report = _analyze(_MINIMAL_DEPLOY)
    assert "KUBE-007" not in _ids(report)


# ── YAML parse error ─────────────────────────────────────────────────────────

def test_parse_error():
    report = _analyze("{ invalid yaml: [\n")
    assert "KUBE-000" in _ids(report)


# ── Multi-doc YAML ───────────────────────────────────────────────────────────

def test_multi_doc():
    yaml = _MINIMAL_DEPLOY + "---\n" + _MINIMAL_DEPLOY.replace("myapp", "myapp2")
    report = _analyze(yaml)
    assert report.overview["manifest_count"] == 2
    assert "KUBE-001" not in _ids(report)


# ── Full good manifest passes all error-level rules ──────────────────────────

def test_full_good_manifest():
    report = _analyze(_MINIMAL_DEPLOY)
    errors = [f for f in report.findings if f.severity.value == "ERROR"]
    assert not errors, f"Unexpected errors: {[f.rule_id for f in errors]}"
