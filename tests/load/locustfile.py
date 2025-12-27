"""Main Locust configuration file for load testing."""

import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tests.load.lease_load_test import LeaseServiceLoadTest
from tests.load.payment_load_test import PaymentServiceLoadTest
from tests.load.ledger_load_test import LedgerServiceLoadTest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

# Export user classes for Locust
__all__ = [
    "LeaseServiceLoadTest",
    "PaymentServiceLoadTest",
    "LedgerServiceLoadTest",
]

logger.info("Load test suite initialized with Lease, Payment, and Ledger service tests")
