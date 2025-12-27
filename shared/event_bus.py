"""Event bus implementation with Redis pub/sub."""

import json
import logging
from typing import Callable, Dict, List, Optional
from uuid import uuid4
from datetime import datetime, timedelta
import asyncio
import redis.asyncio as redis

from shared.redis_client import RedisClient
from shared.events.schemas import BaseEvent

logger = logging.getLogger(__name__)

# Event topics
LEASE_EVENTS_TOPIC = "lease:events"
PAYMENT_EVENTS_TOPIC = "payment:events"
DLQ_TOPIC = "events:dlq"


class EventPublisher:
    """Publishes events to Redis pub/sub."""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def publish(
        self,
        event: BaseEvent,
        topic: str = LEASE_EVENTS_TOPIC,
    ) -> bool:
        """
        Publish an event to a topic.

        Args:
            event: Event to publish
            topic: Redis topic/channel name

        Returns:
            True if at least one subscriber received the event
        """
        try:
            # Generate event ID if not set
            if not event.event_id or event.event_id == '00000000-0000-0000-0000-000000000000':
                event.event_id = str(uuid4())

            # Serialize event to JSON
            event_data = event.model_dump_json()

            # Publish to Redis
            num_subscribers = await self.redis.publish(topic, event_data)

            logger.info(
                f"Published {event.event_type} to {topic}. "
                f"Subscribers: {num_subscribers}"
            )

            return num_subscribers > 0

        except Exception as e:
            logger.error(f"Failed to publish event: {e}")
            raise

    async def publish_with_persistence(
        self,
        event: BaseEvent,
        topic: str = LEASE_EVENTS_TOPIC,
        persistence_key: Optional[str] = None,
    ) -> bool:
        """
        Publish event and store in Redis for persistence.

        Args:
            event: Event to publish
            topic: Redis topic/channel name
            persistence_key: Key to store event in Redis (if None, not persisted)

        Returns:
            True if published successfully
        """
        # Publish the event
        published = await self.publish(event, topic)

        # Optionally persist event
        if persistence_key:
            ttl = 86400  # 24 hours
            await self.redis.setex(
                persistence_key,
                ttl,
                event.model_dump_json(),
            )

        return published


class EventConsumer:
    """Consumes events from Redis pub/sub."""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.pubsub = redis_client.pubsub()
        self.handlers: Dict[str, List[Callable]] = {}
        self._running = False

    def register_handler(
        self,
        event_type: str,
        handler: Callable,
    ):
        """
        Register a handler for a specific event type.

        Args:
            event_type: Type of event to handle (e.g., "LEASE_CREATED")
            handler: Async callable that processes the event
        """
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)

        logger.info(f"Registered handler for {event_type}")

    async def subscribe(self, *topics: str):
        """Subscribe to one or more topics."""
        if not topics:
            topics = (LEASE_EVENTS_TOPIC, PAYMENT_EVENTS_TOPIC)

        await self.pubsub.subscribe(*topics)
        logger.info(f"Subscribed to topics: {topics}")

    async def start(self):
        """Start consuming events."""
        self._running = True
        logger.info("Event consumer started")

        try:
            async for message in self.pubsub.listen():
                if not self._running:
                    break

                # Skip subscription confirmations
                if message["type"] == "subscribe":
                    continue

                if message["type"] == "message":
                    await self._handle_message(message)

        except Exception as e:
            logger.error(f"Error in event consumer: {e}")
            raise
        finally:
            await self.stop()

    async def _handle_message(self, message: dict):
        """Handle a received message."""
        try:
            # Parse event JSON
            event_data = json.loads(message["data"])

            event_type = event_data.get("event_type")
            event_id = event_data.get("event_id")

            logger.debug(f"Received event {event_type} (id={event_id})")

            # Find and execute handlers
            handlers = self.handlers.get(event_type, [])

            if not handlers:
                logger.warning(f"No handlers registered for {event_type}")
                return

            # Execute all handlers for this event type
            for handler in handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event_data)
                    else:
                        handler(event_data)

                    logger.debug(
                        f"Handler executed for {event_type}"
                    )

                except Exception as e:
                    logger.error(
                        f"Handler failed for {event_type}: {e}"
                    )
                    # Send to DLQ
                    await self._send_to_dlq(event_data, str(e))

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse event JSON: {e}")

    async def _send_to_dlq(self, event_data: dict, error: str):
        """Send failed event to dead letter queue."""
        try:
            dlq_entry = {
                "original_event": event_data,
                "error": error,
                "failed_at": datetime.utcnow().isoformat(),
                "dlq_id": str(uuid4()),
            }

            await self.redis.lpush(
                DLQ_TOPIC,
                json.dumps(dlq_entry),
            )

            logger.info(
                f"Event sent to DLQ: {dlq_entry['dlq_id']}"
            )

        except Exception as e:
            logger.error(f"Failed to send event to DLQ: {e}")

    async def stop(self):
        """Stop the event consumer."""
        self._running = False
        await self.pubsub.unsubscribe()
        logger.info("Event consumer stopped")


class DeadLetterQueue:
    """Manages dead letter queue for failed events."""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def get_dlq_entries(self, limit: int = 100) -> List[dict]:
        """Get entries from DLQ."""
        try:
            entries = await self.redis.lrange(DLQ_TOPIC, 0, limit - 1)
            return [json.loads(entry) for entry in entries]
        except Exception as e:
            logger.error(f"Failed to get DLQ entries: {e}")
            return []

    async def acknowledge(self, dlq_id: str) -> bool:
        """Remove entry from DLQ (acknowledge processing)."""
        try:
            entries = await self.redis.lrange(DLQ_TOPIC, 0, -1)

            for idx, entry in enumerate(entries):
                data = json.loads(entry)
                if data.get("dlq_id") == dlq_id:
                    await self.redis.lrem(DLQ_TOPIC, 1, entry)
                    logger.info(f"Acknowledged DLQ entry: {dlq_id}")
                    return True

            logger.warning(f"DLQ entry not found: {dlq_id}")
            return False

        except Exception as e:
            logger.error(f"Failed to acknowledge DLQ entry: {e}")
            return False

    async def get_dlq_count(self) -> int:
        """Get number of entries in DLQ."""
        try:
            return await self.redis.llen(DLQ_TOPIC)
        except Exception as e:
            logger.error(f"Failed to get DLQ count: {e}")
            return 0

    async def clear_dlq(self) -> bool:
        """Clear all entries from DLQ."""
        try:
            await self.redis.delete(DLQ_TOPIC)
            logger.info("DLQ cleared")
            return True
        except Exception as e:
            logger.error(f"Failed to clear DLQ: {e}")
            return False


class EventBusManager:
    """Central event bus manager."""

    def __init__(self):
        self.publisher: Optional[EventPublisher] = None
        self.consumer: Optional[EventConsumer] = None
        self.dlq: Optional[DeadLetterQueue] = None

    async def initialize(self):
        """Initialize event bus components."""
        try:
            redis_client = await RedisClient.get_client()

            self.publisher = EventPublisher(redis_client)
            self.consumer = EventConsumer(redis_client)
            self.dlq = DeadLetterQueue(redis_client)

            logger.info("Event bus initialized")

        except Exception as e:
            logger.error(f"Failed to initialize event bus: {e}")
            raise

    async def publish_event(
        self,
        event: BaseEvent,
        topic: str = LEASE_EVENTS_TOPIC,
    ) -> bool:
        """Publish an event."""
        if self.publisher is None:
            raise RuntimeError("Event bus not initialized")

        return await self.publisher.publish(event, topic)

    async def start_consumer(self, *topics: str):
        """Start consuming events."""
        if self.consumer is None:
            raise RuntimeError("Event bus not initialized")

        await self.consumer.subscribe(*topics)
        await self.consumer.start()

    def register_event_handler(
        self,
        event_type: str,
        handler: Callable,
    ):
        """Register an event handler."""
        if self.consumer is None:
            raise RuntimeError("Event bus not initialized")

        self.consumer.register_handler(event_type, handler)


# Global event bus instance
event_bus = EventBusManager()
