import time
import uuid

from fastapi import FastAPI, HTTPException, status, Request
from fastapi.concurrency import run_in_threadpool

from fastapi.params import Depends
from pydantic import BaseModel, Field

from dotenv import load_dotenv
from sqlalchemy import func
from sqlmodel import select

from providers.groq_provider import GroqProvider
from providers.fallback_provider import FallbackProvider

from utils.auth import verify_api_key
from utils.normalize_query import normalize_prompt
from utils.vector_store import VectorStore
from utils.embedder import Embedder
from utils.logging import log
from utils.db import init_db
from models.request_logs import RequestLog
from utils.db import engine
from sqlmodel.ext.asyncio.session import AsyncSession

from configs.redis_config import RateLimiter

import structlog

from contextlib import asynccontextmanager

import os
app = FastAPI(title="AI Agent Query Service")
load_dotenv()
api_key = os.getenv("GROQ_API_KEY")

@app.on_event("startup")
async def startup_event():
    await init_db()

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


async def call_with_failover(query: str) -> tuple[str, str, dict | None]:
    try:
        result, usage = await provider.call(query)
        print(f"Result from Groq: {result}")
        return result, "groq", usage
    except Exception as e:
        log.warning("provider_failover", primary="groq", error=str(e))
        result, _ = await fallback_provider.call(query)
        print(f"Result from Fallback: {result}")
        return result, "fallback", None


async def log_request(api_key, cache_hit, provider_used, prompt_tokens, completion_tokens):
    total = (prompt_tokens or 0) + (completion_tokens or 0)
    async with AsyncSession(engine) as session:
        session.add(RequestLog(
            api_key=api_key,
            cache_hit=cache_hit,
            provider_used=provider_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total or None,
        ))
        await session.commit()


@app.post("/query")
async def query(request: Request, body: QueryRequest, api_key: str = Depends(verify_api_key)):
    if not rate_limiter.is_allowed(api_key):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    normalized = normalize_prompt(body.query)
    embedding = await run_in_threadpool(embedder.embed, normalized)

    matches = await run_in_threadpool(store.search, embedding)
    if matches and matches[0].score >= CACHE_THRESHOLD:
        saved_prompt_tokens = matches[0].payload.get("prompt_tokens")
        saved_completion_tokens = matches[0].payload.get("completion_tokens")
        log.info("cache_hit", query=normalized, score=matches[0].score, matched_prompt=matches[0].payload["prompt"])
        await log_request(api_key, cache_hit=True, provider_used=None, prompt_tokens=saved_prompt_tokens, completion_tokens=saved_completion_tokens)
        return {"message": matches[0].payload["response"], "cache_hit": True}

    result, provider_used, usage = await call_with_failover(normalized)
    prompt_tokens = usage.get("input_tokens") if usage else None
    completion_tokens = usage.get("output_tokens") if usage else None
    await run_in_threadpool(store.upsert, embedding, normalized, result, prompt_tokens, completion_tokens)

    log.info("cache_miss", query=normalized, provider_used=provider_used)
    await log_request(api_key, cache_hit=False, provider_used=provider_used, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return {"message": result, "cache_hit": False}

@app.get("/stats")
async def stats():
    async with AsyncSession(engine) as session:
        total = (await session.exec(select(func.count()).select_from(RequestLog))).one()
        hits = (await session.exec(
            select(func.count()).select_from(RequestLog).where(RequestLog.cache_hit == True)
        )).one()
        tokens_saved = (await session.exec(
            select(func.coalesce(func.sum(RequestLog.total_tokens), 0)).where(RequestLog.cache_hit == True)
        )).one()

    hit_rate = (hits / total) if total else 0
    return {
        "total_requests": total,
        "cache_hits": hits,
        "cache_hit_rate": round(hit_rate, 3),
        "tokens_saved_via_cache": tokens_saved,
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}