import asyncio

from sqlmodel.ext.asyncio.session import AsyncSession

from utils.db import engine, init_db
from models.api_key import APIKey


async def seed():
    await init_db()
    async with AsyncSession(engine) as session:
        from sqlmodel import select
        existing = await session.exec(select(APIKey).where(APIKey.key == "dev-test-key-123"))
        if existing.first() is None:
            session.add(APIKey(key="dev-test-key-123", label="local-dev"))
            await session.commit()
            print("Seeded API key: dev-test-key-123")
        else:
            print("Key already exists, skipping.")


if __name__ == "__main__":
    asyncio.run(seed())