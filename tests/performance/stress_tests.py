"""Stress testing scenarios to identify system breaking points."""

import asyncio
import logging
import psutil
from typing import Dict, List, Any, Callable
from datetime import datetime
from uuid import uuid4
from decimal import Decimal

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from shared.database import Base
from shared.models.lease import Lease, LeaseStatus
from shared.repositories.lease import LeaseRepository
from shared.repositories.ledger import LedgerRepository

logger = logging.getLogger(__name__)


class StressTestResult:
    """Result of a stress test scenario."""

    def __init__(self, scenario_name: str):
        self.scenario_name = scenario_name
        self.start_time = datetime.utcnow()
        self.end_time = None
        self.total_operations = 0
        self.successful_operations = 0
        self.failed_operations = 0
        self.errors: List[str] = []
        self.peak_memory_mb = 0
        self.peak_cpu_percent = 0

    def duration_seconds(self) -> float:
        """Get test duration in seconds."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0

    def success_rate(self) -> float:
        """Get success rate percentage."""
        if self.total_operations == 0:
            return 0
        return (self.successful_operations / self.total_operations) * 100

    def operations_per_second(self) -> float:
        """Get operations per second."""
        duration = self.duration_seconds()
        if duration == 0:
            return 0
        return self.total_operations / duration

    def print_summary(self):
        """Print test result summary."""
        print(f"\n{'=' * 80}")
        print(f"STRESS TEST: {self.scenario_name}")
        print(f"{'=' * 80}")
        print(f"Duration: {self.duration_seconds():.2f} seconds")
        print(f"Total Operations: {self.total_operations}")
        print(f"Successful: {self.successful_operations}")
        print(f"Failed: {self.failed_operations}")
        print(f"Success Rate: {self.success_rate():.2f}%")
        print(f"Operations/sec: {self.operations_per_second():.2f}")
        print(f"Peak Memory: {self.peak_memory_mb:.2f} MB")
        print(f"Peak CPU: {self.peak_cpu_percent:.2f}%")
        if self.errors:
            print(f"\nErrors (first 5):")
            for error in self.errors[:5]:
                print(f"  - {error}")
        print(f"{'=' * 80}\n")


class StressTestSuite:
    """Suite for running stress tests."""

    def __init__(self, db_url: str = "sqlite+aiosqlite:///:memory:"):
        self.db_url = db_url
        self.engine = None
        self.async_session = None
        self.process = psutil.Process()

    async def setup(self):
        """Setup database session."""
        self.engine = create_async_engine(self.db_url, echo=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self.async_session = sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def teardown(self):
        """Cleanup database session."""
        if self.engine:
            await self.engine.dispose()

    def _monitor_resources(self, result: StressTestResult):
        """Monitor and record resource usage."""
        try:
            memory_info = self.process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            result.peak_memory_mb = max(result.peak_memory_mb, memory_mb)

            cpu_percent = self.process.cpu_percent(interval=0.1)
            result.peak_cpu_percent = max(result.peak_cpu_percent, cpu_percent)
        except Exception as e:
            logger.warning(f"Failed to monitor resources: {e}")

    async def stress_test_concurrent_lease_creation(
        self, concurrent_operations: int = 50, operations_per_task: int = 10
    ) -> StressTestResult:
        """Stress test concurrent lease creation."""
        result = StressTestResult("Concurrent Lease Creation")

        async with self.async_session() as session:
            repo = LeaseRepository(session)

            async def create_leases():
                for i in range(operations_per_task):
                    try:
                        self._monitor_resources(result)
                        result.total_operations += 1

                        lease = Lease(
                            customer_id=f"STRESS-{uuid4()}",
                            status=LeaseStatus.PENDING,
                            principal_amount=Decimal("5000.00"),
                            term_months=12,
                        )
                        await repo.create(lease)
                        await repo.commit()
                        result.successful_operations += 1
                    except Exception as e:
                        result.failed_operations += 1
                        error_msg = f"{type(e).__name__}: {str(e)[:50]}"
                        if error_msg not in result.errors:
                            result.errors.append(error_msg)

            # Run concurrent tasks
            tasks = [create_leases() for _ in range(concurrent_operations)]
            await asyncio.gather(*tasks, return_exceptions=True)

        result.end_time = datetime.utcnow()
        return result

    async def stress_test_ledger_event_storm(
        self, num_leases: int = 10, events_per_lease: int = 100
    ) -> StressTestResult:
        """Stress test rapid ledger event appends (event storm)."""
        result = StressTestResult("Ledger Event Storm")

        async with self.async_session() as session:
            repo = LedgerRepository(session)

            # Create lease IDs
            lease_ids = [uuid4() for _ in range(num_leases)]

            async def append_events(lease_id):
                for i in range(events_per_lease):
                    try:
                        self._monitor_resources(result)
                        result.total_operations += 1

                        await repo.append_event(
                            lease_id=lease_id,
                            event_type=f"STRESS_EVENT_{i}",
                            event_payload={"index": i, "data": "x" * 100},
                            amount=Decimal("10.00"),
                        )
                        result.successful_operations += 1
                    except Exception as e:
                        result.failed_operations += 1
                        error_msg = f"{type(e).__name__}: {str(e)[:50]}"
                        if error_msg not in result.errors:
                            result.errors.append(error_msg)

            # Run concurrent append operations
            tasks = [append_events(lease_id) for lease_id in lease_ids]
            await asyncio.gather(*tasks, return_exceptions=True)

        result.end_time = datetime.utcnow()
        return result

    async def stress_test_read_amplification(
        self, num_leases: int = 20, reads_per_lease: int = 50
    ) -> StressTestResult:
        """Stress test concurrent reads (read amplification)."""
        result = StressTestResult("Read Amplification")

        async with self.async_session() as session:
            lease_repo = LeaseRepository(session)
            ledger_repo = LedgerRepository(session)

            # Create test leases with events
            lease_ids = []
            for i in range(num_leases):
                lease = Lease(
                    customer_id=f"STRESS-READ-{uuid4()}",
                    status=LeaseStatus.PENDING,
                    principal_amount=Decimal("5000.00"),
                    term_months=12,
                )
                created = await lease_repo.create(lease)
                lease_ids.append(created.id)

                # Add events
                for j in range(10):
                    await ledger_repo.append_event(
                        lease_id=created.id,
                        event_type=f"EVENT_{j}",
                        event_payload={"index": j},
                        amount=Decimal("500.00"),
                    )
            await lease_repo.commit()

            async def read_operations(lease_id):
                for i in range(reads_per_lease):
                    try:
                        self._monitor_resources(result)
                        result.total_operations += 1

                        # Read lease
                        await lease_repo.get_by_id(lease_id)
                        # Read events
                        await ledger_repo.get_lease_history(lease_id, skip=0, limit=10)

                        result.successful_operations += 1
                    except Exception as e:
                        result.failed_operations += 1
                        error_msg = f"{type(e).__name__}: {str(e)[:50]}"
                        if error_msg not in result.errors:
                            result.errors.append(error_msg)

            # Run concurrent reads
            tasks = [read_operations(lease_id) for lease_id in lease_ids]
            await asyncio.gather(*tasks, return_exceptions=True)

        result.end_time = datetime.utcnow()
        return result

    async def run_all_stress_tests(self) -> List[StressTestResult]:
        """Run all stress test scenarios."""
        await self.setup()
        results = []

        try:
            logger.info("Starting stress test suite...")

            result1 = await self.stress_test_concurrent_lease_creation()
            results.append(result1)

            result2 = await self.stress_test_ledger_event_storm()
            results.append(result2)

            result3 = await self.stress_test_read_amplification()
            results.append(result3)

            return results
        finally:
            await self.teardown()

    def print_all_results(self, results: List[StressTestResult]):
        """Print all stress test results."""
        print("\n" + "=" * 80)
        print("STRESS TEST SUITE RESULTS")
        print("=" * 80)

        for result in results:
            result.print_summary()

        print("=" * 80)
        print("RECOMMENDATIONS")
        print("=" * 80)
        for result in results:
            if result.success_rate() < 95:
                print(
                    f"⚠️  {result.scenario_name}: Success rate {result.success_rate():.2f}% is below 95%"
                )
            if result.peak_memory_mb > 500:
                print(
                    f"⚠️  {result.scenario_name}: Peak memory {result.peak_memory_mb:.2f}MB exceeds limit"
                )
        print("=" * 80 + "\n")


async def run_stress_tests():
    """Main entry point for stress testing."""
    suite = StressTestSuite()
    results = await suite.run_all_stress_tests()
    suite.print_all_results(results)
    return all(r.success_rate() >= 95 for r in results)


if __name__ == "__main__":
    success = asyncio.run(run_stress_tests())
    exit(0 if success else 1)
