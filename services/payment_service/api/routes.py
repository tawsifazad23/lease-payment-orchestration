"""Payment API routes."""

import logging
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from services.payment_service.domain.payment_service import PaymentService
from services.payment_service.api.schemas import (
    ProcessPaymentRequest,
    ProcessPaymentResponse,
    PaymentResponse,
    LeasePaymentsResponse,
    EarlyPayoffRequest,
    EarlyPayoffResponse,
    DuePaymentsResponse,
    ErrorResponse,
)
from shared.models.payment import PaymentStatus

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1",
    tags=["payments"],
)


@router.post(
    "/payments/{payment_id}/attempt",
    response_model=ProcessPaymentResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def attempt_payment(
    payment_id: UUID,
    request: ProcessPaymentRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
) -> ProcessPaymentResponse:
    """
    Attempt to process a payment.

    Args:
        payment_id: ID of the payment to process
        request: Payment request
        idempotency_key: Unique key for idempotency
        db: Database session

    Returns:
        Payment status

    Raises:
        404: If payment not found
        400: If payment already paid or cancelled
    """
    try:
        service = PaymentService(db)

        # Get payment
        payment = await service.get_payment(payment_id)

        if payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Payment not found: {payment_id}",
            )

        # Check if already paid
        if payment.status == PaymentStatus.PAID:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Payment already paid: {payment_id}",
            )

        # Check if cancelled
        if payment.status == PaymentStatus.CANCELLED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Payment cancelled: {payment_id}",
            )

        # Get lease for customer info
        lease = await service.lease_repo.get_by_id(payment.lease_id)

        if lease is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lease not found: {payment.lease_id}",
            )

        # Attempt payment
        status_result, reason = await service.attempt_payment(
            payment_id=payment_id,
            lease_id=payment.lease_id,
            amount=payment.amount,
            customer_id=lease.customer_id,
            attempt_number=payment.retry_count + 1,
        )

        logger.info(
            f"Payment processed: {payment_id} - {status_result}",
            extra={
                "payment_id": str(payment_id),
                "lease_id": str(payment.lease_id),
                "status": str(status_result),
            },
        )

        return ProcessPaymentResponse(
            payment_id=payment_id,
            lease_id=payment.lease_id,
            status=status_result.value,
            attempt_number=payment.retry_count + 1,
            amount=payment.amount,
            processed_at=datetime.utcnow(),
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error processing payment {payment_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process payment",
        )


@router.get(
    "/leases/{lease_id}/payments",
    response_model=LeasePaymentsResponse,
    responses={
        404: {"model": ErrorResponse},
    },
)
async def get_lease_payments(
    lease_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> LeasePaymentsResponse:
    """
    Get all payments for a lease.

    Args:
        lease_id: ID of the lease
        db: Database session

    Returns:
        Lease payments summary

    Raises:
        404: If lease not found
    """
    try:
        service = PaymentService(db)

        # Verify lease exists
        lease = await service.lease_repo.get_by_id(lease_id)

        if lease is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lease not found: {lease_id}",
            )

        # Get payments
        payments = await service.get_lease_payments(lease_id)

        # Calculate totals
        total_scheduled = sum(p.amount for p in payments)
        total_paid = sum(
            p.amount for p in payments if p.status == PaymentStatus.PAID
        )
        remaining = total_scheduled - total_paid

        # Format response
        payment_responses = [
            PaymentResponse(
                payment_id=p.id,
                lease_id=p.lease_id,
                installment_number=p.installment_number,
                due_date=p.due_date,
                amount=p.amount,
                status=p.status.value,
                retry_count=p.retry_count,
                last_attempt_at=p.last_attempt_at,
                created_at=p.created_at,
                updated_at=p.updated_at,
            )
            for p in payments
        ]

        logger.info(
            f"Retrieved {len(payments)} payments for lease {lease_id}",
            extra={"lease_id": str(lease_id)},
        )

        return LeasePaymentsResponse(
            lease_id=lease_id,
            payments=payment_responses,
            total_scheduled=total_scheduled,
            total_paid=total_paid,
            remaining_balance=remaining,
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error retrieving lease payments {lease_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve payments",
        )


@router.post(
    "/leases/{lease_id}/payoff",
    response_model=EarlyPayoffResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def process_early_payoff(
    lease_id: UUID,
    request: EarlyPayoffRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
) -> EarlyPayoffResponse:
    """
    Process early payoff for a lease.

    Applies 2% discount and completes the lease.

    Args:
        lease_id: ID of the lease
        request: Payoff request
        idempotency_key: Unique key for idempotency
        db: Database session

    Returns:
        Early payoff details

    Raises:
        404: If lease not found
        400: If lease not in valid state
    """
    try:
        service = PaymentService(db)

        # Get lease
        lease = await service.lease_repo.get_by_id(lease_id)

        if lease is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lease not found: {lease_id}",
            )

        # Check lease status
        from shared.models.lease import LeaseStatus

        if lease.status not in [LeaseStatus.ACTIVE, LeaseStatus.PENDING]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot payoff lease in status: {lease.status}",
            )

        # Process early payoff
        remaining, payoff_amount, discount_amount, txn_id = (
            await service.process_early_payoff(lease_id, lease.customer_id)
        )

        logger.info(
            f"Early payoff processed: {lease_id} - ${payoff_amount} "
            f"(discount: ${discount_amount})",
            extra={"lease_id": str(lease_id)},
        )

        return EarlyPayoffResponse(
            lease_id=lease_id,
            remaining_balance=remaining,
            payoff_amount=payoff_amount,
            discount_applied=discount_amount,
            discount_percent=2.0,
            transaction_id=txn_id,
            processed_at=datetime.utcnow(),
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error processing early payoff {lease_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process early payoff",
        )


@router.get(
    "/payments/due",
    response_model=DuePaymentsResponse,
    responses={
        400: {"model": ErrorResponse},
    },
)
async def get_due_payments(
    db: AsyncSession = Depends(get_db),
) -> DuePaymentsResponse:
    """
    Get all payments that are currently due.

    Returns:
        List of due payments

    Raises:
        400: If query fails
    """
    try:
        service = PaymentService(db)

        # Get due payments
        payments = await service.get_due_payments()

        # Calculate total
        total_due = sum(p.amount for p in payments)

        # Format response
        payment_responses = [
            PaymentResponse(
                payment_id=p.id,
                lease_id=p.lease_id,
                installment_number=p.installment_number,
                due_date=p.due_date,
                amount=p.amount,
                status=p.status.value,
                retry_count=p.retry_count,
                last_attempt_at=p.last_attempt_at,
                created_at=p.created_at,
                updated_at=p.updated_at,
            )
            for p in payments
        ]

        logger.info(
            f"Retrieved {len(payments)} due payments (${total_due} total)",
            extra={"count": len(payments), "total": float(total_due)},
        )

        return DuePaymentsResponse(
            payments=payment_responses,
            total_due=total_due,
            count=len(payments),
        )

    except Exception as e:
        logger.error(f"Error retrieving due payments: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve due payments",
        )
