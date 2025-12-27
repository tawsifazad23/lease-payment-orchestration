"""Load tests for Payment Service."""

import logging
from uuid import uuid4
from locust import task, tag
from tests.load.base import BaseLoadTestUser, PAYMENT_SERVICE_URL, LEASE_SERVICE_URL, generate_idempotency_key

logger = logging.getLogger(__name__)


class PaymentServiceLoadTest(BaseLoadTestUser):
    """Load test suite for Payment Service endpoints."""

    host = PAYMENT_SERVICE_URL

    def on_start(self):
        """Initialize payment test user and create a lease."""
        super().on_start()
        # Create a test lease first
        self._create_test_lease()

    def _create_test_lease(self):
        """Helper method to create a test lease."""
        payload = {
            "customer_id": f"CUST-PAYMENT-{self.user_id[:8]}",
            "principal_amount": 1200.00,
            "term_months": 12,
        }
        headers = {"Idempotency-Key": f"lease-{uuid4()}"}

        try:
            response = self.client.post(
                f"{LEASE_SERVICE_URL}/api/v1/leases",
                json=payload,
                headers=headers,
                timeout=10,
            )
            if response.status_code == 201:
                data = response.json()
                self.test_data["lease_id"] = data.get("lease_id")
        except Exception as e:
            logger.error(f"Failed to create test lease: {e}")

    @task(2)
    @tag("payment", "list")
    def get_lease_payments(self):
        """Test get lease payments endpoint."""
        if "lease_id" not in self.test_data:
            return

        response = self.client.get(
            f"{self.host}/api/v1/leases/{self.test_data['lease_id']}/payments"
        )

        if response.status_code == 200:
            data = response.json()
            if "payments" in data and len(data["payments"]) > 0:
                self.test_data["payment_id"] = data["payments"][0]["payment_id"]

        self.metrics.record_request(
            request_type="GET",
            name="/api/v1/leases/{lease_id}/payments",
            response_time=response.elapsed.total_seconds() * 1000,
            success=response.status_code == 200,
            error=None if response.status_code == 200 else f"HTTP {response.status_code}",
        )

    @task(3)
    @tag("payment", "attempt")
    def attempt_payment(self):
        """Test payment attempt endpoint."""
        if "payment_id" not in self.test_data:
            return

        headers = {"Idempotency-Key": generate_idempotency_key()}

        response = self.client.post(
            f"{self.host}/api/v1/payments/{self.test_data['payment_id']}/attempt",
            headers=headers,
        )

        success = response.status_code in [200, 201]
        self.metrics.record_request(
            request_type="POST",
            name="/api/v1/payments/{payment_id}/attempt",
            response_time=response.elapsed.total_seconds() * 1000,
            success=success,
            error=None if success else f"HTTP {response.status_code}",
        )

    @task(1)
    @tag("payment", "payoff")
    def early_payoff(self):
        """Test early payoff endpoint."""
        if "lease_id" not in self.test_data:
            return

        headers = {"Idempotency-Key": generate_idempotency_key()}

        response = self.client.post(
            f"{self.host}/api/v1/leases/{self.test_data['lease_id']}/payoff",
            headers=headers,
        )

        success = response.status_code in [200, 201]
        self.metrics.record_request(
            request_type="POST",
            name="/api/v1/leases/{lease_id}/payoff",
            response_time=response.elapsed.total_seconds() * 1000,
            success=success,
            error=None if success else f"HTTP {response.status_code}",
        )

    @task(1)
    @tag("payment", "health")
    def health_check(self):
        """Test health endpoint."""
        response = self.client.get(f"{self.host}/health")

        self.metrics.record_request(
            request_type="GET",
            name="/health",
            response_time=response.elapsed.total_seconds() * 1000,
            success=response.status_code == 200,
            error=None if response.status_code == 200 else f"HTTP {response.status_code}",
        )
