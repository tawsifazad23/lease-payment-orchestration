from typing import Optional, List
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.lease import Lease, LeaseStatus
from .base import BaseRepository


class LeaseRepository(BaseRepository[Lease]):
    """Repository for Lease operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Lease)

    async def get_by_customer_id(
        self,
        customer_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Lease]:
        """Get all leases for a customer."""
        stmt = (
            select(self.model)
            .where(self.model.customer_id == customer_id)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_status(
        self,
        status: LeaseStatus,
        skip: int = 0,
        limit: int = 100
    ) -> List[Lease]:
        """Get all leases with a specific status."""
        stmt = (
            select(self.model)
            .where(self.model.status == status)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_customer_and_status(
        self,
        customer_id: str,
        status: LeaseStatus,
        skip: int = 0,
        limit: int = 100
    ) -> List[Lease]:
        """Get leases by customer and status."""
        stmt = (
            select(self.model)
            .where(
                (self.model.customer_id == customer_id)
                & (self.model.status == status)
            )
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update_status(
        self,
        lease_id: UUID,
        status: LeaseStatus
    ) -> Optional[Lease]:
        """Update lease status."""
        return await self.update(lease_id, status=status)

    async def count_by_status(self, status: LeaseStatus) -> int:
        """Count leases by status."""
        from sqlalchemy import func
        stmt = select(func.count(self.model.id)).where(
            self.model.status == status
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0
