import pytest
from sqlalchemy import text

from app.db.database import async_session_factory


@pytest.mark.asyncio
async def test_database_connection():
    async with async_session_factory() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1