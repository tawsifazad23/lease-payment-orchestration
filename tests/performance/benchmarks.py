"""Performance benchmarking suite for critical operations."""

import asyncio
import time
import logging
from uuid import uuid4
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Any

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from shared.database import Base
from shared.models.lease import Lease, LeaseStatus
from shared.models.ledger import Ledger
from shared.repositories.lease import LeaseRepository
from shared.repositories.ledger import LedgerRepository

logger = logging.getLogger(__name__)


class PerformanceBenchmark:
    """Base class for performance benchmarks."""

    def __init__(self, name: str, threshold_ms: float):
        self.name = name
        self.threshold_ms = threshold_ms
        self.measurements: List[float] = []

    def record(self, elapsed_ms: float):
        """Record a measurement."""
        self.measurements.append(elapsed_ms)

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics for recorded measurements."""
        if not self.measurements:
            return {}

        sorted_times = sorted(self.measurements)
        return {
            "name": self.name,
            "count": len(self.measurements),
            "min": min(sorted_times),
            "max": max(sorted_times),
            "avg": sum(sorted_times) / len(sorted_times),
            "p50": sorted_times[len(sorted_times) // 2],
            "p95": sorted_times[int(len(sorted_times) * 0.95)],
            "p99": sorted_times[int(len(sorted_times) * 0.99)],
            "threshold": self.threshold_ms,
            "meets_threshold": (sum(sorted_times) / len(sorted_times)) <= self.threshold_ms,
        }


class PerformanceBenchmarkSuite:
    """Suite for running performance benchmarks."""

    def __init__(self, db_url: str = "sqlite+aiosqlite:///:memory:"):
        self.db_url = db_url
        self.engine = None
        self.async_session = None
        self.benchmarks: Dict[str, PerformanceBenchmark] = {}

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

    def add_benchmark(self, name: str, threshold_ms: float = 100):
        """Add a new benchmark to track."""
        self.benchmarks[name] = PerformanceBenchmark(name, threshold_ms)

    async def benchmark_lease_creation(self, iterations: int = 100):
        """Benchmark lease creation performance."""
        self.add_benchmark("lease_creation", threshold_ms=50)
        benchmark = self.benchmarks["lease_creation"]

        async with self.async_session() as session:
            repo = LeaseRepository(session)

            for i in range(iterations):
                start = time.time()

                lease = Lease(
                    customer_id=f"PERF-{uuid4()}",
                    status=LeaseStatus.PENDING,
                    principal_amount=Decimal("5000.00"),
                    term_months=12,
                )
                await repo.create(lease)
                await repo.commit()

                elapsed_ms = (time.time() - start) * 1000
                benchmark.record(elapsed_ms)

        return benchmark.get_stats()

    async def benchmark_lease_retrieval(self, iterations: int = 100):
        """Benchmark lease retrieval performance."""
        self.add_benchmark("lease_retrieval", threshold_ms=20)
        benchmark = self.benchmarks["lease_retrieval"]

        async with self.async_session() as session:
            repo = LeaseRepository(session)

            # Create test leases
            lease_ids = []
            for i in range(10):
                lease = Lease(
                    customer_id=f"PERF-{uuid4()}",
                    status=LeaseStatus.PENDING,
                    principal_amount=Decimal("5000.00"),
                    term_months=12,
                )
                created = await repo.create(lease)
                lease_ids.append(created.id)
            await repo.commit()

            # Benchmark retrieval
            for i in range(iterations):
                lease_id = lease_ids[i % len(lease_ids)]
                start = time.time()

                await repo.get_by_id(lease_id)

                elapsed_ms = (time.time() - start) * 1000
                benchmark.record(elapsed_ms)

        return benchmark.get_stats()

    async def benchmark_ledger_append(self, iterations: int = 100):
        """Benchmark ledger event append performance."""
        self.add_benchmark("ledger_append", threshold_ms=30)
        benchmark = self.benchmarks["ledger_append"]

        async with self.async_session() as session:
            repo = LedgerRepository(session)
            lease_id = uuid4()

            for i in range(iterations):
                start = time.time()

                await repo.append_event(
                    lease_id=lease_id,
                    event_type=f"EVENT_{i}",
                    event_payload={"index": i},
                    amount=Decimal("100.00"),
                )

                elapsed_ms = (time.time() - start) * 1000
                benchmark.record(elapsed_ms)

        return benchmark.get_stats()

    async def benchmark_ledger_history_retrieval(self, iterations: int = 50):
        """Benchmark ledger history retrieval performance."""
        self.add_benchmark("ledger_history_retrieval", threshold_ms=100)
        benchmark = self.benchmarks["ledger_history_retrieval"]

        async with self.async_session() as session:
            repo = LedgerRepository(session)
            lease_id = uuid4()

            # Create test events
            for i in range(100):
                await repo.append_event(
                    lease_id=lease_id,
                    event_type=f"EVENT_{i}",
                    event_payload={"index": i},
                    amount=Decimal("50.00"),
                )

            # Benchmark retrieval
            for i in range(iterations):
                start = time.time()

                await repo.get_lease_history(lease_id, skip=0, limit=100)

                elapsed_ms = (time.time() - start) * 1000
                benchmark.record(elapsed_ms)

        return benchmark.get_stats()

    def print_summary(self):
        """Print benchmark summary."""
        print("\n" + "=" * 80)
        print("PERFORMANCE BENCHMARK SUMMARY")
        print("=" * 80)

        all_pass = True
        for name, benchmark in self.benchmarks.items():
            stats = benchmark.get_stats()
            if not stats:
                continue

            passes = stats["meets_threshold"]
            status = "PASS" if passes else "FAIL"
            all_pass = all_pass and passes

            print(f"\n{stats['name']}: {status}")
            print(f"  Count: {stats['count']}")
            print(f"  Min: {stats['min']:.2f}ms")
            print(f"  Max: {stats['max']:.2f}ms")
            print(f"  Avg: {stats['avg']:.2f}ms")
            print(f"  P50: {stats['p50']:.2f}ms")
            print(f"  P95: {stats['p95']:.2f}ms")
            print(f"  P99: {stats['p99']:.2f}ms")
            print(f"  Threshold: {stats['threshold']:.2f}ms")

        print("\n" + "=" * 80)
        overall = "ALL PASS" if all_pass else "SOME FAILURES"
        print(f"Overall Result: {overall}")
        print("=" * 80 + "\n")

        return all_pass

    async def run_all_benchmarks(self):
        """Run all performance benchmarks."""
        await self.setup()
        try:
            await self.benchmark_lease_creation()
            await self.benchmark_lease_retrieval()
            await self.benchmark_ledger_append()
            await self.benchmark_ledger_history_retrieval()
            return self.print_summary()
        finally:
            await self.teardown()


async def run_benchmarks():
    """Main entry point for benchmarking."""
    suite = PerformanceBenchmarkSuite()
    return await suite.run_all_benchmarks()


if __name__ == "__main__":
    result = asyncio.run(run_benchmarks())
    exit(0 if result else 1)
