"""Redis connection management."""

import redis.asyncio as redis
import logging
from typing import Optional
from shared.config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis connection client with connection pooling."""

    _instance: Optional[redis.Redis] = None
    _pool: Optional[redis.ConnectionPool] = None

    @classmethod
    async def get_client(cls) -> redis.Redis:
        """Get or create Redis client."""
        if cls._instance is None:
            cls._instance = await cls._create_client()
        return cls._instance

    @classmethod
    async def _create_client(cls) -> redis.Redis:
        """Create Redis connection with pooling."""
        # Parse Redis URL to create connection pool
        pool = redis.ConnectionPool.from_url(
            settings.redis_url,
            max_connections=10,
            decode_responses=True,
        )
        cls._pool = pool
        client = redis.Redis(connection_pool=pool)

        # Test connection
        try:
            await client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

        return client

    @classmethod
    async def close(cls):
        """Close Redis connection."""
        if cls._instance is not None:
            await cls._instance.close()
            cls._instance = None
            logger.info("Redis connection closed")

        if cls._pool is not None:
            await cls._pool.disconnect()
            cls._pool = None


async def get_redis() -> redis.Redis:
    """Dependency for FastAPI to get Redis client."""
    return await RedisClient.get_client()
