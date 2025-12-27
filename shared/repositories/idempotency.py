from typing import Optional, Any
from datetime import datetime, timedelta
from sqlalchemy import select, delete, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.idempotency import IdempotencyKey
from .base import BaseRepository


class IdempotencyRepository(BaseRepository[IdempotencyKey]):
    """Repository for Idempotency Key management."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, IdempotencyKey)

    async def get_by_id(self, key: str) -> Optional[IdempotencyKey]:
        """Get an idempotency key by key string (overrides base to use key column)."""
        stmt = select(self.model).where(self.model.key == key)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def update(self, key: str, **kwargs) -> Optional[IdempotencyKey]:
        """Update an idempotency key (overrides base to use key column)."""
        stmt = sql_update(self.model).where(self.model.key == key).values(**kwargs)
        await self.session.execute(stmt)
        await self.session.flush()
        return await self.get_by_id(key)

    async def check_and_store(
        self,
        key: str,
        operation: str,
        response_payload: Optional[dict] = None,
        ttl_seconds: int = 86400  # 24 hours default
    ) -> tuple[bool, Optional[dict]]:
        """
        Check if idempotency key exists, store if not.

        Returns:
            (is_duplicate, cached_response)
            - If key exists: (True, cached_response)
            - If key is new: (False, None)
        """
        # Check if key exists
        existing = await self.get_by_id(key)

        if existing:
            # Check if it has expired
            if existing.expires_at > datetime.utcnow():
                return (True, existing.response_payload)
            else:
                # Key has expired, delete it and treat as new
                await self.delete(key)

        # Store new idempotency key
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        entry = IdempotencyKey(
            key=key,
            operation=operation,
            response_payload=response_payload,
            expires_at=expires_at,
        )
        await self.create(entry)

        return (False, None)

    async def store_response(
        self,
        key: str,
        response_payload: dict
    ) -> Optional[IdempotencyKey]:
        """Store response payload for an idempotency key."""
        return await self.update(key, response_payload=response_payload)

    async def get_cached_response(self, key: str) -> Optional[dict]:
        """Get cached response for an idempotency key (if not expired)."""
        entry = await self.get_by_id(key)

        if entry is None:
            return None

        # Check expiration
        if entry.expires_at <= datetime.utcnow():
            # Key has expired, delete it
            await self.delete(key)
            return None

        return entry.response_payload

    async def cleanup_expired(self) -> int:
        """Delete all expired idempotency keys. Returns count deleted."""
        stmt = delete(self.model).where(
            self.model.expires_at <= datetime.utcnow()
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def delete(self, key: str) -> bool:
        """Delete an idempotency key."""
        stmt = delete(self.model).where(self.model.key == key)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0
