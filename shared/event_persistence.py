"""Event persistence to ledger."""

import logging
from typing import Optional
from uuid import UUID
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from shared.events.schemas import (
    BaseEvent,
    LeaseCreatedEvent,
    PaymentScheduledEvent,
    PaymentAttemptedEvent,
    PaymentSucceededEvent,
    PaymentFailedEvent,
    LeaseCompletedEvent,
)
from shared.repositories.ledger import LedgerRepository

logger = logging.getLogger(__name__)


class EventPersister:
    """Persists events to the ledger."""

    def __init__(self, db_session: AsyncSession):
        self.session = db_session
        self.repo = LedgerRepository(db_session)

    async def persist_event(
        self,
        event: BaseEvent,
        lease_id: UUID,
    ) -> int:
        """
        Persist an event to the ledger.

        Args:
            event: Event to persist
            lease_id: ID of the lease

        Returns:
            Ledger entry ID
        """
        try:
            # Serialize event to dict with JSON-compatible types
            event_dict = event.model_dump(mode='json')

            # Extract amount if present
            amount = None
            if hasattr(event, 'amount'):
                amount = Decimal(str(event.amount))
            elif hasattr(event, 'principal_amount'):
                amount = Decimal(str(event.principal_amount))
            elif hasattr(event, 'total_paid'):
                amount = Decimal(str(event.total_paid))

            # Append to ledger
            entry = await self.repo.append_event(
                lease_id=lease_id,
                event_type=event.event_type,
                event_payload=event_dict,
                amount=amount,
            )

            await self.repo.commit()

            logger.info(
                f"Persisted {event.event_type} to ledger (entry_id={entry.id})"
            )

            return entry.id

        except Exception as e:
            logger.error(f"Failed to persist event {event.event_type}: {e}")
            await self.repo.rollback()
            raise

    async def persist_lease_created(
        self,
        event: LeaseCreatedEvent,
    ) -> int:
        """Persist a LEASE_CREATED event."""
        return await self.persist_event(event, event.lease_id)

    async def persist_payment_scheduled(
        self,
        event: PaymentScheduledEvent,
    ) -> int:
        """Persist a PAYMENT_SCHEDULED event."""
        return await self.persist_event(event, event.lease_id)

    async def persist_payment_attempted(
        self,
        event: PaymentAttemptedEvent,
    ) -> int:
        """Persist a PAYMENT_ATTEMPTED event."""
        return await self.persist_event(event, event.lease_id)

    async def persist_payment_succeeded(
        self,
        event: PaymentSucceededEvent,
    ) -> int:
        """Persist a PAYMENT_SUCCEEDED event."""
        return await self.persist_event(event, event.lease_id)

    async def persist_payment_failed(
        self,
        event: PaymentFailedEvent,
    ) -> int:
        """Persist a PAYMENT_FAILED event."""
        return await self.persist_event(event, event.lease_id)

    async def persist_lease_completed(
        self,
        event: LeaseCompletedEvent,
    ) -> int:
        """Persist a LEASE_COMPLETED event."""
        return await self.persist_event(event, event.lease_id)


async def persist_event_with_session(
    event: BaseEvent,
    lease_id: UUID,
    session: AsyncSession,
) -> int:
    """
    Persist an event using a provided session.

    Helper function for easy event persistence.
    """
    persister = EventPersister(session)
    return await persister.persist_event(event, lease_id)
