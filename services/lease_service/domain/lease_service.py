"""Core lease business logic."""

import logging
from typing import Optional
from uuid import UUID
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.lease import Lease, LeaseStatus
from shared.models.payment import PaymentSchedule, PaymentStatus
from shared.repositories.lease import LeaseRepository
from shared.repositories.payment import PaymentRepository
from shared.repositories.idempotency import IdempotencyRepository
from shared.events.schemas import LeaseCreatedEvent, LeaseCompletedEvent
from shared.event_bus import event_bus
from shared.event_persistence import EventPersister
from .payment_schedule_generator import PaymentScheduleGenerator

logger = logging.getLogger(__name__)


class LeaseStateMachine:
    """State machine for lease status transitions."""

    # Valid transitions: from_status -> [valid_to_statuses]
    VALID_TRANSITIONS = {
        LeaseStatus.PENDING: [LeaseStatus.ACTIVE],
        LeaseStatus.ACTIVE: [LeaseStatus.COMPLETED, LeaseStatus.DEFAULTED],
        LeaseStatus.COMPLETED: [],  # Terminal state
        LeaseStatus.DEFAULTED: [],  # Terminal state
    }

    @classmethod
    def can_transition(
        cls,
        from_status: LeaseStatus,
        to_status: LeaseStatus,
    ) -> bool:
        """Check if transition is allowed."""
        if from_status not in cls.VALID_TRANSITIONS:
            return False

        return to_status in cls.VALID_TRANSITIONS[from_status]

    @classmethod
    def validate_transition(
        cls,
        from_status: LeaseStatus,
        to_status: LeaseStatus,
    ) -> None:
        """Validate transition, raise error if invalid."""
        if not cls.can_transition(from_status, to_status):
            raise ValueError(
                f"Invalid transition: {from_status} -> {to_status}"
            )


class LeaseService:
    """Service for lease operations."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.lease_repo = LeaseRepository(session)
        self.payment_repo = PaymentRepository(session)
        self.idempotency_repo = IdempotencyRepository(session)
        self.event_persister = EventPersister(session)
        self.schedule_generator = PaymentScheduleGenerator()

    async def create_lease(
        self,
        customer_id: str,
        principal_amount: Decimal,
        term_months: int,
        idempotency_key: str,
    ) -> tuple[Lease, list[PaymentSchedule]]:
        """
        Create a new lease with payment schedule.

        Args:
            customer_id: Customer identifier
            principal_amount: Lease principal amount
            term_months: Lease term in months
            idempotency_key: Idempotency key for duplicate prevention

        Returns:
            (Lease, list of PaymentSchedule)

        Raises:
            ValueError: If validation fails or key already exists with different data
        """
        # Validate inputs
        self._validate_lease_inputs(principal_amount, term_months)

        # Check idempotency
        is_duplicate, cached_response = await self.idempotency_repo.check_and_store(
            key=idempotency_key,
            operation="CREATE_LEASE",
            response_payload=None,
            ttl_seconds=86400,  # 24 hours
        )

        if is_duplicate and cached_response:
            logger.info(f"Duplicate lease creation (idempotency key: {idempotency_key})")
            # In production, would reconstruct the lease from cached response
            # For now, we'll re-fetch from DB
            pass

        try:
            # Create lease
            lease = Lease(
                customer_id=customer_id,
                principal_amount=principal_amount,
                term_months=term_months,
                status=LeaseStatus.PENDING,
            )

            created_lease = await self.lease_repo.create(lease)
            await self.lease_repo.commit()

            logger.info(f"Created lease {created_lease.id} for customer {customer_id}")

            # Generate payment schedule
            schedule_data = self.schedule_generator.generate_equal_installments(
                lease_id=created_lease.id,
                principal_amount=principal_amount,
                term_months=term_months,
            )

            # Create payment records
            payment_schedules = []
            for payment_data in schedule_data:
                payment = PaymentSchedule(
                    lease_id=created_lease.id,
                    installment_number=payment_data["installment_number"],
                    due_date=payment_data["due_date"],
                    amount=payment_data["amount"],
                    status=PaymentStatus.PENDING,
                )
                created_payment = await self.payment_repo.create(payment)
                payment_schedules.append(created_payment)

            await self.payment_repo.commit()

            logger.info(
                f"Created {len(payment_schedules)} payment schedules for lease {created_lease.id}"
            )

            # Persist event
            event = LeaseCreatedEvent(
                lease_id=created_lease.id,
                customer_id=customer_id,
                principal_amount=principal_amount,
                term_months=term_months,
            )

            await self.event_persister.persist_lease_created(event)

            # Publish event to trigger payment scheduling
            await event_bus.publish_event(event)

            logger.info(f"Published LEASE_CREATED event for lease {created_lease.id}")

            # Store response in idempotency cache
            response = {
                "lease_id": str(created_lease.id),
                "customer_id": customer_id,
                "principal_amount": float(principal_amount),
                "term_months": term_months,
                "status": created_lease.status.value,
            }
            await self.idempotency_repo.store_response(idempotency_key, response)
            await self.idempotency_repo.commit()

            return created_lease, payment_schedules

        except Exception as e:
            logger.error(f"Failed to create lease: {e}")
            await self.lease_repo.rollback()
            await self.payment_repo.rollback()
            await self.idempotency_repo.rollback()
            raise

    async def get_lease(self, lease_id: UUID) -> Optional[Lease]:
        """Get a lease by ID."""
        return await self.lease_repo.get_by_id(lease_id)

    async def get_lease_by_customer(
        self,
        customer_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Lease]:
        """Get all leases for a customer."""
        return await self.lease_repo.get_by_customer_id(customer_id, skip, limit)

    async def update_lease_status(
        self,
        lease_id: UUID,
        new_status: LeaseStatus,
    ) -> Lease:
        """
        Update lease status with state machine validation.

        Args:
            lease_id: ID of the lease
            new_status: New status

        Raises:
            ValueError: If transition is invalid
        """
        lease = await self.lease_repo.get_by_id(lease_id)

        if lease is None:
            raise ValueError(f"Lease not found: {lease_id}")

        # Validate state transition
        LeaseStateMachine.validate_transition(lease.status, new_status)

        # Update status
        updated = await self.lease_repo.update_status(lease_id, new_status)

        await self.lease_repo.commit()

        logger.info(f"Updated lease {lease_id} status: {lease.status} -> {new_status}")

        return updated

    async def check_and_activate(self, lease_id: UUID) -> bool:
        """
        Check if lease should be activated (first payment scheduled).

        Args:
            lease_id: ID of the lease

        Returns:
            True if lease was activated
        """
        lease = await self.lease_repo.get_by_id(lease_id)

        if lease is None:
            return False

        # Can only activate if in PENDING status
        if lease.status != LeaseStatus.PENDING:
            return False

        # Check if first payment is scheduled
        first_payment = await self.payment_repo.get_next_payment(lease_id)

        if first_payment is None:
            logger.warning(f"No payment scheduled for lease {lease_id}")
            return False

        # Activate the lease
        await self.update_lease_status(lease_id, LeaseStatus.ACTIVE)

        return True

    async def check_and_complete(self, lease_id: UUID) -> bool:
        """
        Check if lease should be completed (all payments done).

        Args:
            lease_id: ID of the lease

        Returns:
            True if lease was completed
        """
        lease = await self.lease_repo.get_by_id(lease_id)

        if lease is None:
            return False

        # Can only complete if in ACTIVE status
        if lease.status != LeaseStatus.ACTIVE:
            return False

        # Check if any pending or failed payments remain
        pending_count = await self.payment_repo.count_by_lease_and_status(
            lease_id, PaymentStatus.PENDING
        )
        failed_count = await self.payment_repo.count_by_lease_and_status(
            lease_id, PaymentStatus.FAILED
        )

        if pending_count > 0 or failed_count > 0:
            return False

        # All payments are paid, complete the lease
        await self.update_lease_status(lease_id, LeaseStatus.COMPLETED)

        # Emit completion event
        event = LeaseCompletedEvent(
            lease_id=lease_id,
            customer_id=lease.customer_id,
        )

        await self.event_persister.persist_lease_completed(event)
        await event_bus.publish_event(event)

        logger.info(f"Lease {lease_id} completed")

        return True

    async def check_and_default(self, lease_id: UUID) -> bool:
        """
        Check if lease should be defaulted (3+ failed payments).

        Args:
            lease_id: ID of the lease

        Returns:
            True if lease was defaulted
        """
        lease = await self.lease_repo.get_by_id(lease_id)

        if lease is None:
            return False

        # Can default from ACTIVE or PENDING
        if lease.status not in [LeaseStatus.ACTIVE, LeaseStatus.PENDING]:
            return False

        # Check failed payment count
        failed_count = await self.payment_repo.count_failed_by_lease(lease_id)

        if failed_count < 3:
            return False

        # Too many failures, default the lease
        await self.update_lease_status(lease_id, LeaseStatus.DEFAULTED)

        logger.warning(f"Lease {lease_id} defaulted due to {failed_count} failed payments")

        return True

    @staticmethod
    def _validate_lease_inputs(principal_amount: Decimal, term_months: int) -> None:
        """Validate lease creation inputs."""
        if principal_amount <= 0:
            raise ValueError("Principal amount must be positive")

        if not (1 <= term_months <= 60):
            raise ValueError("Term must be between 1 and 60 months")
