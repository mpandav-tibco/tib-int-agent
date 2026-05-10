"""AgentForge data model — one Agent per configured domain expert."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Agent:
    id: str                   # UUID4 hex (no dashes)
    name: str                 # Display name  e.g. "Acme Support Bot"
    title: str                # Subtitle  e.g. "Customer Support Specialist"
    description: str          # One-liner shown in the gallery card
    system_prompt: str        # Full system prompt injected before user messages
    collection_name: str      # Weaviate collection  e.g. "Agent_a1b2c3d4"
    llm_provider: str         # ollama | openai | anthropic | groq | custom
    llm_model: str            # e.g. "gpt-4o", "claude-sonnet-4-6", "deepseek-r1:latest"
    llm_api_key: str          # Empty for local Ollama; stored encrypted by the store
    llm_api_base: str         # Custom base URL for groq / ollama-cloud / custom providers
    embed_model: str          # e.g. "nomic-embed-text" — falls back to global default
    created_at: str           # ISO-8601 timestamp
    updated_at: str           # ISO-8601 timestamp
    status: str               # draft | ingesting | ready | error
    last_ingest_chunks: int = 0    # chunk count from last successful ingest
    last_ingest_at: str = ""       # ISO-8601 timestamp of last successful ingest

    # ── helpers ───────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "collection_name": self.collection_name,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "llm_api_key": self.llm_api_key,
            "llm_api_base": self.llm_api_base,
            "embed_model": self.embed_model,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "last_ingest_chunks": self.last_ingest_chunks,
            "last_ingest_at": self.last_ingest_at,
        }

    def to_public_dict(self) -> dict:
        """Like to_dict() but with the API key masked — safe to send to the browser."""
        d = self.to_dict()
        d["llm_api_key"] = "***" if self.llm_api_key else ""
        return d
