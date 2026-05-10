"""Shared test fixture builders for Flogo and BW rule tests."""
from __future__ import annotations
import json


def make_flogo(
    *,
    tasks: list[dict] | None = None,
    connections: list[dict] | None = None,
    triggers: int = 1,
    name: str = "test-app",
    description: str = "Test app",
    version: str = "1.0.0",
    has_error_handler: bool = True,
    flow_name: str = "TestFlow",
) -> str:
    """Minimal valid Flogo JSON. Callers inject problematic tasks."""
    trigger_list = []
    for i in range(triggers):
        trigger_list.append({
            "id": f"trigger_{i}",
            "name": f"trigger_{i}",
            "ref": "#rest",
            "settings": {"port": 8080},
        })

    task_list = tasks or []
    error_handler = {"tasks": []} if has_error_handler else {}

    resource = {
        "id": f"flow:{flow_name}",
        "data": {
            "name": flow_name,
            "tasks": task_list,
            "errorHandler": error_handler,
        },
    }

    app = {
        "name": name,
        "description": description,
        "version": version,
        "appModel": "1.1.1",
        "imports": [],
        "triggers": trigger_list,
        "resources": [resource],
        "connections": connections or [],
    }
    return json.dumps(app)


def make_task(
    *,
    name: str = "task1",
    ref: str = "#rest",
    input: dict | None = None,
    settings: dict | None = None,
    id: str | None = None,
) -> dict:
    """Build a single Flogo task dict."""
    return {
        "id": id or name,
        "name": name,
        "activity": {
            "ref": ref,
            "input": input or {},
            "settings": settings or {},
        },
    }


def make_bw_process(
    *,
    activities: list[str] | None = None,
    has_fault_handler: bool = True,
    proc_name: str = "TestProcess",
    extra_xml: str = "",
) -> str:
    """Minimal valid BW6 XML. Callers inject problematic activities."""
    fault_xml = "<faultHandlers><catchAll/></faultHandlers>" if has_fault_handler else ""
    acts_xml = "\n".join(activities or [])
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<process name="{proc_name}" id="{proc_name}">
  {fault_xml}
  {acts_xml}
  {extra_xml}
</process>"""
