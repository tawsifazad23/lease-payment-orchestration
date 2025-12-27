"""Retry logic with exponential backoff."""

import logging
from typing import Callable, Optional, Any
from datetime import datetime, timedelta
import asyncio

logger = logging.getLogger(__name__)


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay_seconds: int = 60,
        max_delay_seconds: int = 3600,
        backoff_multiplier: float = 2.0,
        jitter: bool = True,
    ):
        """
        Initialize retry configuration.

        Args:
            max_retries: Maximum number of retries
            base_delay_seconds: Initial delay in seconds
            max_delay_seconds: Maximum delay between retries
            backoff_multiplier: Multiplier for exponential backoff
            jitter: Whether to add randomness to delays
        """
        self.max_retries = max_retries
        self.base_delay_seconds = base_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self.backoff_multiplier = backoff_multiplier
        self.jitter = jitter

    def calculate_delay(self, attempt_number: int) -> int:
        """
        Calculate delay for an attempt using exponential backoff.

        Args:
            attempt_number: The attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        delay = self.base_delay_seconds * (
            self.backoff_multiplier ** attempt_number
        )

        # Cap at max delay
        delay = min(delay, self.max_delay_seconds)

        # Add jitter if enabled
        if self.jitter:
            import random
            jitter_amount = random.uniform(0, delay * 0.1)  # 10% jitter
            delay = delay + jitter_amount

        return int(delay)

    def get_next_retry_time(self, attempt_number: int) -> datetime:
        """Get the next retry time based on attempt number."""
        delay = self.calculate_delay(attempt_number)
        return datetime.utcnow() + timedelta(seconds=delay)


class RetryScheduler:
    """Schedules retries with exponential backoff."""

    def __init__(self, config: Optional[RetryConfig] = None):
        """
        Initialize retry scheduler.

        Args:
            config: Retry configuration (uses defaults if None)
        """
        self.config = config or RetryConfig()

    async def retry_with_backoff(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute a function with retries and exponential backoff.

        Args:
            func: Async function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            Result of the function

        Raises:
            Exception: If all retries are exhausted
        """
        last_exception = None

        for attempt in range(self.config.max_retries + 1):
            try:
                logger.debug(
                    f"Executing {func.__name__} (attempt {attempt + 1}/{self.config.max_retries + 1})"
                )

                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                logger.debug(f"{func.__name__} succeeded on attempt {attempt + 1}")
                return result

            except Exception as e:
                last_exception = e

                if attempt < self.config.max_retries:
                    delay = self.config.calculate_delay(attempt)
                    logger.warning(
                        f"{func.__name__} failed on attempt {attempt + 1}. "
                        f"Retrying in {delay}s. Error: {e}"
                    )

                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"{func.__name__} failed after {self.config.max_retries + 1} attempts. "
                        f"Final error: {e}"
                    )

        raise last_exception

    def get_retry_schedule(self, max_attempts: int) -> list[tuple[int, int]]:
        """
        Get a schedule of retry attempts with delays.

        Args:
            max_attempts: Maximum number of attempts

        Returns:
            List of (attempt_number, delay_seconds) tuples
        """
        schedule = []

        for attempt in range(max_attempts):
            delay = self.config.calculate_delay(attempt)
            schedule.append((attempt + 1, delay))

        return schedule

    async def schedule_retry(
        self,
        func: Callable,
        delay_seconds: int,
        *args,
        **kwargs
    ) -> Any:
        """
        Schedule a function to be called after a delay.

        Args:
            func: Async function to execute
            delay_seconds: Delay in seconds
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            Result of the function
        """
        logger.info(
            f"Scheduling {func.__name__} for execution in {delay_seconds}s"
        )

        await asyncio.sleep(delay_seconds)

        logger.debug(f"Executing scheduled {func.__name__}")

        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            return func(*args, **kwargs)


# Global retry scheduler with default config
default_retry_scheduler = RetryScheduler()

# Standard retry configs
PAYMENT_RETRY_CONFIG = RetryConfig(
    max_retries=3,
    base_delay_seconds=60,  # 1 minute
    max_delay_seconds=86400,  # 1 day
    backoff_multiplier=6.0,  # 1min, 6min, 36min, 6h+
)

CRITICAL_OPERATION_RETRY_CONFIG = RetryConfig(
    max_retries=5,
    base_delay_seconds=30,  # 30 seconds
    max_delay_seconds=3600,  # 1 hour
    backoff_multiplier=2.0,
)
