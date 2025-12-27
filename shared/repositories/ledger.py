from typing import Optional, List, Any
from uuid import UUID
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.ledger import Ledger
from .base import BaseRepository


class LedgerRepository(BaseRepository[Ledger]):
    """Repository for Ledger (append-only event log) operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Ledger)

    async def append_event(
        self,
        lease_id: UUID,
        event_type: str,
        event_payload: dict,
        amount: Optional[float] = None
    ) -> Ledger:
        """Append an event to the ledger (insert-only)."""
        entry = Ledger(
            lease_id=lease_id,
            event_type=event_type,
            event_payload=event_payload,
            amount=amount,
        )
        return await self.create(entry)

    async def get_lease_history(
        self,
        lease_id: UUID,
        skip: int = 0,
        limit: int = 100
    ) -> List[Ledger]:
        """Get all events for a lease in chronological order."""
        stmt = (
            select(self.model)
            .where(self.model.lease_id == lease_id)
            .order_by(self.model.id)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_event_type(
        self,
        event_type: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Ledger]:
        """Get all events of a specific type."""
        stmt = (
            select(self.model)
            .where(self.model.event_type == event_type)
            .order_by(self.model.id)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_lease_history_by_event_type(
        self,
        lease_id: UUID,
        event_type: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Ledger]:
        """Get events for a lease filtered by event type."""
        stmt = (
            select(self.model)
            .where(
                (self.model.lease_id == lease_id)
                & (self.model.event_type == event_type)
            )
            .order_by(self.model.id)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_events_for_lease(self, lease_id: UUID) -> int:
        """Count total events for a lease."""
        stmt = select(func.count(self.model.id)).where(
            self.model.lease_id == lease_id
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def count_events_by_type(self, event_type: str) -> int:
        """Count total events of a specific type."""
        stmt = select(func.count(self.model.id)).where(
            self.model.event_type == event_type
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_total_amount_for_lease(self, lease_id: UUID) -> float:
        """Get total amount from all events for a lease."""
        stmt = select(func.sum(self.model.amount)).where(
            self.model.lease_id == lease_id
        )
        result = await self.session.execute(stmt)
        total = result.scalar()
        return float(total) if total else 0.0

    async def delete(self, id: int) -> bool:
        """Override delete to prevent deletion from append-only ledger."""
        raise NotImplementedError(
            "Cannot delete from append-only ledger. Ledger is immutable."
        )

    async def update(self, id: int, **kwargs) -> Optional[Ledger]:
        """Override update to prevent updates to append-only ledger."""
        raise NotImplementedError(
            "Cannot update append-only ledger. Ledger is immutable."
        )
