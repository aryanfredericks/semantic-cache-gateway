# Semantic Cache Gateway

A FastAPI gateway that sits in front of multiple LLMs and serves semantically similar queries from a vector cache instead of hitting a model every time. Built to demonstrate the infrastructure patterns that make LLM-powered products cheaper, faster, and more reliable at scale: semantic caching, complexity-based routing, provider failover, authentication, rate limiting, cost analytics, and live observability.

## Status

Feature-complete for its intended scope. All core infrastructure patterns below are implemented, tested by hand end-to-end, and instrumented. Kubernetes deployment was considered and deliberately left out of scope — see [Future Extensions](#future-extensions).

## Vision

Most applications call an LLM provider directly, which means paying full inference cost and latency for every request — even when the same or a semantically equivalent question has already been asked, and even when a simple question doesn't need the most expensive model available. The **Semantic Cache Gateway** is an intermediary infrastructure layer, modeled on the kind of internal AI platform teams build when running LLM-powered products at scale: every request flows through it, and it's responsible for reducing cost, improving latency, routing intelligently, and keeping the system available even when an upstream provider fails.

This is infrastructure, not an application — the interesting part isn't a chat UI, it's what happens between the client and the model: semantic caching, provider abstraction, complexity-aware routing, resilience, and observability.

## How it works

1. **Authenticate** — every request must include a valid `X-API-Key` header, checked against Postgres. Invalid or missing keys are rejected.
2. **Rate limit** — each API key is allowed 10 requests per 60-second window (Redis-backed fixed-window counter).
3. **Normalize** — the query is whitespace-collapsed before embedding.
4. **Embed** — the normalized query is encoded with `BAAI/bge-small-en-v1.5` (384-dimensional vectors, cosine similarity).
5. **Cache lookup** — Qdrant is searched for semantically similar prompts. If the top non-expired match scores ≥ 0.8, the cached response is returned immediately — no LLM call, no cost, no token spend.
6. **Route (on cache miss)** — a lightweight complexity score is computed from the prompt (length, presence of code/reasoning keywords, multi-part structure). Simple prompts route to a local Ollama model; complex prompts route to Groq.
7. **Call with failover** — the routed provider is tried first; if it fails, the gateway falls through the remaining providers in order rather than erroring out, behind a shared `LLMProvider` interface.
8. **Cache store** — the new prompt/response pair, along with real token usage (from Groq; Ollama's usage metadata is best-effort), is upserted into Qdrant with a 24-hour TTL.
9. **Cost logging** — every request (hit or miss) is logged to Postgres with token counts, so cache savings are measurable, not estimated.
10. **Metrics** — cache hits/misses, provider calls, routing decisions, token usage, and rate-limit rejections are tracked as Prometheus counters and exposed at `/metrics`, alongside auto-instrumented request latency/throughput — all visualized live in Grafana.

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
        ↙ hit                          ↘ miss
[Cached Response]              [Complexity Router]
        │                        ↙            ↘
        │                 [Ollama]          [Groq]
        │                    │  ╲            ╱  │
        │                    │   ╲ (failover)╱   │
        │                    │    ╲        ╱     │
        │                    ▼     ╲      ╱      ▼
        │              [Store in Qdrant]◀────────┘
        │                    │
        ▼                    ▼
        [Log request + tokens → Postgres]
                    │
                    ▼
                Response
```

Every request also increments Prometheus counters (`cache_hits_total`, `cache_misses_total`, `provider_calls_total`, `tokens_used_total`, `tokens_saved_total`, `rate_limit_rejections_total`), scraped by Prometheus and visualized in Grafana.

## Routing

Cache-miss requests are routed by a small complexity score (0–1), computed from:
- Prompt length (weak signal on its own, weighted lightly)
- Presence of code/technical keywords (e.g. "function", "debug", "algorithm")
- Presence of reasoning/analysis keywords (e.g. "explain", "compare", "trade-off")
- Multi-part question structure (lists, "and also", numbered asks)

This is a heuristic, not a learned model — it's deliberately simple and easy to reason about. The routing table (`routing/router.py`) maps complexity thresholds to provider names:

```python
ROUTING_TABLE = [
    (0.0, "ollama"),
    (0.4, "groq"),
]
```

Adding a new tier or provider is additive: implement `LLMProvider`, register it in the provider dict, add one `(threshold, name)` entry. No changes needed to the routing or failover logic itself.

## API

| Method | Path | Auth required | Description |
|--------|------|----------------|-------------|
| `POST` | `/query` | Yes (`X-API-Key`) | Submit a query. Returns `{ message, cache_hit }`. |
| `GET` | `/stats` | No | Aggregate usage: total requests, cache hit rate, tokens saved via cache. |
| `GET` | `/health` | No | Liveness check. Returns `{ status: "healthy" }`. |
| `GET` | `/metrics` | No | Prometheus metrics (cache hits/misses, provider calls, token usage, rate-limit rejections, request latency). |

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
| LLM providers | Groq (`llama-3.3-70b-versatile`) and local Ollama (`qwen2.5:7b`), both behind a shared `LLMProvider` interface |
| Routing | Heuristic complexity scoring → provider selection (`routing/`) |
| Failover | Ordered fallback across providers on call failure |
| Semantic cache | Qdrant (vector DB, cosine similarity, TTL-based expiry) |
| Embeddings | `sentence-transformers` — `BAAI/bge-small-en-v1.5` |
| Auth | API keys stored in Postgres, checked per request |
| Rate limiting | Redis (fixed-window counter, keyed by API key) |
| Cost analytics | Postgres request log with real token counts from provider usage metadata |
| Metrics & dashboards | Prometheus (`prometheus-fastapi-instrumentator` + custom counters) + Grafana |
| Logging | `structlog` — JSON output with request IDs |
| Runtime | Python 3.14, managed with `uv` |

## Getting started

### Prerequisites

- [uv](https://docs.astral.sh/uv/) for Python dependency management
- Docker + Docker Compose for infrastructure services
- [Ollama](https://ollama.com/) running locally with the `qwen2.5:7b` model pulled (`ollama pull qwen2.5:7b`) — used for simple-complexity routing and as Groq's failover

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
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API is available at `http://localhost:8000`. `--host 0.0.0.0` matters if you want Prometheus (running in Docker) to reach the gateway on your host — see the Linux networking note below.

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

> Note: when running the app itself in Docker, update `POSTGRES_URL`/Redis/Qdrant hosts to use Docker service names (e.g. `postgres`, `redis`, `qdrant`) rather than `localhost`.

### Linux networking note (Prometheus scraping the host)

The gateway runs on the host, not in Compose, so Prometheus (in a container) reaches it via Docker Compose's `host-gateway` mapping (`extra_hosts` in `docker-compose.yaml`). On native Linux, a firewall with a default-deny incoming policy (e.g. `ufw`) will silently block this — connections will hang rather than fail immediately. If Prometheus's target shows `DOWN` with a timeout, check your firewall and allow traffic from Docker's Compose-assigned bridge subnet (find it with `docker network inspect <project>_default`, **not** necessarily the default `docker0` subnet — Compose allocates its own per-project subnet):

```bash
sudo ufw allow from <compose-bridge-subnet> to any port 8000
```

This only affects Docker Desktop-less native Linux setups; Mac/Windows Docker Desktop users won't hit this.

## Configuration

| Setting | Location | Default | Description |
|---------|----------|---------|-------------|
| `GROQ_API_KEY` | `.env` | — | Groq API key (required) |
| `POSTGRES_URL` | `.env` / `configs/postgres_config.py` | `postgresql+asyncpg://gateway:gateway@localhost:5432/gateway` | Postgres connection string |
| `CACHE_THRESHOLD` | `main.py` | `0.8` | Minimum cosine similarity score to serve from cache |
| `REQUESTS_PER_WINDOW` | `configs/redis_config.py` | `10` | Max requests per API key per window |
| `WINDOW_SECONDS` | `configs/redis_config.py` | `60` | Rate limit window in seconds |
| `DEFAULT_TTL_SECONDS` | `utils/vector_store.py` | `86400` | Cache entry TTL (24 hours) |
| Groq model | `configs/groq_config.py` | `llama-3.3-70b-versatile` | Used for complex/routed queries and as the general-purpose provider |
| Ollama model / base URL | `providers/ollama_provider.py` | `qwen2.5:7b` / `http://localhost:11434` | Used for simple/routed queries and as Groq's failover |
| `ROUTING_TABLE` / `COMPLEXITY_THRESHOLD` | `routing/router.py` | see file | Maps complexity score thresholds to provider names |
| Prometheus scrape target | `prometheus.yml` | `host-gateway:8000` | Assumes the gateway runs on the host (not in `docker-compose`); relies on the `extra_hosts: host-gateway` mapping |
| Cost rates | `configs/cost_config.py` | placeholder values | Per-token cost estimates — update to match Groq's published pricing |

**Known simplifications:**
- Cost estimates use flat input/output token rates and don't account for provider-side prompt caching (`cache_read` tokens), which is typically billed at a lower rate.
- Complexity routing is a hand-tuned heuristic (keyword + length + structure signals), not a learned classifier. The scoring function and routing table are intentionally decoupled so either can be swapped independently.
- Prometheus counters reset on gateway restart; Postgres (`/stats`) is the authoritative all-time record.

## Project structure

```
.
├── main.py                    # FastAPI app, request pipeline, Prometheus counters
├── seed_key.py                # One-off script to seed a test API key
├── routing/
│   ├── query_complexity.py           # Heuristic complexity scoring
│   └── query_router.py                # Complexity → provider mapping, dispatch + failover
├── providers/
│   ├── base.py                 # LLMProvider abstract interface
│   ├── groq_provider.py        # Groq via LangChain (async)
│   └── ollama_provider.py      # Local Ollama model
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
│       └── gateway_overview.json  # Cache hit ratio, latency, provider mix, token usage panels (manual import)
├── prometheus.yml             # Scrape config for the gateway's /metrics endpoint
├── docker-compose.yaml        # Postgres, Redis, Qdrant, Prometheus, Grafana
└── Dockerfile
```

## Future Extensions

Deliberately out of scope for the current version, listed here for transparency rather than as promises:

- **Kubernetes deployment** — the gateway is containerized (see `Dockerfile`) and could be deployed via a `Deployment`/`Service`/`ConfigMap`/`Secret` on a local cluster (`kind`/`minikube`). Left out of scope since it primarily demonstrates orchestration familiarity rather than AI infrastructure design, which is this project's focus.
- **Learned complexity routing** — replacing the current heuristic with a small classifier or a cheap-model-rates-the-prompt approach.
- **Automated tests** — current verification has been manual (curl + log inspection) throughout development. Unit tests for the complexity scorer, TTL filtering, and normalization would be the highest-value additions.
- **Provider-side cache-aware cost accounting** — factoring Groq's `cache_read` token pricing into `configs/cost_config.py`.