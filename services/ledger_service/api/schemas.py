"""Schemas for Ledger Service API endpoints."""

from pydantic import BaseModel, Field, validator
from datetime import datetime, date
from uuid import UUID
from decimal import Decimal
from typing import Optional, List, Dict, Any


class EventDetailResponse(BaseModel):
    """Response model for individual event detail."""

    event_id: int = Field(..., description="Unique event ID (sequence number)")
    lease_id: UUID = Field(..., description="Associated lease ID")
    event_type: str = Field(..., description="Type of event (e.g., LEASE_CREATED)")
    timestamp: datetime = Field(..., description="When event occurred")
    payload: Dict[str, Any] = Field(..., description="Full event payload")
    amount: Optional[Decimal] = Field(None, description="Monetary amount if applicable")
    sequence_number: int = Field(..., description="Event sequence for ordering")

    class Config:
        json_encoders = {
            UUID: str,
            Decimal: float,
            datetime: lambda v: v.isoformat(),
        }


class LeaseAuditTrailResponse(BaseModel):
    """Response model for complete lease audit trail."""

    lease_id: UUID = Field(..., description="Lease ID")
    total_events: int = Field(..., description="Total number of events")
    events: List[EventDetailResponse] = Field(..., description="List of events in order")
    earliest_event: Optional[datetime] = Field(None, description="First event timestamp")
    latest_event: Optional[datetime] = Field(None, description="Last event timestamp")
    event_types_present: List[str] = Field(..., description="Event types found in history")

    class Config:
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat() if v else None,
        }


class EventTimelineStateResponse(BaseModel):
    """Response model for state at specific point in time."""

    lease_id: UUID = Field(..., description="Lease ID")
    point_in_time: datetime = Field(..., description="Timestamp for state reconstruction")
    reconstructed_state: Dict[str, Any] = Field(..., description="Reconstructed lease state")
    events_before_point: int = Field(..., description="Number of events before point")
    events_after_point: int = Field(..., description="Number of events after point")

    class Config:
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat(),
        }


class AuditMetricsResponse(BaseModel):
    """Response model for audit metrics and analytics."""

    period_start: Optional[datetime] = Field(None, description="Start of metrics period")
    period_end: Optional[datetime] = Field(None, description="End of metrics period")
    total_events: int = Field(..., description="Total events in period")
    event_type_distribution: Dict[str, int] = Field(
        ..., description="Count of events by type"
    )
    event_count_by_date: Dict[str, int] = Field(
        ..., description="Count of events by date"
    )
    top_event_types: List[tuple] = Field(..., description="Top 10 event types by count")
    events_per_lease: Dict[str, int] = Field(..., description="Events grouped by lease")

    class Config:
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat() if v else None,
        }


class AuditExportResponse(BaseModel):
    """Response model for audit trail export."""

    lease_id: UUID = Field(..., description="Lease ID")
    format: str = Field(..., description="Export format (json or csv)")
    event_count: int = Field(..., description="Number of events exported")
    data: str = Field(..., description="Exported data as JSON string or CSV")
    export_timestamp: datetime = Field(..., description="When export was generated")

    class Config:
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat(),
        }


class ErrorResponse(BaseModel):
    """Error response model."""

    detail: str = Field(..., description="Error message")
    error_code: Optional[str] = Field(None, description="Error code")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


# Request Models


class LeaseHistoryQueryRequest(BaseModel):
    """Query parameters for lease history."""

    event_type: Optional[str] = Field(None, description="Filter by event type")
    start_date: Optional[datetime] = Field(None, description="Filter start date")
    end_date: Optional[datetime] = Field(None, description="Filter end date")
    skip: int = Field(0, ge=0, description="Pagination offset")
    limit: int = Field(100, ge=1, le=1000, description="Pagination limit")

    @validator("end_date", pre=False, always=True)
    def validate_date_range(cls, v, values):
        """Ensure end_date is after start_date."""
        if v and "start_date" in values and values["start_date"]:
            if v < values["start_date"]:
                raise ValueError("end_date must be after start_date")
        return v


class EventTimelineRequest(BaseModel):
    """Request for state reconstruction at point in time."""

    point_in_time: datetime = Field(..., description="Timestamp to reconstruct state at")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class AuditMetricsRequest(BaseModel):
    """Query parameters for audit metrics."""

    start_date: Optional[datetime] = Field(None, description="Metrics period start")
    end_date: Optional[datetime] = Field(None, description="Metrics period end")
    group_by: str = Field(
        "event_type",
        description="Grouping strategy: event_type, lease_id, or date",
    )

    @validator("end_date", pre=False, always=True)
    def validate_date_range(cls, v, values):
        """Ensure end_date is after start_date."""
        if v and "start_date" in values and values["start_date"]:
            if v < values["start_date"]:
                raise ValueError("end_date must be after start_date")
        return v

    @validator("group_by")
    def validate_group_by(cls, v):
        """Ensure group_by is valid."""
        valid_options = ["event_type", "lease_id", "date"]
        if v not in valid_options:
            raise ValueError(f"group_by must be one of {valid_options}")
        return v


class ExportAuditTrailRequest(BaseModel):
    """Request parameters for audit trail export."""

    format: str = Field("json", description="Export format: json or csv")
    include_payload: bool = Field(True, description="Include event payloads")
    event_types: Optional[List[str]] = Field(None, description="Filter by event types")

    @validator("format")
    def validate_format(cls, v):
        """Ensure format is valid."""
        valid_formats = ["json", "csv"]
        if v not in valid_formats:
            raise ValueError(f"format must be one of {valid_formats}")
        return v


class EventTypeListResponse(BaseModel):
    """Response for event type list."""

    event_types: List[str] = Field(..., description="List of event types")
    total_types: int = Field(..., description="Total number of event types")

    class Config:
        pass
