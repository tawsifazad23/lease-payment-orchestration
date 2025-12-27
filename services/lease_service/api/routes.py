"""Lease API routes."""

import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from services.lease_service.domain.lease_service import LeaseService
from services.lease_service.api.schemas import (
    CreateLeaseRequest,
    CreateLeaseResponse,
    LeaseResponse,
    LeaseHistoryResponse,
    LeaseHistoryEvent,
    PaymentScheduleResponse,
    EarlyPayoffRequest,
    EarlyPayoffResponse,
    ErrorResponse,
)
from shared.models.payment import PaymentStatus

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/leases",
    tags=["leases"],
)


@router.post(
    "",
    response_model=CreateLeaseResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def create_lease(
    request: CreateLeaseRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
) -> CreateLeaseResponse:
    """
    Create a new lease with payment schedule.

    The Idempotency-Key header prevents duplicate lease creation.
    If the same key is used twice, the first response is returned.

    Args:
        request: Lease creation request
        idempotency_key: Unique key for idempotency
        db: Database session

    Returns:
        Created lease with payment schedule

    Raises:
        400: If input validation fails
        409: If idempotency key conflict
    """
    try:
        service = LeaseService(db)

        lease, payments = await service.create_lease(
            customer_id=request.customer_id,
            principal_amount=request.principal_amount,
            term_months=request.term_months,
            idempotency_key=idempotency_key,
        )

        # Format payment schedule
        payment_schedule = [
            PaymentScheduleResponse(
                payment_id=p.id,
                installment_number=p.installment_number,
                due_date=p.due_date,
                amount=p.amount,
                status=p.status.value,
            )
            for p in payments
        ]

        logger.info(
            f"Lease created: {lease.id} for customer {request.customer_id}",
            extra={"lease_id": str(lease.id)},
        )

        return CreateLeaseResponse(
            lease_id=lease.id,
            status=lease.status.value,
            customer_id=lease.customer_id,
            principal_amount=lease.principal_amount,
            term_months=lease.term_months,
            payment_schedule=payment_schedule,
            created_at=lease.created_at,
        )

    except ValueError as e:
        logger.warning(f"Validation error creating lease: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    except Exception as e:
        logger.error(f"Error creating lease: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create lease",
        )


@router.get(
    "/{lease_id}",
    response_model=LeaseResponse,
    responses={
        404: {"model": ErrorResponse},
    },
)
async def get_lease(
    lease_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> LeaseResponse:
    """
    Get a lease by ID.

    Args:
        lease_id: ID of the lease
        db: Database session

    Returns:
        Lease details

    Raises:
        404: If lease not found
    """
    try:
        service = LeaseService(db)
        lease = await service.get_lease(lease_id)

        if lease is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lease not found: {lease_id}",
            )

        return LeaseResponse(
            lease_id=lease.id,
            customer_id=lease.customer_id,
            status=lease.status.value,
            principal_amount=lease.principal_amount,
            term_months=lease.term_months,
            created_at=lease.created_at,
            updated_at=lease.updated_at,
        )

    except Exception as e:
        logger.error(f"Error retrieving lease {lease_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve lease",
        )


@router.get(
    "/{lease_id}/history",
    response_model=LeaseHistoryResponse,
    responses={
        404: {"model": ErrorResponse},
    },
)
async def get_lease_history(
    lease_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> LeaseHistoryResponse:
    """
    Get complete audit trail for a lease.

    Returns chronological history of all events affecting the lease.

    Args:
        lease_id: ID of the lease
        db: Database session

    Returns:
        Lease with event history

    Raises:
        404: If lease not found
    """
    try:
        from shared.repositories.ledger import LedgerRepository

        service = LeaseService(db)
        lease = await service.get_lease(lease_id)

        if lease is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lease not found: {lease_id}",
            )

        # Get event history
        ledger_repo = LedgerRepository(db)
        events = await ledger_repo.get_lease_history(lease_id)

        # Format events
        event_list = [
            LeaseHistoryEvent(
                event_id=e.id,
                event_type=e.event_type,
                timestamp=e.created_at,
                payload=e.event_payload,
                amount=e.amount,
            )
            for e in events
        ]

        logger.info(
            f"Retrieved lease history: {lease_id} ({len(event_list)} events)",
            extra={"lease_id": str(lease_id)},
        )

        return LeaseHistoryResponse(
            lease_id=lease.id,
            customer_id=lease.customer_id,
            status=lease.status.value,
            events=event_list,
        )

    except Exception as e:
        logger.error(f"Error retrieving lease history {lease_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve lease history",
        )
