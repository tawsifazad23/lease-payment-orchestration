"""Celery tasks for payment retries."""

import logging
from uuid import UUID
from decimal import Decimal
from datetime import datetime

from shared.celery_app import celery_app
from shared.database import SessionLocal
from services.payment_service.domain.payment_service import PaymentService

logger = logging.getLogger(__name__)


@celery_app.task(
    name="payment.retry_failed_payment",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 1},
    retry_backoff=True,
)
async def retry_failed_payment(
    payment_id: str,
    lease_id: str,
    amount: float,
    customer_id: str,
    attempt_number: int,
) -> dict:
    """
    Retry a failed payment.

    Args:
        payment_id: ID of the payment
        lease_id: ID of the lease
        amount: Amount to charge
        customer_id: Customer identifier
        attempt_number: Retry attempt number

    Returns:
        Dict with result information
    """
    payment_id_uuid = UUID(payment_id)
    lease_id_uuid = UUID(lease_id)
    amount_decimal = Decimal(str(amount))

    try:
        # Get a database session
        async with SessionLocal() as session:
            service = PaymentService(session)

            logger.info(
                f"Retrying payment {payment_id} (attempt {attempt_number})",
                extra={
                    "payment_id": payment_id,
                    "lease_id": lease_id,
                    "attempt": attempt_number,
                },
            )

            # Attempt payment
            status, reason = await service.attempt_payment(
                payment_id=payment_id_uuid,
                lease_id=lease_id_uuid,
                amount=amount_decimal,
                customer_id=customer_id,
                attempt_number=attempt_number,
            )

            if str(status) == "PaymentStatus.PAID":
                logger.info(
                    f"Payment retry succeeded: {payment_id}",
                    extra={"payment_id": payment_id},
                )

                return {
                    "status": "success",
                    "payment_id": payment_id,
                    "message": "Payment succeeded on retry",
                }

            else:
                # Schedule next retry if applicable
                if attempt_number < 3:
                    logger.info(
                        f"Payment retry failed, scheduling next attempt: {payment_id}",
                        extra={"payment_id": payment_id},
                    )

                    # Calculate delay for next retry
                    if attempt_number == 1:
                        # 6 minutes after first failure
                        delay_seconds = 360
                    elif attempt_number == 2:
                        # 36 minutes after second failure
                        delay_seconds = 2160
                    else:
                        # 1 hour after third failure
                        delay_seconds = 3600

                    retry_failed_payment.apply_async(
                        args=[
                            payment_id,
                            lease_id,
                            amount,
                            customer_id,
                            attempt_number + 1,
                        ],
                        countdown=delay_seconds,
                    )

                    return {
                        "status": "retry_scheduled",
                        "payment_id": payment_id,
                        "next_attempt": attempt_number + 1,
                        "message": f"Retry scheduled in {delay_seconds}s",
                    }

                else:
                    logger.error(
                        f"Payment exhausted all retries: {payment_id}",
                        extra={"payment_id": payment_id},
                    )

                    # Check if lease should be defaulted
                    result = await service.check_lease_for_default(lease_id_uuid)

                    return {
                        "status": "failed",
                        "payment_id": payment_id,
                        "reason": reason,
                        "lease_defaulted": result,
                        "message": "Payment failed after all retries",
                    }

    except Exception as e:
        logger.error(
            f"Error retrying payment {payment_id}: {e}",
            extra={"payment_id": payment_id},
        )

        return {
            "status": "error",
            "payment_id": payment_id,
            "error": str(e),
            "message": "Error during payment retry",
        }


@celery_app.task(
    name="payment.schedule_lease_payments",
)
async def schedule_lease_payments(lease_id: str) -> dict:
    """
    Schedule all payments for a lease.

    This is called when a lease is created.

    Args:
        lease_id: ID of the lease

    Returns:
        Dict with schedule information
    """
    lease_id_uuid = UUID(lease_id)

    try:
        async with SessionLocal() as session:
            service = PaymentService(session)

            # Get lease and its payments
            lease = await service.lease_repo.get_by_id(lease_id_uuid)

            if lease is None:
                logger.error(f"Lease not found: {lease_id}")
                return {
                    "status": "error",
                    "lease_id": lease_id,
                    "message": "Lease not found",
                }

            # Get payment schedule
            payments = await service.get_lease_payments(lease_id_uuid)

            if not payments:
                logger.error(f"No payments found for lease: {lease_id}")
                return {
                    "status": "error",
                    "lease_id": lease_id,
                    "message": "No payments found",
                }

            # Publish payment scheduled events
            events = await service.schedule_payments_for_lease(lease_id_uuid, payments)

            logger.info(
                f"Scheduled {len(events)} payments for lease {lease_id}",
                extra={"lease_id": lease_id},
            )

            return {
                "status": "success",
                "lease_id": lease_id,
                "payment_count": len(events),
                "message": f"Scheduled {len(events)} payments",
            }

    except Exception as e:
        logger.error(f"Error scheduling payments for lease {lease_id}: {e}")

        return {
            "status": "error",
            "lease_id": lease_id,
            "error": str(e),
            "message": "Error scheduling payments",
        }


@celery_app.task(
    name="payment.process_due_payments",
)
async def process_due_payments() -> dict:
    """
    Process all due payments (auto-charge).

    This could be called by a scheduled beat task.

    Returns:
        Dict with processing information
    """
    try:
        async with SessionLocal() as session:
            service = PaymentService(session)

            # Get all due payments
            due_payments = await service.get_due_payments()

            logger.info(
                f"Found {len(due_payments)} due payments",
                extra={"count": len(due_payments)},
            )

            processed = 0
            succeeded = 0
            failed = 0

            # Process each payment
            for payment in due_payments:
                if payment.status != "PaymentStatus.PENDING":
                    continue

                try:
                    # Get lease info
                    lease = await service.lease_repo.get_by_id(payment.lease_id)

                    if lease is None:
                        logger.warning(f"Lease not found for payment: {payment.id}")
                        continue

                    # Attempt payment
                    status, reason = await service.attempt_payment(
                        payment_id=payment.id,
                        lease_id=payment.lease_id,
                        amount=payment.amount,
                        customer_id=lease.customer_id,
                        attempt_number=1,
                    )

                    processed += 1

                    if str(status) == "PaymentStatus.PAID":
                        succeeded += 1
                    else:
                        failed += 1
                        # Schedule retry
                        retry_failed_payment.apply_async(
                            args=[
                                str(payment.id),
                                str(payment.lease_id),
                                float(payment.amount),
                                lease.customer_id,
                                1,
                            ],
                            countdown=60,  # Retry after 1 minute
                        )

                except Exception as e:
                    logger.error(f"Error processing payment {payment.id}: {e}")
                    failed += 1

            return {
                "status": "success",
                "processed": processed,
                "succeeded": succeeded,
                "failed": failed,
                "message": f"Processed {processed} due payments",
            }

    except Exception as e:
        logger.error(f"Error in process_due_payments task: {e}")

        return {
            "status": "error",
            "error": str(e),
            "message": "Error processing due payments",
        }
