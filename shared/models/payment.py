from sqlalchemy import (
    Column, String, Numeric, Integer, DateTime, Date, Index,
    Enum as SQLEnum, ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, date
from uuid import uuid4
import enum

from shared.database.base import Base


class PaymentStatus(str, enum.Enum):
    """Payment status enumeration."""
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PaymentSchedule(Base):
    """Payment schedule model representing individual installments."""

    __tablename__ = "payment_schedule"

    # Primary Key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Foreign Key
    lease_id = Column(
        UUID(as_uuid=True),
        ForeignKey("leases.id"),
        nullable=False,
        index=True,
    )

    # Business Fields
    installment_number = Column(
        Integer,
        nullable=False,
    )

    due_date = Column(
        Date,
        nullable=False,
        index=True,
    )

    amount = Column(
        Numeric(10, 2),
        nullable=False,
    )

    status = Column(
        SQLEnum(PaymentStatus),
        nullable=False,
        default=PaymentStatus.PENDING,
        index=True,
    )

    # Retry Tracking
    retry_count = Column(
        Integer,
        nullable=False,
        default=0,
    )

    last_attempt_at = Column(
        DateTime,
        nullable=True,
    )

    # Timestamps
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Indexes
    __table_args__ = (
        Index("idx_lease_status", "lease_id", "status"),
        Index("idx_due_date_status", "due_date", "status"),
    )

    def __repr__(self):
        return f"<PaymentSchedule(id={self.id}, lease_id={self.lease_id}, installment={self.installment_number})>"
