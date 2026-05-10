.PHONY: dev forge-dev forge-build docker-up docker-down install

# ── Development ───────────────────────────────────────────────────────────────

## Start both API server and Chainlit side-by-side (requires two terminals, or use & for background)
dev:
	uvicorn main:app --reload --port 8000 & chainlit run chainlit_app.py --port 8080

## Start the React builder UI dev server with hot-reload (proxies /api to :8000)
forge-dev:
	cd forge && npm run dev

## Build the React SPA production bundle into forge/dist/
forge-build:
	cd forge && npm run build

## Install Python deps
install:
	pip install -r requirements.txt

## Install React deps
forge-install:
	cd forge && npm install

# ── Docker ────────────────────────────────────────────────────────────────────

## Build React SPA then start all Docker services
docker-up: forge-build
	docker compose up --build

## Stop all Docker services
docker-down:
	docker compose down

# ── Testing ───────────────────────────────────────────────────────────────────

## Run tests (no external services needed)
test:
	pytest tests/ test_analyzers.py -v -k "not weaviate and not rag"
