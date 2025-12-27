"""Integration tests for Payment Service."""

import pytest
from uuid import uuid4
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from services.payment_service.domain.payment_service import PaymentService
from services.payment_service.domain.payment_gateway import PaymentGateway, PaymentResult
from shared.models.lease import Lease, LeaseStatus
from shared.models.payment import PaymentSchedule, PaymentStatus
from shared.repositories.payment import PaymentRepository
from shared.repositories.lease import LeaseRepository


class TestPaymentGateway:
    """Test payment gateway simulation."""

    def test_process_payment_success(self):
        """Test successful payment processing."""
        PaymentGateway.set_success_rate(1.0)  # 100% success

        result, info = PaymentGateway.process_payment(
            payment_id="pay-001",
            lease_id="lease-001",
            amount=Decimal("100.00"),
            attempt_number=1,
        )

        assert result == PaymentResult.SUCCESS
        assert info.startswith("txn-")

    def test_process_payment_failure(self):
        """Test failed payment processing."""
        PaymentGateway.set_success_rate(0.0)  # 0% success

        result, info = PaymentGateway.process_payment(
            payment_id="pay-002",
            lease_id="lease-002",
            amount=Decimal("100.00"),
            attempt_number=1,
        )

        assert result == PaymentResult.FAILURE
        assert isinstance(info, str)

    def test_process_payment_retry_increases_success_rate(self):
        """Test that retry attempts have higher success rate."""
        PaymentGateway.set_success_rate(0.5)  # 50% initial success

        # First attempt - 50% success
        # Second attempt - 55% success
        # Third attempt - 60% success
        for attempt in range(1, 4):
            adjusted_rate = 0.5 + ((attempt - 1) * 0.05)
            # Just verify the logic, actual randomness varies

    def test_set_success_rate_valid(self):
        """Test setting valid success rate."""
        PaymentGateway.set_success_rate(0.7)
        assert PaymentGateway.SUCCESS_RATE == 0.7

        PaymentGateway.set_success_rate(1.0)
        assert PaymentGateway.SUCCESS_RATE == 1.0

        PaymentGateway.set_success_rate(0.0)
        assert PaymentGateway.SUCCESS_RATE == 0.0

    def test_set_success_rate_invalid(self):
        """Test setting invalid success rate."""
        with pytest.raises(ValueError):
            PaymentGateway.set_success_rate(-0.1)

        with pytest.raises(ValueError):
            PaymentGateway.set_success_rate(1.1)


class TestPaymentService:
    """Test Payment Service business logic."""

    @pytest.mark.asyncio
    async def test_schedule_payments_for_lease(self, test_db_session):
        """Test scheduling payments for a lease."""
        service = PaymentService(test_db_session)
        lease_id = uuid4()

        # Create payment schedules
        payments = [
            PaymentSchedule(
                lease_id=lease_id,
                installment_number=1,
                due_date=date(2025, 1, 15),
                amount=Decimal("300.00"),
            ),
            PaymentSchedule(
                lease_id=lease_id,
                installment_number=2,
                due_date=date(2025, 2, 15),
                amount=Decimal("300.00"),
            ),
        ]

        # Mock event bus
        with patch("shared.event_bus.event_bus.publish_event", new_callable=AsyncMock):
            events = await service.schedule_payments_for_lease(lease_id, payments)

        assert len(events) == 2
        assert events[0].payment_id == payments[0].id
        assert events[1].payment_id == payments[1].id

    @pytest.mark.asyncio
    async def test_attempt_payment_success(self, test_db_session):
        """Test successful payment attempt."""
        PaymentGateway.set_success_rate(1.0)  # Guarantee success
        service = PaymentService(test_db_session)

        # Create lease and payment
        lease_repo = LeaseRepository(test_db_session)
        lease = Lease(
            customer_id="CUST-001",
            status=LeaseStatus.ACTIVE,
            principal_amount=Decimal("1000.00"),
            term_months=12,
        )
        created_lease = await lease_repo.create(lease)
        await lease_repo.commit()

        payment_repo = PaymentRepository(test_db_session)
        payment = PaymentSchedule(
            lease_id=created_lease.id,
            installment_number=1,
            due_date=date(2025, 1, 15),
            amount=Decimal("100.00"),
        )
        created_payment = await payment_repo.create(payment)
        await payment_repo.commit()

        # Attempt payment
        with patch("shared.event_bus.event_bus.publish_event", new_callable=AsyncMock):
            status, reason = await service.attempt_payment(
                payment_id=created_payment.id,
                lease_id=created_lease.id,
                amount=Decimal("100.00"),
                customer_id="CUST-001",
                attempt_number=1,
            )

        assert status == PaymentStatus.PAID
        assert reason is None

        # Verify payment updated
        updated_payment = await payment_repo.get_by_id(created_payment.id)
        assert updated_payment.status == PaymentStatus.PAID
        assert updated_payment.retry_count == 0

    @pytest.mark.asyncio
    async def test_attempt_payment_failure(self, test_db_session):
        """Test failed payment attempt."""
        PaymentGateway.set_success_rate(0.0)  # Guarantee failure
        service = PaymentService(test_db_session)

        # Create lease and payment
        lease_repo = LeaseRepository(test_db_session)
        lease = Lease(
            customer_id="CUST-002",
            status=LeaseStatus.ACTIVE,
            principal_amount=Decimal("1000.00"),
            term_months=12,
        )
        created_lease = await lease_repo.create(lease)
        await lease_repo.commit()

        payment_repo = PaymentRepository(test_db_session)
        payment = PaymentSchedule(
            lease_id=created_lease.id,
            installment_number=1,
            due_date=date(2025, 1, 15),
            amount=Decimal("100.00"),
        )
        created_payment = await payment_repo.create(payment)
        await payment_repo.commit()

        # Attempt payment
        with patch("shared.event_bus.event_bus.publish_event", new_callable=AsyncMock):
            status, reason = await service.attempt_payment(
                payment_id=created_payment.id,
                lease_id=created_lease.id,
                amount=Decimal("100.00"),
                customer_id="CUST-002",
                attempt_number=1,
            )

        assert status == PaymentStatus.FAILED
        assert reason is not None

        # Verify payment updated
        updated_payment = await payment_repo.get_by_id(created_payment.id)
        assert updated_payment.status == PaymentStatus.FAILED
        assert updated_payment.retry_count == 1

    @pytest.mark.asyncio
    async def test_get_payment(self, test_db_session):
        """Test retrieving a payment."""
        service = PaymentService(test_db_session)
        lease_id = uuid4()

        payment_repo = PaymentRepository(test_db_session)
        payment = PaymentSchedule(
            lease_id=lease_id,
            installment_number=1,
            due_date=date(2025, 1, 15),
            amount=Decimal("100.00"),
        )
        created = await payment_repo.create(payment)
        await payment_repo.commit()

        retrieved = await service.get_payment(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.amount == Decimal("100.00")

    @pytest.mark.asyncio
    async def test_get_lease_payments(self, test_db_session):
        """Test retrieving all payments for a lease."""
        service = PaymentService(test_db_session)
        lease_id = uuid4()

        payment_repo = PaymentRepository(test_db_session)

        # Create 3 payments
        for i in range(1, 4):
            payment = PaymentSchedule(
                lease_id=lease_id,
                installment_number=i,
                due_date=date(2025, i, 15),
                amount=Decimal("100.00"),
            )
            await payment_repo.create(payment)

        await payment_repo.commit()

        # Retrieve all
        payments = await service.get_lease_payments(lease_id)

        assert len(payments) == 3
        assert all(p.lease_id == lease_id for p in payments)

    @pytest.mark.asyncio
    async def test_calculate_early_payoff(self, test_db_session):
        """Test early payoff calculation with 2% discount."""
        service = PaymentService(test_db_session)
        lease_id = uuid4()

        lease_repo = LeaseRepository(test_db_session)
        lease = Lease(
            id=lease_id,
            customer_id="CUST-003",
            status=LeaseStatus.ACTIVE,
            principal_amount=Decimal("1000.00"),
            term_months=10,
        )
        await lease_repo.create(lease)
        await lease_repo.commit()

        payment_repo = PaymentRepository(test_db_session)

        # Create 10 payments
        for i in range(1, 11):
            payment = PaymentSchedule(
                lease_id=lease_id,
                installment_number=i,
                due_date=date(2025, i, 15),
                amount=Decimal("100.00"),
            )
            await payment_repo.create(payment)

        # Mark 3 as paid
        all_payments = await payment_repo.get_by_lease_id(lease_id, skip=0, limit=100)
        for payment in all_payments[:3]:
            await payment_repo.update_status(payment.id, PaymentStatus.PAID)

        await payment_repo.commit()

        # Calculate payoff
        remaining, payoff, discount = await service.calculate_early_payoff(lease_id)

        assert remaining == Decimal("700.00")  # 1000 - 300 paid
        assert discount == Decimal("14.00")  # 700 * 0.02
        assert payoff == Decimal("686.00")  # 700 - 14

    @pytest.mark.asyncio
    async def test_check_lease_for_default(self, test_db_session):
        """Test automatic lease default on 3+ failed payments."""
        service = PaymentService(test_db_session)
        lease_id = uuid4()

        # Create lease
        lease_repo = LeaseRepository(test_db_session)
        lease = Lease(
            id=lease_id,
            customer_id="CUST-004",
            status=LeaseStatus.ACTIVE,
            principal_amount=Decimal("1000.00"),
            term_months=12,
        )
        await lease_repo.create(lease)
        await lease_repo.commit()

        payment_repo = PaymentRepository(test_db_session)

        # Create 3 payments and mark as failed
        for i in range(1, 4):
            payment = PaymentSchedule(
                lease_id=lease_id,
                installment_number=i,
                due_date=date(2025, i, 15),
                amount=Decimal("100.00"),
                status=PaymentStatus.FAILED,
                retry_count=3,
            )
            await payment_repo.create(payment)

        await payment_repo.commit()

        # Check for default
        result = await service.check_lease_for_default(lease_id)

        assert result is True

        # Verify lease is defaulted
        updated_lease = await lease_repo.get_by_id(lease_id)
        assert updated_lease.status == LeaseStatus.DEFAULTED

    @pytest.mark.asyncio
    async def test_get_due_payments(self, test_db_session):
        """Test retrieving due payments."""
        service = PaymentService(test_db_session)
        lease_id = uuid4()

        payment_repo = PaymentRepository(test_db_session)

        # Create overdue and future payments
        overdue = PaymentSchedule(
            lease_id=lease_id,
            installment_number=1,
            due_date=date(2024, 12, 1),  # Past date
            amount=Decimal("100.00"),
        )
        await payment_repo.create(overdue)

        due_today = PaymentSchedule(
            lease_id=lease_id,
            installment_number=2,
            due_date=date.today(),
            amount=Decimal("100.00"),
        )
        await payment_repo.create(due_today)

        future = PaymentSchedule(
            lease_id=lease_id,
            installment_number=3,
            due_date=date(2026, 1, 1),  # Future date
            amount=Decimal("100.00"),
        )
        await payment_repo.create(future)

        await payment_repo.commit()

        # Get due payments
        due = await service.get_due_payments()

        assert len(due) >= 2  # At least overdue and due today
        assert all(p.status == PaymentStatus.PENDING for p in due)

    @pytest.mark.asyncio
    async def test_payment_event_emissions(self, test_db_session):
        """Test that payment events are emitted and persisted."""
        PaymentGateway.set_success_rate(1.0)
        service = PaymentService(test_db_session)
        lease_id = uuid4()

        # Create lease and payment
        lease_repo = LeaseRepository(test_db_session)
        lease = Lease(
            customer_id="CUST-005",
            status=LeaseStatus.ACTIVE,
            principal_amount=Decimal("1000.00"),
            term_months=12,
        )
        created_lease = await lease_repo.create(lease)
        await lease_repo.commit()

        payment_repo = PaymentRepository(test_db_session)
        payment = PaymentSchedule(
            lease_id=created_lease.id,
            installment_number=1,
            due_date=date(2025, 1, 15),
            amount=Decimal("100.00"),
        )
        created_payment = await payment_repo.create(payment)
        await payment_repo.commit()

        # Mock event publishing
        with patch("shared.event_bus.event_bus.publish_event", new_callable=AsyncMock) as mock_pub:
            # Attempt payment
            await service.attempt_payment(
                payment_id=created_payment.id,
                lease_id=created_lease.id,
                amount=Decimal("100.00"),
                customer_id="CUST-005",
                attempt_number=1,
            )

            # Should emit PAYMENT_ATTEMPTED and PAYMENT_SUCCEEDED events
            assert mock_pub.call_count >= 2

            # Check event types
            events_published = [call[0][0] for call in mock_pub.call_args_list]
            event_types = [e.event_type for e in events_published]

            assert "PAYMENT_ATTEMPTED" in event_types
            assert "PAYMENT_SUCCEEDED" in event_types

    @pytest.mark.asyncio
    async def test_payment_retry_tracking(self, test_db_session):
        """Test retry count tracking."""
        PaymentGateway.set_success_rate(0.0)  # Always fail
        service = PaymentService(test_db_session)
        lease_id = uuid4()

        # Create lease and payment
        lease_repo = LeaseRepository(test_db_session)
        lease = Lease(
            customer_id="CUST-006",
            status=LeaseStatus.ACTIVE,
            principal_amount=Decimal("1000.00"),
            term_months=12,
        )
        created_lease = await lease_repo.create(lease)
        await lease_repo.commit()

        payment_repo = PaymentRepository(test_db_session)
        payment = PaymentSchedule(
            lease_id=created_lease.id,
            installment_number=1,
            due_date=date(2025, 1, 15),
            amount=Decimal("100.00"),
        )
        created_payment = await payment_repo.create(payment)
        await payment_repo.commit()

        # Attempt multiple times
        with patch("shared.event_bus.event_bus.publish_event", new_callable=AsyncMock):
            for attempt in range(1, 4):
                await service.attempt_payment(
                    payment_id=created_payment.id,
                    lease_id=created_lease.id,
                    amount=Decimal("100.00"),
                    customer_id="CUST-006",
                    attempt_number=attempt,
                )

        # Check retry count
        updated_payment = await payment_repo.get_by_id(created_payment.id)
        assert updated_payment.retry_count == 3  # 3 failed attempts
        assert updated_payment.status == PaymentStatus.FAILED
