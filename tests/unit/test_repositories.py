"""Unit tests for repository classes."""

import pytest
from datetime import date, datetime, timedelta
from uuid import uuid4
from decimal import Decimal

from shared.models.lease import Lease, LeaseStatus
from shared.models.payment import PaymentSchedule, PaymentStatus
from shared.models.ledger import Ledger
from shared.models.idempotency import IdempotencyKey
from shared.repositories.lease import LeaseRepository
from shared.repositories.payment import PaymentRepository
from shared.repositories.ledger import LedgerRepository
from shared.repositories.idempotency import IdempotencyRepository


class TestLeaseRepository:
    """Test Lease repository operations."""

    @pytest.mark.asyncio
    async def test_create_lease(self, test_db_session):
        """Test creating a lease."""
        repo = LeaseRepository(test_db_session)

        lease = Lease(
            customer_id="CUST-001",
            status=LeaseStatus.PENDING,
            principal_amount=Decimal("3500.00"),
            term_months=12,
        )

        created = await repo.create(lease)
        await repo.commit()

        assert created.id is not None
        assert created.customer_id == "CUST-001"
        assert created.status == LeaseStatus.PENDING

    @pytest.mark.asyncio
    async def test_get_lease_by_id(self, test_db_session):
        """Test retrieving a lease by ID."""
        repo = LeaseRepository(test_db_session)

        lease = Lease(
            customer_id="CUST-001",
            status=LeaseStatus.PENDING,
            principal_amount=Decimal("3500.00"),
            term_months=12,
        )

        created = await repo.create(lease)
        await repo.commit()

        retrieved = await repo.get_by_id(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.customer_id == "CUST-001"

    @pytest.mark.asyncio
    async def test_get_leases_by_customer_id(self, test_db_session):
        """Test retrieving leases by customer ID."""
        repo = LeaseRepository(test_db_session)

        for i in range(3):
            lease = Lease(
                customer_id="CUST-001",
                status=LeaseStatus.PENDING,
                principal_amount=Decimal("3500.00"),
                term_months=12,
            )
            await repo.create(lease)

        await repo.commit()

        leases = await repo.get_by_customer_id("CUST-001")

        assert len(leases) == 3
        assert all(l.customer_id == "CUST-001" for l in leases)

    @pytest.mark.asyncio
    async def test_update_lease_status(self, test_db_session):
        """Test updating lease status."""
        repo = LeaseRepository(test_db_session)

        lease = Lease(
            customer_id="CUST-001",
            status=LeaseStatus.PENDING,
            principal_amount=Decimal("3500.00"),
            term_months=12,
        )

        created = await repo.create(lease)
        await repo.commit()

        updated = await repo.update_status(created.id, LeaseStatus.ACTIVE)

        assert updated is not None
        assert updated.status == LeaseStatus.ACTIVE


class TestPaymentRepository:
    """Test Payment repository operations."""

    @pytest.mark.asyncio
    async def test_create_payment_schedule(self, test_db_session):
        """Test creating a payment schedule."""
        repo = PaymentRepository(test_db_session)
        lease_id = uuid4()

        payment = PaymentSchedule(
            lease_id=lease_id,
            installment_number=1,
            due_date=date.today() + timedelta(days=30),
            amount=Decimal("291.67"),
            status=PaymentStatus.PENDING,
        )

        created = await repo.create(payment)
        await repo.commit()

        assert created.id is not None
        assert created.lease_id == lease_id
        assert created.installment_number == 1

    @pytest.mark.asyncio
    async def test_get_payments_by_lease_id(self, test_db_session):
        """Test retrieving payments by lease ID."""
        repo = PaymentRepository(test_db_session)
        lease_id = uuid4()

        for i in range(1, 4):
            payment = PaymentSchedule(
                lease_id=lease_id,
                installment_number=i,
                due_date=date.today() + timedelta(days=30 * i),
                amount=Decimal("291.67"),
                status=PaymentStatus.PENDING,
            )
            await repo.create(payment)

        await repo.commit()

        payments = await repo.get_by_lease_id(lease_id)

        assert len(payments) == 3
        assert all(p.lease_id == lease_id for p in payments)

    @pytest.mark.asyncio
    async def test_get_due_payments(self, test_db_session):
        """Test retrieving due payments."""
        repo = PaymentRepository(test_db_session)
        lease_id = uuid4()

        # Create overdue payment
        overdue = PaymentSchedule(
            lease_id=lease_id,
            installment_number=1,
            due_date=date.today() - timedelta(days=5),
            amount=Decimal("291.67"),
            status=PaymentStatus.PENDING,
        )
        await repo.create(overdue)

        # Create future payment
        future = PaymentSchedule(
            lease_id=lease_id,
            installment_number=2,
            due_date=date.today() + timedelta(days=30),
            amount=Decimal("291.67"),
            status=PaymentStatus.PENDING,
        )
        await repo.create(future)

        await repo.commit()

        due = await repo.get_due_payments(date.today())

        assert len(due) == 1
        assert due[0].due_date == overdue.due_date

    @pytest.mark.asyncio
    async def test_update_payment_status(self, test_db_session):
        """Test updating payment status."""
        repo = PaymentRepository(test_db_session)
        lease_id = uuid4()

        payment = PaymentSchedule(
            lease_id=lease_id,
            installment_number=1,
            due_date=date.today() + timedelta(days=30),
            amount=Decimal("291.67"),
            status=PaymentStatus.PENDING,
        )

        created = await repo.create(payment)
        await repo.commit()

        updated = await repo.update_status(
            created.id,
            PaymentStatus.PAID,
            retry_count=0,
            last_attempt_at=datetime.utcnow()
        )

        assert updated is not None
        assert updated.status == PaymentStatus.PAID
        assert updated.retry_count == 0


class TestLedgerRepository:
    """Test Ledger repository operations."""

    @pytest.mark.asyncio
    async def test_append_event(self, test_db_session):
        """Test appending an event to ledger."""
        repo = LedgerRepository(test_db_session)
        lease_id = uuid4()

        entry = await repo.append_event(
            lease_id=lease_id,
            event_type="LEASE_CREATED",
            event_payload={"principal": 3500, "term": 12},
            amount=None,
        )
        await repo.commit()

        assert entry.id is not None
        assert entry.lease_id == lease_id
        assert entry.event_type == "LEASE_CREATED"

    @pytest.mark.asyncio
    async def test_get_lease_history(self, test_db_session):
        """Test retrieving lease history."""
        repo = LedgerRepository(test_db_session)
        lease_id = uuid4()

        events = [
            ("LEASE_CREATED", {"principal": 3500}, None),
            ("PAYMENT_SCHEDULED", {"installment": 1}, Decimal("291.67")),
            ("PAYMENT_ATTEMPTED", {"attempt": 1}, None),
        ]

        for event_type, payload, amount in events:
            await repo.append_event(
                lease_id=lease_id,
                event_type=event_type,
                event_payload=payload,
                amount=amount,
            )

        await repo.commit()

        history = await repo.get_lease_history(lease_id)

        assert len(history) == 3
        assert history[0].event_type == "LEASE_CREATED"
        assert history[1].event_type == "PAYMENT_SCHEDULED"

    @pytest.mark.asyncio
    async def test_ledger_immutability(self, test_db_session):
        """Test that ledger cannot be updated or deleted."""
        repo = LedgerRepository(test_db_session)
        lease_id = uuid4()

        entry = await repo.append_event(
            lease_id=lease_id,
            event_type="TEST_EVENT",
            event_payload={},
        )
        await repo.commit()

        # Attempting to update should raise error
        with pytest.raises(NotImplementedError):
            await repo.update(entry.id, event_type="UPDATED")

        # Attempting to delete should raise error
        with pytest.raises(NotImplementedError):
            await repo.delete(entry.id)


class TestIdempotencyRepository:
    """Test Idempotency repository operations."""

    @pytest.mark.asyncio
    async def test_check_and_store_new_key(self, test_db_session):
        """Test storing a new idempotency key."""
        repo = IdempotencyRepository(test_db_session)
        key = "idem-key-123"

        is_duplicate, cached = await repo.check_and_store(
            key=key,
            operation="CREATE_LEASE",
            response_payload={"lease_id": "lease-123"},
        )

        await repo.commit()

        assert is_duplicate is False
        assert cached is None

    @pytest.mark.asyncio
    async def test_check_duplicate_key(self, test_db_session):
        """Test detecting duplicate idempotency key."""
        repo = IdempotencyRepository(test_db_session)
        key = "idem-key-456"

        # First call - new key
        is_duplicate1, cached1 = await repo.check_and_store(
            key=key,
            operation="CREATE_LEASE",
            response_payload={"lease_id": "lease-456"},
        )
        await repo.commit()

        assert is_duplicate1 is False

        # Second call - duplicate
        is_duplicate2, cached2 = await repo.check_and_store(
            key=key,
            operation="CREATE_LEASE",
        )
        await repo.commit()

        assert is_duplicate2 is True
        assert cached2 is not None
        assert cached2["lease_id"] == "lease-456"

    @pytest.mark.asyncio
    async def test_expired_key_cleanup(self, test_db_session):
        """Test that expired keys are cleaned up."""
        repo = IdempotencyRepository(test_db_session)
        key = "idem-key-expired"

        # Store with very short TTL
        is_duplicate, cached = await repo.check_and_store(
            key=key,
            operation="TEST",
            response_payload={"result": "test"},
            ttl_seconds=1,
        )
        await repo.commit()

        assert is_duplicate is False

        # Wait for expiration
        import time
        time.sleep(2)

        # Check again - should be expired and deleted
        is_duplicate2, cached2 = await repo.check_and_store(
            key=key,
            operation="TEST",
        )
        await repo.commit()

        assert is_duplicate2 is False  # Treated as new since expired
        assert cached2 is None

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, test_db_session):
        """Test cleanup of expired keys."""
        repo = IdempotencyRepository(test_db_session)

        # Store multiple keys with short TTL
        for i in range(3):
            await repo.check_and_store(
                key=f"key-{i}",
                operation="TEST",
                ttl_seconds=1,
            )

        await repo.commit()

        # Wait for expiration
        import time
        time.sleep(2)

        # Cleanup
        deleted_count = await repo.cleanup_expired()
        await repo.commit()

        assert deleted_count == 3
