"""Docker deployment manager — wraps docker CLI via subprocess (no SDK dependency)."""
from __future__ import annotations

import logging
import re
import socket
import subprocess

log = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    return _SLUG_RE.sub("-", text.lower()).strip("-")[:40]


def _pick_port(start: int) -> int:
    """Return the first TCP port >= start that is not in use."""
    for port in range(start, start + 200):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError(f"No free port found in range {start}–{start + 200}")


def deploy(agent, image: str, port_start: int) -> tuple[str, int]:
    """Start a Chainlit container for agent. Returns (container_id, host_port)."""
    port = _pick_port(port_start)
    slug = _slugify(agent.name)
    name = f"agent-{slug}-{agent.id[:8]}"

    cmd = [
        "docker", "run", "-d",
        "--name", name,
        "--restart", "unless-stopped",
        "-p", f"{port}:8080",
        "-e", f"AGENT_ID={agent.id}",
        "-e", f"LLM_PROVIDER={agent.llm_provider}",
        "-e", f"LLM_MODEL={agent.llm_model}",
        "-e", f"LLM_API_KEY={agent.llm_api_key}",
        "-e", f"LLM_API_BASE={agent.llm_api_base}",
        "-e", f"EMBED_MODEL={agent.embed_model}",
        "-e", f"VECTOR_DB={agent.vector_db}",
        "-e", f"VECTOR_DB_URL={agent.vector_db_url}",
        "-e", f"VECTOR_DB_API_KEY={agent.vector_db_api_key}",
        "-e", f"COLLECTION_NAME={agent.collection_name}",
        image,
    ]

    log.info("Deploying agent %s on port %d: %s", agent.id, port, name)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"docker run failed (exit {result.returncode})")

    container_id = result.stdout.strip()
    log.info("Container started: %s (port %d)", container_id[:12], port)
    return container_id, port


def undeploy(container_id: str) -> None:
    """Stop and remove a container."""
    for subcmd in (["stop"], ["rm"]):
        result = subprocess.run(
            ["docker"] + subcmd + [container_id],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            log.warning("docker %s %s: %s", subcmd[0], container_id[:12], result.stderr.strip())


def container_status(container_id: str) -> str:
    """Return docker State.Status string, or 'not_found' if container is gone."""
    if not container_id:
        return "not_found"
    result = subprocess.run(
        ["docker", "inspect", "--format={{.State.Status}}", container_id],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        return "not_found"
    return result.stdout.strip() or "not_found"
