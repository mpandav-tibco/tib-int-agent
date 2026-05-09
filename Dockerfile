FROM python:3.11-slim

WORKDIR /app

# Install system deps for reportlab PDF generation
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Runtime defaults — override via docker-compose environment or -e flags
ENV OLLAMA_BASE_URL=http://host.docker.internal:11434
ENV WEAVIATE_URL=http://weaviate:8080
ENV LLM_PROVIDER=ollama
ENV LLM_MODEL=deepseek-r1:latest
ENV EMBED_MODEL=nomic-embed-text
ENV COLLECTION_NAME=TibcoKnowledge
ENV REQUEST_TIMEOUT=180

# Create data directory so feedback.db and knowledge files persist
RUN mkdir -p /app/data/knowledge

EXPOSE 8000

CMD ["chainlit", "run", "chainlit_app.py", "--host", "0.0.0.0", "--port", "8000"]
