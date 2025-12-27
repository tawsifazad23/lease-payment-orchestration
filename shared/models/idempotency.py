from sqlalchemy import (
    Column, String, DateTime, Index, JSON
)
from datetime import datetime

from shared.database.base import Base


class IdempotencyKey(Base):
    """Idempotency keys for preventing duplicate operations."""

    __tablename__ = "idempotency_keys"

    # Primary Key (the idempotency key itself)
    key = Column(
        String(255),
        primary_key=True,
    )

    # Operation type
    operation = Column(
        String(100),
        nullable=False,
        index=True,
    )

    # Response payload (cached response)
    response_payload = Column(
        JSON,
        nullable=True,
    )

    # Expiration (for cleanup)
    expires_at = Column(
        DateTime,
        nullable=False,
        index=True,
    )

    # Timestamp (when the idempotency key was created)
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    # Indexes
    __table_args__ = (
        Index("idx_operation_created", "operation", "created_at"),
    )

    def __repr__(self):
        return f"<IdempotencyKey(key={self.key}, operation={self.operation})>"
