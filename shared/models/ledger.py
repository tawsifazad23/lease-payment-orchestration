from sqlalchemy import (
    Column, String, Numeric, DateTime, Index, JSON, Integer, ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID, BIGINT
from datetime import datetime
from uuid import uuid4

from shared.database.base import Base


class Ledger(Base):
    """Append-only ledger for immutable event history."""

    __tablename__ = "ledger"

    # Primary Key (auto-incrementing for ordering)
    # Use Integer for SQLite compatibility, BIGINT for PostgreSQL
    id = Column(
        Integer().with_variant(BIGINT(), "postgresql"),
        primary_key=True,
        autoincrement=True,
    )

    # Foreign Key
    lease_id = Column(
        UUID(as_uuid=True),
        ForeignKey("leases.id"),
        nullable=False,
        index=True,
    )

    # Event Information
    event_type = Column(
        String(50),
        nullable=False,
        index=True,
    )

    event_payload = Column(
        JSON,
        nullable=False,
    )

    # Amount (if applicable to this event)
    amount = Column(
        Numeric(10, 2),
        nullable=True,
    )

    # Timestamp (when event occurred, NOT when it was recorded)
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    # Indexes
    __table_args__ = (
        Index("idx_lease_events", "lease_id", "created_at"),
        Index("idx_event_type_created", "event_type", "created_at"),
    )

    def __repr__(self):
        return f"<Ledger(id={self.id}, lease_id={self.lease_id}, event_type={self.event_type})>"
