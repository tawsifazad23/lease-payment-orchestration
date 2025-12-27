"""Integration tests for event bus functionality."""

import pytest
import json
import asyncio
from uuid import uuid4
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from shared.events.schemas import (
    LeaseCreatedEvent,
    PaymentScheduledEvent,
    PaymentSucceededEvent,
    PaymentFailedEvent,
)
from shared.event_bus import (
    EventPublisher,
    EventConsumer,
    DeadLetterQueue,
    EventBusManager,
    LEASE_EVENTS_TOPIC,
    PAYMENT_EVENTS_TOPIC,
    DLQ_TOPIC,
)
from shared.retry_manager import RetryConfig, RetryScheduler
from shared.event_persistence import EventPersister


class TestEventPublisher:
    """Test event publishing functionality."""

    @pytest.mark.asyncio
    async def test_publish_event(self, mock_redis):
        """Test publishing an event."""
        publisher = EventPublisher(mock_redis)

        event = LeaseCreatedEvent(
            lease_id=uuid4(),
            customer_id="CUST-001",
            principal_amount=Decimal("3500.00"),
            term_months=12,
        )

        # Mock the publish method
        mock_redis.publish = AsyncMock(return_value=1)

        result = await publisher.publish(event, LEASE_EVENTS_TOPIC)

        assert result is True
        mock_redis.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_event_with_persistence(self, mock_redis):
        """Test publishing and persisting an event."""
        publisher = EventPublisher(mock_redis)

        event = PaymentScheduledEvent(
            payment_id=uuid4(),
            lease_id=uuid4(),
            installment_number=1,
            due_date=date.today(),
            amount=Decimal("291.67"),
        )

        # Mock Redis methods
        mock_redis.publish = AsyncMock(return_value=1)
        mock_redis.setex = AsyncMock(return_value=True)

        result = await publisher.publish_with_persistence(
            event,
            PAYMENT_EVENTS_TOPIC,
            persistence_key="event:payment:123"
        )

        assert result is True
        mock_redis.publish.assert_called_once()
        mock_redis.setex.assert_called_once()


class TestEventConsumer:
    """Test event consuming functionality."""

    @pytest.mark.asyncio
    async def test_register_handler(self, mock_redis):
        """Test registering an event handler."""
        consumer = EventConsumer(mock_redis)

        handler = AsyncMock()
        consumer.register_handler("LEASE_CREATED", handler)

        assert "LEASE_CREATED" in consumer.handlers
        assert handler in consumer.handlers["LEASE_CREATED"]

    @pytest.mark.asyncio
    async def test_handle_message_with_valid_event(self, mock_redis):
        """Test handling a valid event message."""
        consumer = EventConsumer(mock_redis)

        # Register handler
        handler = AsyncMock()
        consumer.register_handler("LEASE_CREATED", handler)

        # Create a test event
        event_data = {
            "event_type": "LEASE_CREATED",
            "event_id": str(uuid4()),
            "lease_id": str(uuid4()),
            "customer_id": "CUST-001",
            "principal_amount": 3500.0,
            "term_months": 12,
            "timestamp": "2025-12-27T12:00:00",
        }

        # Create message
        message = {
            "type": "message",
            "data": json.dumps(event_data),
        }

        # Handle the message
        await consumer._handle_message(message)

        # Handler should be called
        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_message_with_invalid_json(self, mock_redis):
        """Test handling a message with invalid JSON."""
        consumer = EventConsumer(mock_redis)

        message = {
            "type": "message",
            "data": "invalid json {{{",
        }

        # Should not raise, just log error
        await consumer._handle_message(message)


class TestDeadLetterQueue:
    """Test dead letter queue functionality."""

    @pytest.mark.asyncio
    async def test_get_dlq_entries(self, mock_redis):
        """Test retrieving DLQ entries."""
        dlq = DeadLetterQueue(mock_redis)

        dlq_entries = [
            json.dumps({
                "dlq_id": "dlq-1",
                "error": "Handler failed",
                "original_event": {},
            }),
            json.dumps({
                "dlq_id": "dlq-2",
                "error": "Timeout",
                "original_event": {},
            }),
        ]

        mock_redis.lrange = AsyncMock(return_value=dlq_entries)

        entries = await dlq.get_dlq_entries()

        assert len(entries) == 2
        assert entries[0]["dlq_id"] == "dlq-1"
        assert entries[1]["dlq_id"] == "dlq-2"

    @pytest.mark.asyncio
    async def test_acknowledge_dlq_entry(self, mock_redis):
        """Test acknowledging a DLQ entry."""
        dlq = DeadLetterQueue(mock_redis)

        dlq_entry = json.dumps({
            "dlq_id": "dlq-123",
            "error": "Handler failed",
            "original_event": {},
        })

        # Mock the methods
        mock_redis.lrange = AsyncMock(return_value=[dlq_entry])
        mock_redis.lrem = AsyncMock(return_value=1)

        result = await dlq.acknowledge("dlq-123")

        assert result is True
        mock_redis.lrem.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_dlq_count(self, mock_redis):
        """Test getting DLQ count."""
        dlq = DeadLetterQueue(mock_redis)

        mock_redis.llen = AsyncMock(return_value=5)

        count = await dlq.get_dlq_count()

        assert count == 5

    @pytest.mark.asyncio
    async def test_clear_dlq(self, mock_redis):
        """Test clearing DLQ."""
        dlq = DeadLetterQueue(mock_redis)

        mock_redis.delete = AsyncMock(return_value=1)

        result = await dlq.clear_dlq()

        assert result is True
        mock_redis.delete.assert_called_once()


class TestRetryScheduler:
    """Test retry scheduler with exponential backoff."""

    def test_calculate_delay_exponential_backoff(self):
        """Test exponential backoff calculation."""
        config = RetryConfig(
            max_retries=3,
            base_delay_seconds=60,
            backoff_multiplier=2.0,
            jitter=False,  # Disable jitter for predictable results
        )

        scheduler = RetryScheduler(config)

        # First attempt: 60 seconds
        delay1 = config.calculate_delay(0)
        assert delay1 == 60

        # Second attempt: 120 seconds
        delay2 = config.calculate_delay(1)
        assert delay2 == 120

        # Third attempt: 240 seconds
        delay3 = config.calculate_delay(2)
        assert delay3 == 240

    def test_calculate_delay_with_max_cap(self):
        """Test that delay is capped at max_delay."""
        config = RetryConfig(
            max_retries=5,
            base_delay_seconds=1000,
            max_delay_seconds=3600,
            backoff_multiplier=2.0,
            jitter=False,
        )

        # This would be 1000 * 2^5 = 32000, but should be capped at 3600
        delay = config.calculate_delay(5)
        assert delay == 3600

    def test_get_retry_schedule(self):
        """Test getting a full retry schedule."""
        config = RetryConfig(
            max_retries=3,
            base_delay_seconds=60,
            backoff_multiplier=2.0,
            jitter=False,
        )

        scheduler = RetryScheduler(config)
        schedule = scheduler.get_retry_schedule(max_attempts=3)

        assert len(schedule) == 3
        assert schedule[0] == (1, 60)
        assert schedule[1] == (2, 120)
        assert schedule[2] == (3, 240)

    @pytest.mark.asyncio
    async def test_retry_with_backoff_success(self):
        """Test retry succeeds on first attempt."""
        config = RetryConfig(max_retries=3)
        scheduler = RetryScheduler(config)

        async_func = AsyncMock(return_value="success")

        result = await scheduler.retry_with_backoff(async_func, arg1="test")

        assert result == "success"
        async_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_with_backoff_succeeds_after_retries(self):
        """Test retry succeeds after multiple attempts."""
        config = RetryConfig(
            max_retries=2,
            base_delay_seconds=0.01,  # Very short for testing
            backoff_multiplier=1.0,
        )
        scheduler = RetryScheduler(config)

        # Fail twice, then succeed
        async_func = AsyncMock(
            side_effect=[
                Exception("First attempt failed"),
                Exception("Second attempt failed"),
                "success",
            ]
        )

        result = await scheduler.retry_with_backoff(async_func)

        assert result == "success"
        assert async_func.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        """Test all retries exhausted."""
        config = RetryConfig(
            max_retries=2,
            base_delay_seconds=0.01,
        )
        scheduler = RetryScheduler(config)

        async_func = AsyncMock(side_effect=ValueError("Always fails"))

        with pytest.raises(ValueError, match="Always fails"):
            await scheduler.retry_with_backoff(async_func)

        assert async_func.call_count == 3  # Initial + 2 retries


class TestEventPersistence:
    """Test event persistence to ledger."""

    @pytest.mark.asyncio
    async def test_persist_lease_created_event(self, test_db_session):
        """Test persisting a LEASE_CREATED event."""
        persister = EventPersister(test_db_session)

        lease_id = uuid4()
        event = LeaseCreatedEvent(
            lease_id=lease_id,
            customer_id="CUST-001",
            principal_amount=Decimal("3500.00"),
            term_months=12,
        )

        entry_id = await persister.persist_lease_created(event)

        assert entry_id is not None
        assert isinstance(entry_id, int)

        # Verify in ledger
        from shared.repositories.ledger import LedgerRepository
        repo = LedgerRepository(test_db_session)
        history = await repo.get_lease_history(lease_id)

        assert len(history) == 1
        assert history[0].event_type == "LEASE_CREATED"
        assert history[0].lease_id == lease_id

    @pytest.mark.asyncio
    async def test_persist_payment_succeeded_event(self, test_db_session):
        """Test persisting a PAYMENT_SUCCEEDED event."""
        persister = EventPersister(test_db_session)

        lease_id = uuid4()
        event = PaymentSucceededEvent(
            payment_id=uuid4(),
            lease_id=lease_id,
            amount=Decimal("291.67"),
            ledger_entry_id=1,
        )

        entry_id = await persister.persist_payment_succeeded(event)

        assert entry_id is not None

        # Verify amount is captured
        from shared.repositories.ledger import LedgerRepository
        repo = LedgerRepository(test_db_session)
        history = await repo.get_lease_history(lease_id)

        assert len(history) == 1
        assert history[0].amount == Decimal("291.67")

    @pytest.mark.asyncio
    async def test_persist_event_rollback_on_error(self, test_db_session):
        """Test that transaction rolls back on error."""
        persister = EventPersister(test_db_session)
        lease_id = uuid4()

        event = LeaseCreatedEvent(
            lease_id=lease_id,
            customer_id="CUST-001",
            principal_amount=Decimal("3500.00"),
            term_months=12,
        )

        # Mock the repo.append_event to raise an error
        with patch.object(persister.repo, 'append_event', side_effect=Exception("Test error")):
            # Should raise an error and rollback
            with pytest.raises(Exception):
                await persister.persist_event(event, lease_id)
