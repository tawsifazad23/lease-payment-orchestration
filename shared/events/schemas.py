"""Event schemas for the lease payment system."""

from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, date
from uuid import UUID
from decimal import Decimal
from typing import Optional


class BaseEvent(BaseModel):
    """Base event schema with common fields."""

    model_config = ConfigDict(json_encoders={
        UUID: str,
        Decimal: float,
        datetime: lambda v: v.isoformat(),
    })

    event_id: str = Field(default_factory=lambda: str(UUID('00000000-0000-0000-0000-000000000000')))
    event_type: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class LeaseCreatedEvent(BaseEvent):
    """Event emitted when a lease is created."""

    event_type: str = Field(default="LEASE_CREATED")
    lease_id: UUID
    customer_id: str
    principal_amount: Decimal
    term_months: int


class PaymentScheduledEvent(BaseEvent):
    """Event emitted when a payment is scheduled."""

    event_type: str = Field(default="PAYMENT_SCHEDULED")
    payment_id: UUID
    lease_id: UUID
    installment_number: int
    due_date: date
    amount: Decimal


class PaymentAttemptedEvent(BaseEvent):
    """Event emitted when a payment is attempted."""

    event_type: str = Field(default="PAYMENT_ATTEMPTED")
    payment_id: UUID
    lease_id: UUID
    attempt_number: int
    scheduled_retry: bool = False


class PaymentSucceededEvent(BaseEvent):
    """Event emitted when a payment succeeds."""

    event_type: str = Field(default="PAYMENT_SUCCEEDED")
    payment_id: UUID
    lease_id: UUID
    amount: Decimal
    ledger_entry_id: int


class PaymentFailedEvent(BaseEvent):
    """Event emitted when a payment fails."""

    event_type: str = Field(default="PAYMENT_FAILED")
    payment_id: UUID
    lease_id: UUID
    reason: str
    retry_scheduled: bool
    next_retry_at: Optional[datetime] = None
    attempt_number: int


class LeaseCompletedEvent(BaseEvent):
    """Event emitted when a lease is completed."""

    event_type: str = Field(default="LEASE_COMPLETED")
    lease_id: UUID
    customer_id: str
    completion_date: datetime = Field(default_factory=datetime.utcnow)
    total_paid: Decimal
