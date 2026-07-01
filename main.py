import time
import uuid

from fastapi import FastAPI, HTTPException, status, Request
from fastapi.concurrency import run_in_threadpool

from pydantic import BaseModel, Field

from dotenv import load_dotenv

from providers.groq_provider import GroqProvider
from providers.fallback_provider import FallbackProvider

from utils.normalize_query import normalize_prompt
from utils.vector_store import VectorStore
from utils.embedder import Embedder
from utils.logging import log

from configs.redis_config import RateLimiter

import structlog

import os
app = FastAPI(title="AI Agent Query Service")
load_dotenv()
api_key = os.getenv("GROQ_API_KEY")

log = structlog.get_logger()

CACHE_THRESHOLD = 0.8


rate_limiter = RateLimiter()
provider = GroqProvider(api_key=api_key)
fallback_provider = FallbackProvider()

embedder = Embedder()
store = VectorStore()


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="The input query for the Groq model")

@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)

    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)

    log.info(
        "request_completed",
        path=request.url.path,
        method=request.method,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    return response


async def call_with_failover(query: str) -> tuple[str, str]:
    try:
        result = await provider.call(query)
        return result, "groq"
    except Exception as e:
        log.warning("provider_failover", primary="groq", error=str(e))
        result = await fallback_provider.call(query)
        return result, "fallback"

@app.post("/query")
async def query(request : Request, body: QueryRequest):
    if not rate_limiter.is_allowed(request.client.host):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    normalized = normalize_prompt(body.query)
    embedding = await run_in_threadpool(embedder.embed, normalized)

    matches = await run_in_threadpool(store.search, embedding)
    if matches and matches[0].score >= CACHE_THRESHOLD:
        log.info(
            "cache_hit",
            query=normalized,
            score=matches[0].score,
            matched_prompt=matches[0].payload["prompt"],
        )
        return {"message": matches[0].payload["response"], "cache_hit": True}

    result = await call_with_failover(normalized)
    await run_in_threadpool(store.upsert, embedding, normalized, result)

    log.info(
        "cache_miss",
        query=normalized,
        top_score=matches[0].score if matches else None,
    )
    return {"message": result, "cache_hit": False}

@app.get("/health")
def health_check():
    return {"status": "healthy"}