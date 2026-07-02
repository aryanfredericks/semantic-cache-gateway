# Semantic Cache Gateway

A FastAPI gateway that sits in front of an LLM and serves semantically similar queries from a vector cache instead of hitting the model every time. Reduces latency and API costs for workloads with repetitive or paraphrased prompts — with authentication, rate limiting, provider failover, cost tracking, and Prometheus/Grafana observability built in.

## Vision

Most applications call an LLM provider directly, which means paying full inference cost and latency for every request — even when the same or a semantically equivalent question has already been asked. The **Semantic Cache Gateway** is an intermediary infrastructure layer, modeled on the kind of internal AI platform teams build when running LLM-powered products at scale: every request flows through it, and it's responsible for reducing cost, improving latency, and keeping the system available even when an upstream provider fails.

This is infrastructure, not an application — the interesting part isn't a chat UI, it's what happens between the client and the model: semantic caching, provider abstraction, resilience, and observability.

**Planned capabilities** (beyond what's implemented today):
- Intelligent model routing — selecting a model based on prompt complexity rather than always calling the same one
- Kubernetes-ready, horizontally scalable deployment

The project is being built incrementally; the sections below reflect what's implemented and working right now.

## How it works

1. **Authenticate** — every request must include a valid `X-API-Key` header, checked against Postgres. Invalid or missing keys are rejected.
2. **Rate limit** — each API key is allowed 10 requests per 60-second window (Redis-backed token bucket).
3. **Normalize** — the query is whitespace-collapsed before embedding.
4. **Embed** — the normalized query is encoded with `BAAI/bge-small-en-v1.5` (384-dimensional vectors, cosine similarity).
5. **Cache lookup** — Qdrant is searched for semantically similar prompts. If the top non-expired match scores ≥ 0.8, the cached response is returned immediately — no LLM call, no cost.
6. **LLM call (on cache miss)** — the query is forwarded to Groq (`llama-3.3-70b-versatile`) via LangChain, behind an `LLMProvider` interface. If Groq fails or is unreachable, the gateway automatically fails over to a local Ollama model (`qwen2.5:7b`) instead of erroring out.
7. **Cache store** — the new prompt/response pair, along with real token usage (from Groq; Ollama's usage metadata is best-effort), is upserted into Qdrant with a 24-hour TTL.
8. **Cost logging** — every request (hit or miss) is logged to Postgres with token counts, so cache savings are measurable, not estimated.
9. **Metrics** — cache hits/misses, provider calls, and rate-limit rejections are tracked as Prometheus counters and exposed at `/metrics`, alongside auto-instrumented request latency/throughput.

```
Client
  │
  ▼
[API Key Auth] ──✗──▶ 401
  │ ✓
  ▼
[Rate Limiter] ──✗──▶ 429
  │ ✓
  ▼
[Normalize] → [Embed]
                 │
                 ▼
       [Qdrant Vector Search]
        ↙ hit              ↘ miss
[Cached Response]      [Groq] ──fails──▶ [Ollama (local)]
        │                    │                   │
        │                    ▼                   │
        │            [Store in Qdrant]            │
        │                    │                    │
        ▼                    ▼                    ▼
              [Log request + tokens → Postgres]
                             │
                             ▼
                        Response
```

Every request also increments Prometheus counters (`cache_hits_total`, `cache_misses_total`, `provider_calls_total`, `rate_limit_rejections_total`), scraped by Prometheus and visualized in Grafana.

## API

| Method | Path | Auth required | Description |
|--------|------|----------------|-------------|
| `POST` | `/query` | Yes (`X-API-Key`) | Submit a query. Returns `{ message, cache_hit }`. |
| `GET` | `/stats` | No | Aggregate usage: total requests, cache hit rate, tokens saved via cache. |
| `GET` | `/health` | No | Liveness check. Returns `{ status: "healthy" }`. |
| `GET` | `/metrics` | No | Prometheus metrics (cache hits/misses, provider calls, rate-limit rejections, request latency). |

**Request:**
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"query": "What is the capital of France?"}'
```

**Response:**
```json
{ "message": "The capital of France is Paris.", "cache_hit": false }
```

**`/stats` response:**
```json
{
  "total_requests": 6,
  "cache_hits": 3,
  "cache_hit_rate": 0.5,
  "tokens_saved_via_cache": 58
}
```

## Stack

| Layer | Technology |
|-------|-----------|
| API server | FastAPI + Uvicorn |
| LLM provider | Groq (`llama-3.3-70b-versatile`) via LangChain, behind an `LLMProvider` interface |
| Failover | Local Ollama model (`qwen2.5:7b` via `langchain-ollama`), auto-triggered on Groq failure |
| Semantic cache | Qdrant (vector DB, cosine similarity, TTL-based expiry) |
| Embeddings | `sentence-transformers` — `BAAI/bge-small-en-v1.5` |
| Auth | API keys stored in Postgres, checked per request |
| Rate limiting | Redis (fixed-window counter, keyed by API key) |
| Cost analytics | Postgres request log with real token counts from Groq's `usage_metadata` |
| Metrics & dashboards | Prometheus (`prometheus-fastapi-instrumentator` + custom counters) + Grafana |
| Logging | `structlog` — JSON output with request IDs |
| Runtime | Python 3.14, managed with `uv` |

## Getting started

### Prerequisites

- [uv](https://docs.astral.sh/uv/) for Python dependency management
- Docker + Docker Compose for infrastructure services
- [Ollama](https://ollama.com/) running locally with the `qwen2.5:7b` model pulled (`ollama pull qwen2.5:7b`) — used as the failover provider if Groq is unreachable

### 1. Start infrastructure

```bash
docker compose up -d
```

This starts:
- **Postgres** on `:5432` — API keys and request logs
- **Redis** on `:6379` — rate limiting
- **Qdrant** on `:6333` (HTTP) and `:6334` (gRPC) — semantic cache
- **Prometheus** on `:9090` — scrapes gateway metrics from `/metrics` (config in `prometheus.yml`)
- **Grafana** on `:3000` — dashboards (default login `admin` / `admin`; import `grafana/dashboards/gateway_overview.json` manually, no auto-provisioning yet)

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

### 4. Seed a test API key

Every request to `/query` requires a valid `X-API-Key`. Seed one:

```bash
uv run seed_key.py
```

This inserts a test key (`dev-test-key-123` by default — see `seed_key.py`) into Postgres. Without this step, all requests return `401`.

### Run in Docker

```bash
docker build -t semantic-cache-gateway .
docker run --env-file .env -p 8000:8000 semantic-cache-gateway
```

> Note: when running the app itself in Docker, update `POSTGRES_URL`/Redis/Qdrant hosts to use Docker service names (e.g. `postgres`, `redis`, `qdrant`) rather than `localhost`. See `configs/` for how these are read from environment variables.

## Configuration

| Setting | Location | Default | Description |
|---------|----------|---------|-------------|
| `GROQ_API_KEY` | `.env` | — | Groq API key (required) |
| `POSTGRES_URL` | `.env` / `configs/postgres_config.py` | `postgresql+asyncpg://gateway:gateway@localhost:5432/gateway` | Postgres connection string |
| `CACHE_THRESHOLD` | `main.py` | `0.8` | Minimum cosine similarity score to serve from cache |
| `REQUESTS_PER_WINDOW` | `configs/redis_config.py` | `10` | Max requests per API key per window |
| `WINDOW_SECONDS` | `configs/redis_config.py` | `60` | Rate limit window in seconds |
| `DEFAULT_TTL_SECONDS` | `utils/vector_store.py` | `86400` | Cache entry TTL (24 hours) |
| Groq model | `configs/groq_config.py` | `llama-3.3-70b-versatile` | LLM used for cache misses |
| Ollama model / base URL | `providers/ollama_provider.py` | `qwen2.5:7b` / `http://localhost:11434` | Local failover model, used if Groq fails |
| Prometheus scrape target | `prometheus.yml` | `host-gateway:8000` | Assumes the gateway runs on the host (not in `docker-compose`); relies on the `extra_hosts: host-gateway` mapping |
| Cost rates | `configs/cost_config.py` | placeholder values | Per-token cost estimates — update to match Groq's published pricing |

**Known simplification:** cost estimates use flat input/output token rates and don't currently account for provider-side prompt caching (`cache_read` tokens in Groq's usage metadata), which is typically billed at a lower rate.

## Project structure

```
.
├── main.py                    # FastAPI app, request pipeline, Prometheus counters
├── seed_key.py                # One-off script to seed a test API key
├── providers/
│   ├── base.py                 # LLMProvider abstract interface
│   ├── groq_provider.py        # Groq via LangChain (async)
│   ├── ollama_provider.py      # Local Ollama model, used as failover
│   └── fallback_provider.py    # Static text fallback — legacy, no longer wired in (superseded by ollama_provider.py)
├── models/
│   ├── api_key.py              # SQLModel: api_keys table
│   └── request_logs.py         # SQLModel: request_logs table (cost analytics)
├── utils/
│   ├── auth.py                   # API key verification dependency
│   ├── embedder.py               # sentence-transformers wrapper
│   ├── vector_store.py           # Qdrant client (upsert + search + TTL)
│   ├── normalize_query.py        # Whitespace normalization
│   ├── db.py                     # Postgres async engine + session
│   └── logging.py                # structlog configuration
├── configs/
│   ├── groq_config.py           # Groq model settings
│   ├── postgres_config.py       # Postgres connection string
│   ├── redis_config.py          # Redis-backed fixed-window rate limiter (RateLimiter)
│   └── cost_config.py           # Token cost estimation rates
├── grafana/
│   └── dashboards/
│       └── gateway_overview.json  # Cache hit ratio, request rate, latency panels (manual import)
├── prometheus.yml             # Scrape config for the gateway's /metrics endpoint
├── docker-compose.yaml        # Postgres, Redis, Qdrant, Prometheus, Grafana
└── Dockerfile
```