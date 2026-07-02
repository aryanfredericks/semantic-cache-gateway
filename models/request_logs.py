from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime
from sqlmodel import SQLModel, Field


class RequestLog(SQLModel, table=True):
    __tablename__ = "request_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    api_key: str = Field(index=True)
    cache_hit: bool
    provider_used: Optional[str] = None 
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )