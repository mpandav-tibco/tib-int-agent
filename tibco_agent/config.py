import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    ollama_base_url: str
    llm_model: str
    embed_model: str
    weaviate_url: str
    knowledge_path: str
    collection_name: str  # Weaviate class name — must start with uppercase
    request_timeout: float

    def validate(self) -> None:
        Path(self.knowledge_path).mkdir(parents=True, exist_ok=True)

    def apply(self, **kwargs) -> None:
        """Update one or more fields at runtime (used by the Streamlit settings UI)."""
        for k, v in kwargs.items():
            if not hasattr(self, k):
                raise ValueError(f"Unknown setting: {k}")
            setattr(self, k, v)


settings = Settings(
    ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    llm_model=os.getenv("LLM_MODEL", "llama3.1:8b"),
    embed_model=os.getenv("EMBED_MODEL", "nomic-embed-text"),
    weaviate_url=os.getenv("WEAVIATE_URL", "http://localhost:8080"),
    knowledge_path=os.getenv("KNOWLEDGE_PATH", "./data/knowledge"),
    collection_name=os.getenv("COLLECTION_NAME", "TibcoKnowledge"),
    request_timeout=float(os.getenv("REQUEST_TIMEOUT", "180")),
)
