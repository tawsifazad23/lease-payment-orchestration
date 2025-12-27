"""Load tests for Ledger Service."""

import logging
from uuid import uuid4
from datetime import datetime, timedelta
from locust import task, tag
from tests.load.base import BaseLoadTestUser, LEDGER_SERVICE_URL, LEASE_SERVICE_URL

logger = logging.getLogger(__name__)


class LedgerServiceLoadTest(BaseLoadTestUser):
    """Load test suite for Ledger Service endpoints."""

    host = LEDGER_SERVICE_URL

    def on_start(self):
        """Initialize ledger test user and create a lease with events."""
        super().on_start()
        self._create_test_lease_with_events()

    def _create_test_lease_with_events(self):
        """Helper method to create a test lease that will have ledger events."""
        payload = {
            "customer_id": f"CUST-LEDGER-{self.user_id[:8]}",
            "principal_amount": 2400.00,
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

    @task(3)
    @tag("ledger", "audit_trail")
    def get_audit_trail(self):
        """Test audit trail endpoint."""
        if "lease_id" not in self.test_data:
            return

        response = self.client.get(
            f"{self.host}/api/v1/audit/leases/{self.test_data['lease_id']}"
        )

        self.metrics.record_request(
            request_type="GET",
            name="/api/v1/audit/leases/{lease_id}",
            response_time=response.elapsed.total_seconds() * 1000,
            success=response.status_code == 200,
            error=None if response.status_code == 200 else f"HTTP {response.status_code}",
        )

    @task(2)
    @tag("ledger", "timeline")
    def get_timeline(self):
        """Test event timeline endpoint."""
        if "lease_id" not in self.test_data:
            return

        response = self.client.get(
            f"{self.host}/api/v1/audit/leases/{self.test_data['lease_id']}/timeline"
        )

        self.metrics.record_request(
            request_type="GET",
            name="/api/v1/audit/leases/{lease_id}/timeline",
            response_time=response.elapsed.total_seconds() * 1000,
            success=response.status_code == 200,
            error=None if response.status_code == 200 else f"HTTP {response.status_code}",
        )

    @task(2)
    @tag("ledger", "state_reconstruction")
    def reconstruct_state(self):
        """Test state reconstruction endpoint."""
        if "lease_id" not in self.test_data:
            return

        point_in_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        response = self.client.post(
            f"{self.host}/api/v1/audit/leases/{self.test_data['lease_id']}/state-at-point",
            params={"point_in_time": point_in_time},
        )

        success = response.status_code in [200, 400]  # 400 if lease not found
        self.metrics.record_request(
            request_type="POST",
            name="/api/v1/audit/leases/{lease_id}/state-at-point",
            response_time=response.elapsed.total_seconds() * 1000,
            success=success,
            error=None if success else f"HTTP {response.status_code}",
        )

    @task(2)
    @tag("ledger", "export")
    def export_audit_trail(self):
        """Test audit trail export endpoint."""
        if "lease_id" not in self.test_data:
            return

        # Alternate between JSON and CSV
        format_type = "json" if hash(self.user_id) % 2 == 0 else "csv"

        response = self.client.get(
            f"{self.host}/api/v1/audit/leases/{self.test_data['lease_id']}/export",
            params={"format": format_type, "include_payload": True},
        )

        self.metrics.record_request(
            request_type="GET",
            name=f"/api/v1/audit/leases/{{lease_id}}/export?format={format_type}",
            response_time=response.elapsed.total_seconds() * 1000,
            success=response.status_code == 200,
            error=None if response.status_code == 200 else f"HTTP {response.status_code}",
        )

    @task(1)
    @tag("ledger", "metrics")
    def get_metrics(self):
        """Test audit metrics endpoint."""
        response = self.client.get(f"{self.host}/api/v1/audit/metrics")

        self.metrics.record_request(
            request_type="GET",
            name="/api/v1/audit/metrics",
            response_time=response.elapsed.total_seconds() * 1000,
            success=response.status_code == 200,
            error=None if response.status_code == 200 else f"HTTP {response.status_code}",
        )

    @task(1)
    @tag("ledger", "health")
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
