"""Request/response schemas for Lease API."""

from pydantic import BaseModel, Field, validator
from uuid import UUID
from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional

from shared.models.lease import LeaseStatus


class CreateLeaseRequest(BaseModel):
    """Request to create a new lease."""

    customer_id: str = Field(..., min_length=1, max_length=255)
    principal_amount: Decimal = Field(..., gt=0, decimal_places=2)
    term_months: int = Field(..., ge=1, le=60)

    @validator("principal_amount", pre=True)
    def validate_principal(cls, v):
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        return v


class PaymentScheduleResponse(BaseModel):
    """Response schema for a payment in schedule."""

    payment_id: UUID
    installment_number: int
    due_date: date
    amount: Decimal
    status: str

    class Config:
        from_attributes = True


class LeaseResponse(BaseModel):
    """Response schema for a lease."""

    lease_id: UUID
    customer_id: str
    status: str
    principal_amount: Decimal
    term_months: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CreateLeaseResponse(BaseModel):
    """Response when creating a lease."""

    lease_id: UUID
    status: str
    customer_id: str
    principal_amount: Decimal
    term_months: int
    payment_schedule: List[PaymentScheduleResponse]
    created_at: datetime

    class Config:
        from_attributes = True


class LeaseHistoryEvent(BaseModel):
    """Event from lease history."""

    event_id: int
    event_type: str
    timestamp: datetime
    payload: dict
    amount: Optional[Decimal] = None

    class Config:
        from_attributes = True


class LeaseHistoryResponse(BaseModel):
    """Response for lease audit trail."""

    lease_id: UUID
    customer_id: str
    status: str
    events: List[LeaseHistoryEvent]

    class Config:
        from_attributes = True


class EarlyPayoffRequest(BaseModel):
    """Request for early payoff."""

    pass  # No body needed


class EarlyPayoffResponse(BaseModel):
    """Response for early payoff."""

    lease_id: UUID
    remaining_balance: Decimal
    payoff_amount: Decimal
    discount_applied: Decimal
    discount_percent: Decimal

    class Config:
        from_attributes = True


class ErrorResponse(BaseModel):
    """Error response."""

    detail: str
    error_code: Optional[str] = None

    class Config:
        from_attributes = True
