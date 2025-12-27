from typing import Optional, List
from uuid import UUID
from datetime import date, datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.payment import PaymentSchedule, PaymentStatus
from .base import BaseRepository


class PaymentRepository(BaseRepository[PaymentSchedule]):
    """Repository for Payment Schedule operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, PaymentSchedule)

    async def get_by_lease_id(
        self,
        lease_id: UUID,
        skip: int = 0,
        limit: int = 100
    ) -> List[PaymentSchedule]:
        """Get all payments for a lease."""
        stmt = (
            select(self.model)
            .where(self.model.lease_id == lease_id)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_lease_and_status(
        self,
        lease_id: UUID,
        status: PaymentStatus,
        skip: int = 0,
        limit: int = 100
    ) -> List[PaymentSchedule]:
        """Get payments for a lease with specific status."""
        stmt = (
            select(self.model)
            .where(
                (self.model.lease_id == lease_id)
                & (self.model.status == status)
            )
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_due_payments(
        self,
        due_before: date,
        status: PaymentStatus = PaymentStatus.PENDING,
        skip: int = 0,
        limit: int = 100
    ) -> List[PaymentSchedule]:
        """Get payments due before a certain date."""
        stmt = (
            select(self.model)
            .where(
                (self.model.due_date <= due_before)
                & (self.model.status == status)
            )
            .order_by(self.model.due_date)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_overdue_payments(
        self,
        days_overdue: int = 0,
        skip: int = 0,
        limit: int = 100
    ) -> List[PaymentSchedule]:
        """Get overdue payments."""
        from datetime import timedelta
        cutoff_date = date.today() - timedelta(days=days_overdue)
        return await self.get_due_payments(cutoff_date, skip=skip, limit=limit)

    async def update_status(
        self,
        payment_id: UUID,
        status: PaymentStatus,
        retry_count: Optional[int] = None,
        last_attempt_at: Optional[datetime] = None
    ) -> Optional[PaymentSchedule]:
        """Update payment status and retry info."""
        update_data = {"status": status}
        if retry_count is not None:
            update_data["retry_count"] = retry_count
        if last_attempt_at is not None:
            update_data["last_attempt_at"] = last_attempt_at
        return await self.update(payment_id, **update_data)

    async def count_by_lease_and_status(
        self,
        lease_id: UUID,
        status: PaymentStatus
    ) -> int:
        """Count payments for a lease by status."""
        stmt = select(func.count(self.model.id)).where(
            (self.model.lease_id == lease_id)
            & (self.model.status == status)
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def count_failed_by_lease(self, lease_id: UUID) -> int:
        """Count failed payments for a lease."""
        return await self.count_by_lease_and_status(lease_id, PaymentStatus.FAILED)

    async def get_next_payment(self, lease_id: UUID) -> Optional[PaymentSchedule]:
        """Get the next pending payment for a lease."""
        stmt = (
            select(self.model)
            .where(
                (self.model.lease_id == lease_id)
                & (self.model.status == PaymentStatus.PENDING)
            )
            .order_by(self.model.due_date)
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()
