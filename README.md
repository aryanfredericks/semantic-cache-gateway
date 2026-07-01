## Vision

Most applications call an LLM provider directly, which means paying full inference cost and latency for every request — even when the same or a semantically equivalent question has already been asked. The **Semantic Cache Gateway** is an intermediary infrastructure layer, modeled on the kind of internal AI platform teams build when running LLM-powered products at scale: every request flows through it, and it's responsible for reducing cost, improving latency, and keeping the system available even when an upstream provider fails.

This is infrastructure, not an application — the interesting part isn't a chat UI, it's what happens between the client and the model: semantic caching, provider abstraction, resilience, and observability.

**Planned capabilities** (beyond what's implemented today):
- Intelligent model routing — selecting a model based on prompt complexity rather than always calling the same one
- Full provider abstraction with additional backends (e.g. a local model via vLLM/Ollama) alongside Groq
- API key–based authentication and per-user usage tracking
- Cost analytics — quantifying tokens and spend saved by cache hits
- Metrics and dashboards (Prometheus/Grafana) for cache hit ratio, provider latency, and failure rates
- Kubernetes-ready, horizontally scalable deployment

The project is being built incrementally; the sections below reflect what's implemented and working right now.


# Semantic Cache Gateway

A FastAPI gateway that sits in front of an LLM and serves semantically similar queries from a vector cache instead of hitting the model every time. Reduces latency and API costs for workloads with repetitive or paraphrased prompts.

## How it works

1. **Rate limit** — each client IP is allowed 10 requests per 60-second window (Redis-backed).
2. **Normalize** — the query is whitespace-collapsed before embedding.
3. **Embed** — the normalized query is encoded with `BAAI/bge-small-en-v1.5` (384-dimensional vectors, cosine similarity).
4. **Cache lookup** — Qdrant is searched for semantically similar prompts. If the top match scores ≥ 0.8, the cached response is returned immediately.
5. **LLM call** — on a cache miss, the query is forwarded to Groq (`llama-3.3-70b-versatile`) via LangChain. If Groq is unreachable, a static fallback response is returned.
6. **Cache store** — the new prompt/response pair is upserted into Qdrant with a 24-hour TTL.

```
Client → [Rate Limiter] → [Normalizer] → [Embedder]
                                              ↓
                                     [Qdrant Vector Search]
                                      ↙ hit        ↘ miss
                              Cached Response    [Groq / Fallback]
                                                       ↓
                                              [Store in Qdrant]
```

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/query` | Submit a query. Returns `{ message, cache_hit }`. |
| `GET` | `/health` | Liveness check. Returns `{ status: "healthy" }`. |

**Request body:**
```json
{ "query": "What is the capital of France?" }
```

**Response:**
```json
{ "message": "Paris is the capital of France.", "cache_hit": false }
```

## Stack

| Layer | Technology |
|-------|-----------|
| API server | FastAPI + Uvicorn |
| LLM provider | Groq (`llama-3.3-70b-versatile`) via LangChain |
| Semantic cache | Qdrant (vector DB, cosine similarity) |
| Embeddings | `sentence-transformers` — `BAAI/bge-small-en-v1.5` |
| Rate limiting | Redis (sliding window counter) |
| Logging | `structlog` — JSON output with request IDs |
| Runtime | Python 3.14, managed with `uv` |

## Getting started

### Prerequisites

- [uv](https://docs.astral.sh/uv/) for Python dependency management
- Docker + Docker Compose for infrastructure services

### 1. Start infrastructure

```bash
docker compose up -d
```

This starts:
- **Postgres** on `:5432`
- **Redis** on `:6379`
- **Qdrant** on `:6333` (HTTP) and `:6334` (gRPC)

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and add your GROQ_API_KEY
```

### 3. Install dependencies and run

```bash
uv sync
uv run uvicorn main:app --reload
```

The API is available at `http://localhost:8000`.

### Run in Docker

```bash
docker build -t semantic-cache-gateway .
docker run --env-file .env -p 8000:8000 semantic-cache-gateway
```

## Configuration

| Setting | Location | Default | Description |
|---------|----------|---------|-------------|
| `GROQ_API_KEY` | `.env` | — | Groq API key (required) |
| `CACHE_THRESHOLD` | `main.py` | `0.8` | Minimum cosine similarity score to serve from cache |
| `REQUESTS_PER_WINDOW` | `configs/redis_config.py` | `10` | Max requests per client IP per window |
| `WINDOW_SECONDS` | `configs/redis_config.py` | `60` | Rate limit window in seconds |
| `DEFAULT_TTL_SECONDS` | `utils/vector_store.py` | `86400` | Cache entry TTL (24 hours) |
| Groq model | `configs/groq_config.py` | `llama-3.3-70b-versatile` | LLM used for cache misses |

## Project structure

```
.
├── main.py                  # FastAPI app, request pipeline
├── providers/
│   ├── base.py              # LLMProvider abstract base class
│   ├── groq_provider.py     # Groq via LangChain
│   └── fallback_provider.py # Static fallback when Groq is down
├── utils/
│   ├── embedder.py          # sentence-transformers wrapper
│   ├── vector_store.py      # Qdrant client (upsert + search + TTL)
│   ├── normalize_query.py   # Whitespace normalization
│   └── logging.py           # structlog configuration
├── configs/
│   ├── groq_config.py       # Groq model settings
│   └── redis_config.py      # Redis rate limiter
├── docker-compose.yaml
└── Dockerfile
```
