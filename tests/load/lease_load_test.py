"""Load tests for Lease Service."""

import logging
from locust import task, tag
from tests.load.base import BaseLoadTestUser, LEASE_SERVICE_URL, generate_idempotency_key

logger = logging.getLogger(__name__)


class LeaseServiceLoadTest(BaseLoadTestUser):
    """Load test suite for Lease Service endpoints."""

    host = LEASE_SERVICE_URL

    @task(3)
    @tag("lease", "create")
    def create_lease(self):
        """Test lease creation endpoint."""
        payload = {
            "customer_id": f"CUST-LOAD-{self.user_id[:8]}",
            "principal_amount": 3600.00,
            "term_months": 12,
        }
        headers = {"Idempotency-Key": generate_idempotency_key()}

        response = self.client.post(
            f"{self.host}/api/v1/leases",
            json=payload,
            headers=headers,
        )

        if response.status_code == 201:
            data = response.json()
            if "lease_id" in data:
                self.test_data["lease_id"] = data["lease_id"]
                self.metrics.record_request(
                    request_type="POST",
                    name="/api/v1/leases",
                    response_time=response.elapsed.total_seconds() * 1000,
                    success=True,
                )
        else:
            self.metrics.record_request(
                request_type="POST",
                name="/api/v1/leases",
                response_time=response.elapsed.total_seconds() * 1000,
                success=False,
                error=f"HTTP {response.status_code}",
            )

    @task(2)
    @tag("lease", "retrieve")
    def get_lease(self):
        """Test lease retrieval endpoint."""
        if "lease_id" not in self.test_data:
            return

        response = self.client.get(
            f"{self.host}/api/v1/leases/{self.test_data['lease_id']}"
        )

        self.metrics.record_request(
            request_type="GET",
            name="/api/v1/leases/{lease_id}",
            response_time=response.elapsed.total_seconds() * 1000,
            success=response.status_code == 200,
            error=None if response.status_code == 200 else f"HTTP {response.status_code}",
        )

    @task(2)
    @tag("lease", "history")
    def get_lease_history(self):
        """Test lease history endpoint."""
        if "lease_id" not in self.test_data:
            return

        response = self.client.get(
            f"{self.host}/api/v1/leases/{self.test_data['lease_id']}/history"
        )

        self.metrics.record_request(
            request_type="GET",
            name="/api/v1/leases/{lease_id}/history",
            response_time=response.elapsed.total_seconds() * 1000,
            success=response.status_code == 200,
            error=None if response.status_code == 200 else f"HTTP {response.status_code}",
        )

    @task(1)
    @tag("lease", "list")
    def list_leases(self):
        """Test list leases endpoint."""
        response = self.client.get(f"{self.host}/api/v1/leases?skip=0&limit=50")

        self.metrics.record_request(
            request_type="GET",
            name="/api/v1/leases",
            response_time=response.elapsed.total_seconds() * 1000,
            success=response.status_code == 200,
            error=None if response.status_code == 200 else f"HTTP {response.status_code}",
        )

    @task(1)
    @tag("lease", "health")
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
