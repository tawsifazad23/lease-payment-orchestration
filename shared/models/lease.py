from sqlalchemy import Column, String, Numeric, Integer, DateTime, Index, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
from uuid import uuid4
import enum

from shared.database.base import Base


class LeaseStatus(str, enum.Enum):
    """Lease status enumeration."""
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    DEFAULTED = "DEFAULTED"


class Lease(Base):
    """Lease model representing a lease agreement."""

    __tablename__ = "leases"

    # Primary Key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Business Fields
    customer_id = Column(
        String(255),
        nullable=False,
        index=True,
    )

    status = Column(
        SQLEnum(LeaseStatus),
        nullable=False,
        default=LeaseStatus.PENDING,
        index=True,
    )

    principal_amount = Column(
        Numeric(10, 2),
        nullable=False,
    )

    term_months = Column(
        Integer,
        nullable=False,
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
        Index("idx_customer_status", "customer_id", "status"),
    )

    def __repr__(self):
        return f"<Lease(id={self.id}, customer_id={self.customer_id}, status={self.status})>"
