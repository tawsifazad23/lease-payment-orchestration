"""Simulated payment gateway for testing."""

import random
import logging
from datetime import datetime
from decimal import Decimal
from enum import Enum

logger = logging.getLogger(__name__)


class PaymentResult(str, Enum):
    """Result of a payment attempt."""
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    DECLINED = "DECLINED"
    TIMEOUT = "TIMEOUT"


class PaymentGateway:
    """Simulated payment gateway for testing."""

    # Success rate for payments (70% success)
    SUCCESS_RATE = 0.70

    @staticmethod
    def process_payment(
        payment_id: str,
        lease_id: str,
        amount: Decimal,
        attempt_number: int = 1,
        customer_id: str = None,
    ) -> tuple[PaymentResult, str]:
        """
        Simulate processing a payment.

        Args:
            payment_id: ID of the payment
            lease_id: ID of the lease
            amount: Amount to charge
            attempt_number: Which attempt this is (1, 2, 3...)
            customer_id: Customer identifier

        Returns:
            (PaymentResult, transaction_id)
        """
        # Increase success rate on retries (encourages eventual success)
        adjusted_success_rate = PaymentGateway.SUCCESS_RATE + (
            (attempt_number - 1) * 0.05
        )
        adjusted_success_rate = min(adjusted_success_rate, 1.0)

        # Random success/failure
        random_value = random.random()

        if random_value < adjusted_success_rate:
            # Success
            transaction_id = f"txn-{payment_id}-{int(datetime.utcnow().timestamp())}"
            logger.info(
                f"Payment succeeded: {payment_id} (${amount}) - {transaction_id}",
                extra={
                    "payment_id": payment_id,
                    "lease_id": lease_id,
                    "amount": float(amount),
                },
            )
            return PaymentResult.SUCCESS, transaction_id
        else:
            # Failure
            failure_reasons = [
                "Insufficient funds",
                "Card declined",
                "Network timeout",
                "Invalid card",
            ]
            reason = random.choice(failure_reasons)
            logger.warning(
                f"Payment failed: {payment_id} (${amount}) - {reason}",
                extra={
                    "payment_id": payment_id,
                    "lease_id": lease_id,
                    "amount": float(amount),
                    "reason": reason,
                },
            )
            return PaymentResult.FAILURE, reason

    @staticmethod
    def set_success_rate(rate: float):
        """
        Set the success rate for testing.

        Args:
            rate: Success rate between 0.0 and 1.0
        """
        if not (0.0 <= rate <= 1.0):
            raise ValueError("Success rate must be between 0.0 and 1.0")
        PaymentGateway.SUCCESS_RATE = rate
        logger.info(f"Payment gateway success rate set to {rate}")
