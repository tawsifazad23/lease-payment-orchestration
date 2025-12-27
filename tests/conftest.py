import asyncio
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock
import os

# Set test environment
os.environ["ENVIRONMENT"] = "test"
os.environ["LOG_LEVEL"] = "DEBUG"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def test_db_engine():
    """Create a test database engine."""
    # Use SQLite for testing (in-memory)
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )

    # Create tables
    from shared.database.base import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(scope="function")
async def test_db_session(test_db_engine):
    """Create a test database session."""
    SessionLocal = async_sessionmaker(
        test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with SessionLocal() as session:
        yield session


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    return AsyncMock()


@pytest.fixture
def mock_event_bus():
    """Create a mock event bus."""
    return MagicMock()


@pytest.fixture
def mock_celery_task():
    """Create a mock Celery task."""
    task = MagicMock()
    task.delay = MagicMock(return_value=MagicMock(id="task-123"))
    return task


@pytest.fixture
async def mock_event_bus_initialized():
    """Initialize event bus with mock Redis for testing."""
    from shared.event_bus import event_bus
    from shared.redis_client import RedisClient

    # Mock Redis client
    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock(return_value=1)
    mock_redis.setex = AsyncMock(return_value=True)

    # Patch RedisClient.get_client to return mock
    original_get_client = RedisClient.get_client
    RedisClient.get_client = AsyncMock(return_value=mock_redis)

    # Initialize event bus
    await event_bus.initialize()

    yield event_bus

    # Cleanup
    RedisClient.get_client = original_get_client
    event_bus.publisher = None
    event_bus.consumer = None
    event_bus.dlq = None
