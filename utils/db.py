from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine

from configs.postgres_config import POSTGRES_URL

engine = create_async_engine(POSTGRES_URL, echo=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        
async def get_session():
    async with AsyncSession(engine) as session:
        yield session