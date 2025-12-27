"""Core payment service business logic."""

import logging
from typing import Optional
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.payment import PaymentSchedule, PaymentStatus
from shared.models.lease import LeaseStatus
from shared.repositories.payment import PaymentRepository
from shared.repositories.lease import LeaseRepository
from shared.events.schemas import (
    PaymentScheduledEvent,
    PaymentAttemptedEvent,
    PaymentSucceededEvent,
    PaymentFailedEvent,
)
from shared.event_bus import event_bus, PAYMENT_EVENTS_TOPIC
from shared.event_persistence import EventPersister
from shared.retry_manager import PAYMENT_RETRY_CONFIG
from .payment_gateway import PaymentGateway, PaymentResult

logger = logging.getLogger(__name__)


class PaymentService:
    """Service for payment operations."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.payment_repo = PaymentRepository(session)
        self.lease_repo = LeaseRepository(session)
        self.event_persister = EventPersister(session)
        self.gateway = PaymentGateway()

    async def schedule_payments_for_lease(
        self,
        lease_id: UUID,
        schedule: list[PaymentSchedule],
    ) -> list[PaymentScheduledEvent]:
        """
        Schedule payments for a lease and emit events.

        Args:
            lease_id: ID of the lease
            schedule: List of payment schedules to process

        Returns:
            List of emitted events
        """
        events = []

        try:
            for payment in schedule:
                event = PaymentScheduledEvent(
                    payment_id=payment.id,
                    lease_id=lease_id,
                    installment_number=payment.installment_number,
                    due_date=payment.due_date,
                    amount=payment.amount,
                )

                # Persist event
                await self.event_persister.persist_event(event, lease_id)

                # Publish event
                await event_bus.publish_event(event, PAYMENT_EVENTS_TOPIC)

                events.append(event)

                logger.info(
                    f"Scheduled payment {payment.id} for lease {lease_id}: "
                    f"${payment.amount} on {payment.due_date}",
                    extra={"lease_id": str(lease_id), "payment_id": str(payment.id)},
                )

            await self.event_persister.commit()

            return events

        except Exception as e:
            logger.error(f"Failed to schedule payments for lease {lease_id}: {e}")
            await self.event_persister.rollback()
            raise

    async def attempt_payment(
        self,
        payment_id: UUID,
        lease_id: UUID,
        amount: Decimal,
        customer_id: str,
        attempt_number: int = 1,
    ) -> tuple[PaymentStatus, Optional[str]]:
        """
        Attempt to process a payment.

        Args:
            payment_id: ID of the payment
            lease_id: ID of the lease
            amount: Amount to charge
            customer_id: Customer identifier
            attempt_number: Which attempt this is (1, 2, 3...)

        Returns:
            (PaymentStatus, reason_if_failed)

        Raises:
            Exception: If payment processing fails
        """
        try:
            # Emit payment attempted event
            attempted_event = PaymentAttemptedEvent(
                payment_id=payment_id,
                lease_id=lease_id,
                attempt_number=attempt_number,
            )

            await self.event_persister.persist_event(attempted_event, lease_id)
            await event_bus.publish_event(attempted_event, PAYMENT_EVENTS_TOPIC)

            logger.info(
                f"Attempting payment {payment_id} (attempt {attempt_number})",
                extra={
                    "lease_id": str(lease_id),
                    "payment_id": str(payment_id),
                    "attempt": attempt_number,
                },
            )

            # Call payment gateway
            result, info = self.gateway.process_payment(
                payment_id=str(payment_id),
                lease_id=str(lease_id),
                amount=amount,
                attempt_number=attempt_number,
                customer_id=customer_id,
            )

            if result == PaymentResult.SUCCESS:
                # Create success event
                success_event = PaymentSucceededEvent(
                    payment_id=payment_id,
                    lease_id=lease_id,
                    amount=amount,
                    ledger_entry_id=0,  # Would be set by ledger
                )

                await self.event_persister.persist_payment_succeeded(success_event)
                await event_bus.publish_event(success_event, PAYMENT_EVENTS_TOPIC)

                # Update payment status
                await self.payment_repo.update_status(
                    payment_id,
                    PaymentStatus.PAID,
                    retry_count=attempt_number - 1,
                    last_attempt_at=datetime.utcnow(),
                )

                await self.payment_repo.commit()

                logger.info(
                    f"Payment succeeded: {payment_id}",
                    extra={"lease_id": str(lease_id), "payment_id": str(payment_id)},
                )

                return PaymentStatus.PAID, None

            else:
                # Create failure event
                retry_scheduled = attempt_number < 3

                failure_event = PaymentFailedEvent(
                    payment_id=payment_id,
                    lease_id=lease_id,
                    reason=info,
                    retry_scheduled=retry_scheduled,
                    attempt_number=attempt_number,
                    next_retry_at=(
                        PAYMENT_RETRY_CONFIG.get_next_retry_time(attempt_number - 1)
                        if retry_scheduled
                        else None
                    ),
                )

                await self.event_persister.persist_payment_failed(failure_event)
                await event_bus.publish_event(failure_event, PAYMENT_EVENTS_TOPIC)

                # Update payment status
                await self.payment_repo.update_status(
                    payment_id,
                    PaymentStatus.FAILED,
                    retry_count=attempt_number,
                    last_attempt_at=datetime.utcnow(),
                )

                await self.payment_repo.commit()

                logger.warning(
                    f"Payment failed: {payment_id} - {info} (attempt {attempt_number})",
                    extra={
                        "lease_id": str(lease_id),
                        "payment_id": str(payment_id),
                        "reason": info,
                    },
                )

                return PaymentStatus.FAILED, info

        except Exception as e:
            logger.error(f"Error processing payment {payment_id}: {e}")
            await self.payment_repo.rollback()
            await self.event_persister.rollback()
            raise

    async def get_payment(self, payment_id: UUID) -> Optional[PaymentSchedule]:
        """Get a payment by ID."""
        return await self.payment_repo.get_by_id(payment_id)

    async def get_lease_payments(
        self,
        lease_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[PaymentSchedule]:
        """Get all payments for a lease."""
        return await self.payment_repo.get_by_lease_id(lease_id, skip, limit)

    async def get_due_payments(
        self,
        from_date=None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[PaymentSchedule]:
        """Get payments due on or before a date."""
        from datetime import date

        if from_date is None:
            from_date = date.today()

        return await self.payment_repo.get_due_payments(from_date, skip=skip, limit=limit)

    async def check_lease_for_default(self, lease_id: UUID) -> bool:
        """
        Check if lease should be defaulted due to failed payments.

        Args:
            lease_id: ID of the lease

        Returns:
            True if lease was defaulted
        """
        # Get lease
        lease = await self.lease_repo.get_by_id(lease_id)

        if lease is None or lease.status == LeaseStatus.DEFAULTED:
            return False

        # Count failed payments
        failed_count = await self.payment_repo.count_failed_by_lease(lease_id)

        if failed_count >= 3:
            # Default the lease
            from services.lease_service.domain.lease_service import LeaseService

            lease_service = LeaseService(self.session)
            result = await lease_service.check_and_default(lease_id)

            return result

        return False

    async def calculate_early_payoff(
        self,
        lease_id: UUID,
    ) -> tuple[Decimal, Decimal, Decimal]:
        """
        Calculate early payoff amount for a lease.

        Args:
            lease_id: ID of the lease

        Returns:
            (remaining_balance, payoff_amount, discount_amount)

        Raises:
            ValueError: If lease not found
        """
        # Get lease and schedule
        lease = await self.lease_repo.get_by_id(lease_id)

        if lease is None:
            raise ValueError(f"Lease not found: {lease_id}")

        # Get all payments
        all_payments = await self.payment_repo.get_by_lease_id(lease_id, skip=0, limit=1000)

        # Calculate totals
        total_scheduled = sum(p.amount for p in all_payments)

        # Get paid payments
        paid_payments = [p for p in all_payments if p.status == PaymentStatus.PAID]
        total_paid = sum(p.amount for p in paid_payments)

        # Remaining balance
        remaining_balance = total_scheduled - total_paid

        # Apply 2% early payoff discount
        discount_amount = (remaining_balance * Decimal("0.02")).quantize(Decimal("0.01"))
        payoff_amount = (remaining_balance - discount_amount).quantize(Decimal("0.01"))

        return remaining_balance, payoff_amount, discount_amount

    async def process_early_payoff(
        self,
        lease_id: UUID,
        customer_id: str,
    ) -> tuple[Decimal, Decimal, Decimal, str]:
        """
        Process early payoff for a lease.

        Args:
            lease_id: ID of the lease
            customer_id: Customer identifier

        Returns:
            (remaining_balance, payoff_amount, discount_amount, transaction_id)
        """
        try:
            remaining_balance, payoff_amount, discount_amount = (
                await self.calculate_early_payoff(lease_id)
            )

            # Create a single payment for the payoff
            payoff_payment_id = UUID(int=0)  # Special ID for payoff

            # Process the payment
            status, info = await self.attempt_payment(
                payment_id=payoff_payment_id,
                lease_id=lease_id,
                amount=payoff_amount,
                customer_id=customer_id,
                attempt_number=1,
            )

            if status != PaymentStatus.PAID:
                raise ValueError(f"Early payoff payment failed: {info}")

            # Mark all remaining pending payments as cancelled
            remaining_payments = await self.payment_repo.get_by_lease_and_status(
                lease_id, PaymentStatus.PENDING
            )

            for payment in remaining_payments:
                await self.payment_repo.update_status(
                    payment.id,
                    PaymentStatus.CANCELLED,
                )

            await self.payment_repo.commit()

            # Complete the lease
            from services.lease_service.domain.lease_service import LeaseService

            lease_service = LeaseService(self.session)
            await lease_service.check_and_complete(lease_id)

            logger.info(
                f"Early payoff processed for lease {lease_id}: "
                f"${payoff_amount} with ${discount_amount} discount",
                extra={"lease_id": str(lease_id)},
            )

            return remaining_balance, payoff_amount, discount_amount, str(payoff_payment_id)

        except Exception as e:
            logger.error(f"Failed to process early payoff for lease {lease_id}: {e}")
            await self.payment_repo.rollback()
            await self.event_persister.rollback()
            raise
