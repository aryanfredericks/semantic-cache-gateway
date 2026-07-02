from fastapi import Header, HTTPException
from sqlmodel import select

from utils.db import engine
from sqlmodel.ext.asyncio.session import AsyncSession
from models.api_key import APIKey


async def verify_api_key(x_api_key: str = Header(...)) -> str:
    async with AsyncSession(engine) as session:
        result = await session.exec(
            select(APIKey).where(APIKey.key == x_api_key, APIKey.is_active == True)
        )
        api_key = result.first()

    if api_key is None:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")

    return api_key.key