"""API routes for Ledger Service."""

import logging
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from shared.repositories.lease import LeaseRepository
from shared.repositories.ledger import LedgerRepository
from services.ledger_service.api.schemas import (
    LeaseAuditTrailResponse,
    EventDetailResponse,
    EventTimelineStateResponse,
    AuditMetricsResponse,
    AuditExportResponse,
    ErrorResponse,
    EventTypeListResponse,
)
from services.ledger_service.domain.ledger_service import (
    LedgerQueryService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get(
    "/leases/{lease_id}",
    response_model=LeaseAuditTrailResponse,
    responses={
        200: {"description": "Audit trail retrieved successfully"},
        400: {"description": "Invalid query parameters", "model": ErrorResponse},
        404: {"description": "Lease not found", "model": ErrorResponse},
    },
)
async def get_lease_audit_trail(
    lease_id: UUID,
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    start_date: Optional[datetime] = Query(None, description="Filter start date"),
    end_date: Optional[datetime] = Query(None, description="Filter end date"),
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit"),
    db: AsyncSession = Depends(get_db),
) -> LeaseAuditTrailResponse:
    """
    Get comprehensive audit trail for a lease.

    Returns all events for a lease in chronological order with optional filtering
    by event type and date range.
    """
    try:
        # Validate lease exists
        lease_repo = LeaseRepository(db)
        lease = await lease_repo.get_by_id(lease_id)
        if not lease:
            raise HTTPException(status_code=404, detail="Lease not found")

        # Validate date range
        if start_date and end_date and end_date < start_date:
            raise HTTPException(
                status_code=400, detail="end_date must be after start_date"
            )

        # Query events
        service = LedgerQueryService(db)
        events = await service.get_lease_audit_trail(
            lease_id=lease_id,
            event_type=event_type,
            start_date=start_date,
            end_date=end_date,
            skip=skip,
            limit=limit,
        )

        # Format response
        event_responses = [
            EventDetailResponse(
                event_id=e.id,
                lease_id=e.lease_id,
                event_type=e.event_type,
                timestamp=e.created_at,
                payload=e.event_payload,
                amount=e.amount,
                sequence_number=e.id,
            )
            for e in events
        ]

        earliest = event_responses[0].timestamp if event_responses else None
        latest = event_responses[-1].timestamp if event_responses else None
        event_types = list(set(e.event_type for e in event_responses))

        return LeaseAuditTrailResponse(
            lease_id=lease_id,
            total_events=len(event_responses),
            events=event_responses,
            earliest_event=earliest,
            latest_event=latest,
            event_types_present=event_types,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving audit trail for lease {lease_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve audit trail"
        )


@router.get(
    "/leases/{lease_id}/timeline",
    response_model=List[EventTimelineStateResponse],
    responses={
        200: {"description": "Event timeline retrieved"},
        404: {"description": "Lease not found", "model": ErrorResponse},
    },
)
async def get_event_timeline(
    lease_id: UUID,
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit"),
    db: AsyncSession = Depends(get_db),
) -> List[EventTimelineStateResponse]:
    """
    Get event timeline with state transitions.

    Returns complete sequence of events with state snapshots showing
    what changed at each step.
    """
    try:
        # Validate lease exists
        lease_repo = LeaseRepository(db)
        lease = await lease_repo.get_by_id(lease_id)
        if not lease:
            raise HTTPException(status_code=404, detail="Lease not found")

        # Get timeline
        service = LedgerQueryService(db)
        timeline, total = await service.get_event_timeline(lease_id, skip, limit)

        # Format response
        responses = [
            EventTimelineStateResponse(
                lease_id=lease_id,
                point_in_time=datetime.fromisoformat(event["timestamp"]),
                reconstructed_state=event["state_after"],
                events_before_point=event["sequence"],
                events_after_point=total - event["sequence"],
            )
            for event in timeline
        ]

        return responses

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving timeline for lease {lease_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve timeline"
        )


@router.post(
    "/leases/{lease_id}/state-at-point",
    response_model=EventTimelineStateResponse,
    responses={
        200: {"description": "State reconstructed"},
        400: {"description": "Invalid request", "model": ErrorResponse},
        404: {"description": "Lease not found", "model": ErrorResponse},
    },
)
async def reconstruct_state_at_point(
    lease_id: UUID,
    point_in_time: datetime = Query(..., description="Timestamp to reconstruct state at"),
    db: AsyncSession = Depends(get_db),
) -> EventTimelineStateResponse:
    """
    Reconstruct lease state at specific point in time.

    Uses event sourcing to rebuild the exact state of the lease
    at any historical timestamp.
    """
    try:
        # Validate lease exists
        lease_repo = LeaseRepository(db)
        lease = await lease_repo.get_by_id(lease_id)
        if not lease:
            raise HTTPException(status_code=404, detail="Lease not found")

        # Reconstruct state
        service = LedgerQueryService(db)
        result = await service.reconstruct_state_at_point(lease_id, point_in_time)

        return EventTimelineStateResponse(
            lease_id=lease_id,
            point_in_time=point_in_time,
            reconstructed_state=result["reconstructed_state"],
            events_before_point=result["events_before_point"],
            events_after_point=result["events_after_point"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reconstructing state for lease {lease_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to reconstruct state"
        )


@router.get(
    "/metrics",
    response_model=AuditMetricsResponse,
    responses={
        200: {"description": "Metrics calculated"},
        400: {"description": "Invalid parameters", "model": ErrorResponse},
    },
)
async def get_audit_metrics(
    start_date: Optional[datetime] = Query(None, description="Metrics period start"),
    end_date: Optional[datetime] = Query(None, description="Metrics period end"),
    group_by: str = Query("event_type", description="Grouping strategy"),
    db: AsyncSession = Depends(get_db),
) -> AuditMetricsResponse:
    """
    Get system-wide audit metrics and analytics.

    Returns statistics about events including distribution by type,
    count by date, and events per lease.
    """
    try:
        # Validate date range
        if start_date and end_date and end_date < start_date:
            raise HTTPException(
                status_code=400, detail="end_date must be after start_date"
            )

        # Validate group_by parameter
        valid_group_by = ["event_type", "lease_id", "date"]
        if group_by not in valid_group_by:
            raise HTTPException(
                status_code=400,
                detail=f"group_by must be one of {valid_group_by}",
            )

        # Calculate metrics
        service = LedgerQueryService(db)
        metrics = await service.get_audit_metrics(start_date, end_date)

        return AuditMetricsResponse(
            period_start=start_date,
            period_end=end_date,
            total_events=metrics["total_events"],
            event_type_distribution=metrics["event_type_distribution"],
            event_count_by_date=metrics["event_count_by_date"],
            top_event_types=metrics["top_event_types"],
            events_per_lease=metrics["events_per_lease"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating audit metrics: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to calculate metrics"
        )


@router.get(
    "/leases/{lease_id}/export",
    response_model=AuditExportResponse,
    responses={
        200: {"description": "Export generated"},
        400: {"description": "Invalid parameters", "model": ErrorResponse},
        404: {"description": "Lease not found", "model": ErrorResponse},
    },
)
async def export_audit_trail(
    lease_id: UUID,
    format: str = Query("json", description="Export format: json or csv"),
    include_payload: bool = Query(True, description="Include event payloads"),
    event_types: Optional[str] = Query(None, description="Comma-separated event types"),
    db: AsyncSession = Depends(get_db),
) -> AuditExportResponse:
    """
    Export audit trail as JSON or CSV.

    Generates formatted export of all events for a lease with optional
    filtering by event type.
    """
    try:
        # Validate lease exists
        lease_repo = LeaseRepository(db)
        lease = await lease_repo.get_by_id(lease_id)
        if not lease:
            raise HTTPException(status_code=404, detail="Lease not found")

        # Validate format
        valid_formats = ["json", "csv"]
        if format not in valid_formats:
            raise HTTPException(
                status_code=400, detail=f"format must be one of {valid_formats}"
            )

        # Parse event types filter
        event_types_list = None
        if event_types:
            event_types_list = [t.strip() for t in event_types.split(",")]

        # Export data
        service = LedgerQueryService(db)
        export_data = await service.export_audit_trail(
            lease_id=lease_id,
            format=format,
            include_payload=include_payload,
            event_types=event_types_list,
        )

        # Count events in export
        if format == "json":
            import json
            events = json.loads(export_data)
            event_count = len(events)
        else:
            event_count = export_data.count("\n") - 1  # Subtract header row

        return AuditExportResponse(
            lease_id=lease_id,
            format=format,
            event_count=event_count,
            data=export_data,
            export_timestamp=datetime.utcnow(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting audit trail for lease {lease_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to export audit trail"
        )


@router.get(
    "/event-types",
    response_model=EventTypeListResponse,
    responses={200: {"description": "Event types retrieved"}},
)
async def get_all_event_types(
    db: AsyncSession = Depends(get_db),
) -> EventTypeListResponse:
    """
    Get list of all event types in the system.

    Returns all unique event types that have been recorded.
    """
    try:
        ledger_repo = LedgerRepository(db)
        all_events = await ledger_repo.get_all(skip=0, limit=100000)

        # Extract unique event types
        event_types = sorted(list(set(e.event_type for e in all_events)))

        return EventTypeListResponse(
            event_types=event_types,
            total_types=len(event_types),
        )

    except Exception as e:
        logger.error(f"Error retrieving event types: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve event types"
        )


@router.get(
    "/leases/{lease_id}/event-types",
    response_model=EventTypeListResponse,
    responses={
        200: {"description": "Event types retrieved"},
        404: {"description": "Lease not found", "model": ErrorResponse},
    },
)
async def get_lease_event_types(
    lease_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> EventTypeListResponse:
    """
    Get event types for specific lease.

    Returns all event types recorded for a particular lease.
    """
    try:
        # Validate lease exists
        lease_repo = LeaseRepository(db)
        lease = await lease_repo.get_by_id(lease_id)
        if not lease:
            raise HTTPException(status_code=404, detail="Lease not found")

        # Get lease events
        ledger_repo = LedgerRepository(db)
        events = await ledger_repo.get_lease_history(lease_id, skip=0, limit=10000)

        # Extract unique event types
        event_types = sorted(list(set(e.event_type for e in events)))

        return EventTypeListResponse(
            event_types=event_types,
            total_types=len(event_types),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving event types for lease {lease_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve event types"
        )
