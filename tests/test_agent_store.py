"""Tests for AgentStore CRUD, clone, URL management, and API endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Isolated SQLite DB + file root for each test."""
    db_path = str(tmp_path / "agents.db")
    files_root = str(tmp_path / "agent_files")
    monkeypatch.setenv("AGENTS_DB_PATH", db_path)
    monkeypatch.setenv("AGENT_FILES_ROOT", files_root)
    return db_path, files_root


@pytest.fixture()
def fresh_store(tmp_db):
    """A fresh AgentStore instance pointing at the temp DB."""
    from agent_store.store import AgentStore
    from pathlib import Path
    db_path, _ = tmp_db
    return AgentStore(db_path=Path(db_path))


@pytest.fixture()
def app_client(tmp_db, monkeypatch):
    """FastAPI TestClient with a fresh isolated store."""
    from pathlib import Path
    db_path, files_root = tmp_db

    from agent_store.store import AgentStore
    fresh = AgentStore(db_path=Path(db_path))

    # Patch the singleton used by the router and main.py lifespan
    import agent_store.router as _router
    import main as _main
    monkeypatch.setattr(_router, "store", fresh)
    monkeypatch.setattr(_main, "store", fresh)
    monkeypatch.setattr(_router, "_FILES_ROOT", Path(files_root))

    return TestClient(_main.app)


# ── Store unit tests ──────────────────────────────────────────────────────────

class TestAgentStoreBasic:
    def test_create_and_get(self, fresh_store):
        a = fresh_store.create(name="alpha", title="Alpha Agent")
        assert a.id
        assert a.name == "alpha"
        assert a.status == "draft"
        assert a.collection_name.startswith("Agent_")

        got = fresh_store.get(a.id)
        assert got is not None
        assert got.name == "alpha"

    def test_list_all(self, fresh_store):
        fresh_store.create(name="a1")
        fresh_store.create(name="a2")
        agents = fresh_store.list_all()
        names = {a.name for a in agents}
        assert {"a1", "a2"}.issubset(names)

    def test_update(self, fresh_store):
        a = fresh_store.create(name="beta")
        updated = fresh_store.update(a.id, title="New Title", llm_model="gpt-4o")
        assert updated.title == "New Title"
        assert updated.llm_model == "gpt-4o"
        # Name unchanged
        assert updated.name == "beta"

    def test_delete(self, fresh_store):
        a = fresh_store.create(name="gamma")
        fresh_store.delete(a.id)
        assert fresh_store.get(a.id) is None

    def test_set_status(self, fresh_store):
        a = fresh_store.create(name="delta")
        fresh_store.set_status(a.id, "ingesting")
        assert fresh_store.get(a.id).status == "ingesting"

    def test_record_ingest(self, fresh_store):
        a = fresh_store.create(name="epsilon")
        fresh_store.record_ingest(a.id, chunks=42)
        got = fresh_store.get(a.id)
        assert got.status == "ready"
        assert got.last_ingest_chunks == 42
        assert got.last_ingest_at  # non-empty timestamp

    def test_list_ingesting(self, fresh_store):
        a1 = fresh_store.create(name="i1")
        a2 = fresh_store.create(name="i2")
        fresh_store.set_status(a1.id, "ingesting")
        fresh_store.set_status(a2.id, "ready")
        ingesting = fresh_store.list_ingesting()
        ingesting_ids = {a.id for a in ingesting}
        assert a1.id in ingesting_ids
        assert a2.id not in ingesting_ids


class TestAgentStoreClone:
    def test_clone_basic(self, fresh_store):
        original = fresh_store.create(
            name="source",
            title="Source Agent",
            system_prompt="Be helpful.",
            llm_provider="openai",
            llm_model="gpt-4o",
        )
        cloned = fresh_store.clone(original.id)
        assert cloned.id != original.id
        assert cloned.name == "Copy of source"
        assert cloned.title == original.title
        assert cloned.system_prompt == original.system_prompt
        assert cloned.llm_provider == original.llm_provider
        assert cloned.status == "draft"
        assert cloned.collection_name != original.collection_name

    def test_clone_missing_raises(self, fresh_store):
        with pytest.raises(KeyError):
            fresh_store.clone("nonexistent-id")

    def test_clone_is_independent(self, fresh_store):
        original = fresh_store.create(name="orig")
        cloned = fresh_store.clone(original.id)
        fresh_store.update(original.id, title="Changed Original")
        assert fresh_store.get(cloned.id).title != "Changed Original"


class TestAgentStoreUrls:
    def test_add_and_list_urls(self, fresh_store):
        a = fresh_store.create(name="url-agent")
        fresh_store.add_url(a.id, "https://example.com", label="Example")
        fresh_store.add_url(a.id, "https://docs.example.com")
        urls = fresh_store.list_urls(a.id)
        assert len(urls) == 2
        assert any(u["url"] == "https://example.com" for u in urls)

    def test_delete_url(self, fresh_store):
        a = fresh_store.create(name="url-del")
        url_row = fresh_store.add_url(a.id, "https://todelete.com")
        fresh_store.delete_url(url_row["id"])
        assert fresh_store.list_urls(a.id) == []

    def test_get_urls_for_agent(self, fresh_store):
        a = fresh_store.create(name="url-fetch")
        fresh_store.add_url(a.id, "https://one.com")
        fresh_store.add_url(a.id, "https://two.com")
        urls = fresh_store.get_urls_for_agent(a.id)
        assert set(urls) == {"https://one.com", "https://two.com"}

    def test_urls_cascade_delete(self, fresh_store):
        a = fresh_store.create(name="url-cascade")
        fresh_store.add_url(a.id, "https://cascade.com")
        fresh_store.delete(a.id)
        # URLs should be gone (FK cascade)
        # Re-create store connection to check
        assert fresh_store.list_urls(a.id) == []


# ── API endpoint tests ────────────────────────────────────────────────────────

class TestAgentsAPI:
    def test_list_empty(self, app_client):
        r = app_client.get("/api/agents/")
        assert r.status_code == 200
        assert r.json() == []

    def test_create_agent(self, app_client):
        r = app_client.post("/api/agents/", json={"name": "test-agent", "title": "Test"})
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "test-agent"
        assert data["status"] == "draft"
        assert "id" in data
        assert data["llm_api_key"] == ""  # empty when none provided (masked in public dict)

    def test_get_agent(self, app_client):
        created = app_client.post("/api/agents/", json={"name": "get-me"}).json()
        r = app_client.get(f"/api/agents/{created['id']}")
        assert r.status_code == 200
        assert r.json()["id"] == created["id"]

    def test_get_agent_not_found(self, app_client):
        r = app_client.get("/api/agents/nonexistent")
        assert r.status_code == 404

    def test_update_agent(self, app_client):
        created = app_client.post("/api/agents/", json={"name": "upd-agent"}).json()
        r = app_client.patch(
            f"/api/agents/{created['id']}",
            json={"title": "Updated Title"},
        )
        assert r.status_code == 200
        assert r.json()["title"] == "Updated Title"

    def test_delete_agent(self, app_client):
        created = app_client.post("/api/agents/", json={"name": "del-me"}).json()
        r = app_client.delete(f"/api/agents/{created['id']}")
        assert r.status_code == 204
        assert app_client.get(f"/api/agents/{created['id']}").status_code == 404

    def test_clone_agent(self, app_client):
        created = app_client.post(
            "/api/agents/",
            json={"name": "original", "system_prompt": "Hello!"},
        ).json()
        r = app_client.post(f"/api/agents/{created['id']}/clone")
        assert r.status_code == 201
        cloned = r.json()
        assert cloned["name"] == "Copy of original"
        assert cloned["system_prompt"] == "Hello!"
        assert cloned["id"] != created["id"]
        assert cloned["status"] == "draft"

    def test_clone_not_found(self, app_client):
        r = app_client.post("/api/agents/does-not-exist/clone")
        assert r.status_code == 404


class TestUrlsAPI:
    def _create(self, client):
        return client.post("/api/agents/", json={"name": "url-test"}).json()

    def test_add_url(self, app_client):
        a = self._create(app_client)
        r = app_client.post(
            f"/api/agents/{a['id']}/urls",
            json={"url": "https://example.com", "label": "Docs"},
        )
        assert r.status_code == 201
        assert r.json()["url"] == "https://example.com"

    def test_add_invalid_url(self, app_client):
        a = self._create(app_client)
        r = app_client.post(
            f"/api/agents/{a['id']}/urls",
            json={"url": "not-a-url"},
        )
        assert r.status_code == 400

    def test_list_urls(self, app_client):
        a = self._create(app_client)
        app_client.post(f"/api/agents/{a['id']}/urls", json={"url": "https://one.com"})
        app_client.post(f"/api/agents/{a['id']}/urls", json={"url": "https://two.com"})
        r = app_client.get(f"/api/agents/{a['id']}/urls")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_delete_url(self, app_client):
        a = self._create(app_client)
        url = app_client.post(
            f"/api/agents/{a['id']}/urls",
            json={"url": "https://del.com"},
        ).json()
        r = app_client.delete(f"/api/agents/{a['id']}/urls/{url['id']}")
        assert r.status_code == 204
        remaining = app_client.get(f"/api/agents/{a['id']}/urls").json()
        assert remaining == []


class TestStatusAPI:
    def test_status_default(self, app_client):
        a = app_client.post("/api/agents/", json={"name": "stat-test"}).json()
        r = app_client.get(f"/api/agents/{a['id']}/status")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "draft"
        assert data["chunks"] == 0

    def test_status_not_found(self, app_client):
        r = app_client.get("/api/agents/missing/status")
        assert r.status_code == 404


class TestIngestAPI:
    def test_ingest_no_sources(self, app_client):
        a = app_client.post("/api/agents/", json={"name": "no-src"}).json()
        r = app_client.post(f"/api/agents/{a['id']}/ingest")
        assert r.status_code == 400
        assert "No files or URLs" in r.json()["detail"]

    def test_ingest_not_found(self, app_client):
        r = app_client.post("/api/agents/ghost/ingest")
        assert r.status_code == 404
