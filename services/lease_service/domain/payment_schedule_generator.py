"""Payment schedule generation logic."""

import logging
from datetime import datetime, date, timedelta
from decimal import Decimal
from uuid import UUID

logger = logging.getLogger(__name__)


class PaymentScheduleGenerator:
    """Generates payment schedules for leases."""

    @staticmethod
    def generate_equal_installments(
        lease_id: UUID,
        principal_amount: Decimal,
        term_months: int,
        start_date: date = None,
        interest_rate: Decimal = None,
    ) -> list[dict]:
        """
        Generate equal monthly installment schedule.

        Args:
            lease_id: ID of the lease
            principal_amount: Total amount to be financed
            term_months: Number of months for the lease
            start_date: Start date for payments (default: today + 30 days)
            interest_rate: Annual interest rate (not used for simple division, can be extended)

        Returns:
            List of payment dictionaries with installment details
        """
        if term_months <= 0:
            raise ValueError("Term must be greater than 0")

        if principal_amount <= 0:
            raise ValueError("Principal amount must be greater than 0")

        if start_date is None:
            start_date = date.today() + timedelta(days=30)

        # Calculate monthly payment (simple equal division)
        monthly_payment = principal_amount / Decimal(term_months)

        # Round to 2 decimal places
        monthly_payment = monthly_payment.quantize(Decimal("0.01"))

        schedule = []

        for installment_num in range(1, term_months + 1):
            # Calculate due date
            due_date = start_date + timedelta(days=30 * (installment_num - 1))

            # For the last installment, adjust amount to cover rounding
            if installment_num == term_months:
                # Calculate total of all previous payments
                total_previous = monthly_payment * Decimal(term_months - 1)
                # Last payment = principal - sum of previous
                amount = principal_amount - total_previous
            else:
                amount = monthly_payment

            schedule.append({
                "lease_id": lease_id,
                "installment_number": installment_num,
                "due_date": due_date,
                "amount": amount,
            })

        logger.info(
            f"Generated {term_months} installments for lease {lease_id}: "
            f"${principal_amount} over {term_months} months"
        )

        return schedule

    @staticmethod
    def validate_schedule(schedule: list[dict]) -> bool:
        """
        Validate a payment schedule.

        Args:
            schedule: List of payment dictionaries

        Returns:
            True if valid, raises ValueError otherwise
        """
        if not schedule:
            raise ValueError("Schedule cannot be empty")

        # Check installment numbers are sequential
        expected_num = 1
        for payment in schedule:
            if payment["installment_number"] != expected_num:
                raise ValueError(
                    f"Non-sequential installment numbers. Expected {expected_num}, "
                    f"got {payment['installment_number']}"
                )
            expected_num += 1

        # Check amounts are positive
        total = Decimal("0")
        for payment in schedule:
            if payment["amount"] <= 0:
                raise ValueError(f"Invalid amount: {payment['amount']}")
            total += payment["amount"]

        return True

    @staticmethod
    def calculate_remaining_balance(
        schedule: list[dict],
        payments_made: list[dict],
    ) -> Decimal:
        """
        Calculate remaining balance on a lease.

        Args:
            schedule: Full payment schedule
            payments_made: List of paid payments

        Returns:
            Remaining balance
        """
        total_scheduled = sum(p["amount"] for p in schedule)
        total_paid = sum(p.get("amount", 0) for p in payments_made)

        return total_scheduled - total_paid

    @staticmethod
    def calculate_payoff_amount(
        remaining_balance: Decimal,
        early_payoff_discount_percent: Decimal = Decimal("2.0"),
    ) -> tuple[Decimal, Decimal]:
        """
        Calculate payoff amount with early payoff discount.

        Args:
            remaining_balance: Current remaining balance
            early_payoff_discount_percent: Discount percentage (default 2%)

        Returns:
            (payoff_amount, discount_amount)
        """
        discount_amount = (
            remaining_balance * early_payoff_discount_percent / Decimal("100")
        ).quantize(Decimal("0.01"))

        payoff_amount = (remaining_balance - discount_amount).quantize(
            Decimal("0.01")
        )

        return payoff_amount, discount_amount
