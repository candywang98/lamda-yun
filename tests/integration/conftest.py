"""Shared test fixtures for integration tests."""

from collections.abc import AsyncIterator

import pytest
from cloudctl_api.db import Database
from cloudctl_api.settings import Settings
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Provide a database session for integration tests."""
    settings = Settings(env="test", repository_mode="memory")
    db = Database(settings)

    # Create schema
    await db.create_schema()

    async with db.session_factory() as session:
        yield session
        await session.rollback()

    await db.dispose()
