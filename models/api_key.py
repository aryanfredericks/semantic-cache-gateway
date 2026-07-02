from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column
from sqlmodel import DateTime, SQLModel, Field


class APIKey(SQLModel, table=True):
    __tablename__ = "api_keys"

    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(unique=True, index=True)
    label: str
    is_active: bool = Field(default=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )