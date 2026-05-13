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
    llm_provider: str    # ollama | openai | anthropic | groq | custom
    llm_api_key: str     # empty for local ollama
    llm_api_base: str    # custom base URL for groq / custom providers
    weaviate_grpc_port: int  # set to 0 to skip gRPC init checks
    vector_db: str       # weaviate | chroma | qdrant | pinecone | pgvector | activespaces
    vector_db_url: str   # DB-specific connection URL (blank = embedded/default)
    vector_db_api_key: str  # required for Pinecone; optional for Qdrant Cloud
    chainlit_image: str  # Docker image used when deploying agents
    deploy_port_start: int  # first host port to try when deploying agent containers

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
    llm_model=os.getenv("LLM_MODEL", "deepseek-r1:latest"),
    embed_model=os.getenv("EMBED_MODEL", "nomic-embed-text"),
    weaviate_url=os.getenv("WEAVIATE_URL", "http://localhost:8080"),
    knowledge_path=os.getenv("KNOWLEDGE_PATH", "./data/knowledge"),
    collection_name=os.getenv("COLLECTION_NAME", "TibcoKnowledge"),
    request_timeout=float(os.getenv("REQUEST_TIMEOUT", "180")),
    llm_provider=os.getenv("LLM_PROVIDER", "ollama"),
    llm_api_key=os.getenv("LLM_API_KEY", ""),
    llm_api_base=os.getenv("LLM_API_BASE", ""),
    weaviate_grpc_port=int(os.getenv("WEAVIATE_GRPC_PORT", "0")),
    vector_db=os.getenv("VECTOR_DB", "weaviate"),
    vector_db_url=os.getenv("VECTOR_DB_URL", os.getenv("WEAVIATE_URL", "http://localhost:8080")),
    vector_db_api_key=os.getenv("VECTOR_DB_API_KEY", ""),
    chainlit_image=os.getenv("CHAINLIT_IMAGE", "tibco-ai-agent-chainlit:latest"),
    deploy_port_start=int(os.getenv("DEPLOY_PORT_START", "8100")),
)
