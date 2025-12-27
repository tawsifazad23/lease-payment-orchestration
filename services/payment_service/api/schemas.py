"""Request/response schemas for Payment API."""

from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from shared.models.payment import PaymentStatus


class ProcessPaymentRequest(BaseModel):
    """Request to process a payment."""

    pass  # No body required


class PaymentResponse(BaseModel):
    """Response for a payment."""

    payment_id: UUID
    lease_id: UUID
    installment_number: int
    due_date: date
    amount: Decimal
    status: str
    retry_count: int
    last_attempt_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProcessPaymentResponse(BaseModel):
    """Response when processing a payment."""

    payment_id: UUID
    lease_id: UUID
    status: str
    attempt_number: int
    amount: Decimal
    processed_at: datetime

    class Config:
        from_attributes = True


class LeasePaymentsResponse(BaseModel):
    """Response for lease payments."""

    lease_id: UUID
    payments: list[PaymentResponse]
    total_scheduled: Decimal
    total_paid: Decimal
    remaining_balance: Decimal

    class Config:
        from_attributes = True


class EarlyPayoffRequest(BaseModel):
    """Request for early payoff."""

    pass  # No body required


class EarlyPayoffResponse(BaseModel):
    """Response for early payoff."""

    lease_id: UUID
    remaining_balance: Decimal
    payoff_amount: Decimal
    discount_applied: Decimal
    discount_percent: Decimal
    transaction_id: str
    processed_at: datetime

    class Config:
        from_attributes = True


class DuePaymentsResponse(BaseModel):
    """Response for due payments."""

    payments: list[PaymentResponse]
    total_due: Decimal
    count: int

    class Config:
        from_attributes = True


class ErrorResponse(BaseModel):
    """Error response."""

    detail: str
    error_code: Optional[str] = None

    class Config:
        from_attributes = True
