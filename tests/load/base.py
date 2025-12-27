"""Base configuration and utilities for load testing."""

import os
import time
from uuid import uuid4
from datetime import datetime
from typing import Dict, Any, Optional
from locust import HttpUser, task, between, events
import logging

logger = logging.getLogger(__name__)

# Service URLs (configurable via environment variables)
LEASE_SERVICE_URL = os.getenv("LEASE_SERVICE_URL", "http://localhost:8000")
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://localhost:8001")
LEDGER_SERVICE_URL = os.getenv("LEDGER_SERVICE_URL", "http://localhost:8002")
EVENT_BUS_URL = os.getenv("EVENT_BUS_URL", "http://localhost:8003")

# Test configuration
DEFAULT_WAIT_TIME = (1, 5)  # Random wait between 1-5 seconds
SPAWN_RATE = int(os.getenv("SPAWN_RATE", "1"))  # Users spawned per second
NUM_USERS = int(os.getenv("NUM_USERS", "10"))  # Total number of concurrent users
RUN_TIME = os.getenv("RUN_TIME", "5m")  # Duration (e.g., "5m", "60s")

# Performance metrics thresholds
API_RESPONSE_TIME_THRESHOLD = 500  # milliseconds
DB_QUERY_THRESHOLD = 200  # milliseconds
P95_THRESHOLD = 1000  # milliseconds


class PerformanceMetrics:
    """Collects performance metrics during load test."""

    def __init__(self):
        self.start_time = datetime.utcnow()
        self.requests_total = 0
        self.requests_success = 0
        self.requests_failed = 0
        self.response_times = []
        self.error_counts = {}

    def record_request(
        self,
        request_type: str,
        name: str,
        response_time: float,
        success: bool,
        error: Optional[str] = None,
    ):
        """Record a request metric."""
        self.requests_total += 1
        self.response_times.append(response_time)

        if success:
            self.requests_success += 1
        else:
            self.requests_failed += 1
            if error:
                self.error_counts[error] = self.error_counts.get(error, 0) + 1

    def get_summary(self) -> Dict[str, Any]:
        """Get performance metrics summary."""
        if not self.response_times:
            return {}

        sorted_times = sorted(self.response_times)
        total_time = (datetime.utcnow() - self.start_time).total_seconds()

        return {
            "total_requests": self.requests_total,
            "successful_requests": self.requests_success,
            "failed_requests": self.requests_failed,
            "success_rate": (
                (self.requests_success / self.requests_total * 100)
                if self.requests_total > 0
                else 0
            ),
            "avg_response_time": sum(sorted_times) / len(sorted_times),
            "min_response_time": min(sorted_times),
            "max_response_time": max(sorted_times),
            "p50_response_time": sorted_times[len(sorted_times) // 2],
            "p95_response_time": sorted_times[int(len(sorted_times) * 0.95)],
            "p99_response_time": sorted_times[int(len(sorted_times) * 0.99)],
            "requests_per_second": self.requests_total / total_time if total_time > 0 else 0,
            "error_summary": self.error_counts,
        }


class BaseLoadTestUser(HttpUser):
    """Base class for all load test users with common utilities."""

    wait_time = between(*DEFAULT_WAIT_TIME)
    metrics = PerformanceMetrics()

    def on_start(self):
        """Initialize test user."""
        self.user_id = str(uuid4())
        self.test_data = {}

    def make_request(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict] = None,
        name: Optional[str] = None,
        expected_status: int = 200,
    ):
        """Make HTTP request with error handling and metrics collection."""
        url = f"{self.host}{path}"
        request_type = method.upper()
        request_name = name or path

        start_time = time.time()
        try:
            response = self.client.request(
                method=request_type,
                url=url,
                json=json_data,
                timeout=10,
            )
            response_time = (time.time() - start_time) * 1000  # Convert to ms

            success = response.status_code == expected_status
            error = None if success else f"HTTP {response.status_code}"

            self.metrics.record_request(
                request_type=request_type,
                name=request_name,
                response_time=response_time,
                success=success,
                error=error,
            )

            # Log slow requests
            if response_time > API_RESPONSE_TIME_THRESHOLD:
                logger.warning(
                    f"Slow request: {request_type} {request_name} took {response_time:.2f}ms"
                )

            return response

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            self.metrics.record_request(
                request_type=request_type,
                name=request_name,
                response_time=response_time,
                success=False,
                error=str(type(e).__name__),
            )
            logger.error(f"Request failed: {request_type} {url}: {e}")
            raise


def generate_idempotency_key() -> str:
    """Generate a unique idempotency key."""
    return f"load-test-{uuid4()}"


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when test starts."""
    logger.info(f"Load test starting with {environment.runner.target_shape} users")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when test stops."""
    logger.info("Load test completed")
    if BaseLoadTestUser.metrics:
        summary = BaseLoadTestUser.metrics.get_summary()
        logger.info(f"Metrics Summary: {summary}")
