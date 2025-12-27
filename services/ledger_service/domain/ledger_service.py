"""Ledger Service domain logic for audit trails and event sourcing."""

import logging
from typing import List, Dict, Tuple, Optional, Any, Union
from uuid import UUID
from datetime import datetime
from decimal import Decimal
import csv
import json
from io import StringIO

from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.ledger import Ledger
from shared.repositories.ledger import LedgerRepository

logger = logging.getLogger(__name__)


class LedgerQueryService:
    """Service for querying and filtering ledger events."""

    def __init__(self, db_session: AsyncSession):
        self.session = db_session
        self.repo = LedgerRepository(db_session)

    async def get_lease_audit_trail(
        self,
        lease_id: UUID,
        event_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Ledger]:
        """
        Retrieve filtered event history for a lease.

        Args:
            lease_id: ID of the lease
            event_type: Filter by specific event type
            start_date: Filter events after this date
            end_date: Filter events before this date
            skip: Pagination offset
            limit: Pagination limit

        Returns:
            List of Ledger entries in chronological order
        """
        # Get all events for lease
        events = await self.repo.get_lease_history(lease_id, skip=0, limit=10000)

        # Filter by event type
        if event_type:
            events = [e for e in events if e.event_type == event_type]

        # Filter by date range
        if start_date:
            events = [e for e in events if e.created_at >= start_date]
        if end_date:
            events = [e for e in events if e.created_at <= end_date]

        # Apply pagination
        total = len(events)
        events = events[skip : skip + limit]

        logger.info(
            f"Retrieved {len(events)} events for lease {lease_id}"
            f" (filtered from {total} total)"
        )

        return events

    async def get_event_timeline(
        self, lease_id: UUID, skip: int = 0, limit: int = 100
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get complete event timeline with state snapshots.

        Args:
            lease_id: ID of the lease
            skip: Pagination offset
            limit: Pagination limit

        Returns:
            Tuple of (timeline events, total count)
        """
        # Get all events in order
        all_events = await self.repo.get_lease_history(lease_id, skip=0, limit=10000)

        if not all_events:
            return [], 0

        # Build timeline with state transitions
        timeline = []
        reconstructor = HistoricalStateReconstructor()

        for i, event in enumerate(all_events):
            # Get state before and after this event
            state_before = reconstructor.reconstruct_lease_state(
                all_events[:i], point_in_time=event.created_at
            )
            state_after = reconstructor.reconstruct_lease_state(
                all_events[: i + 1], point_in_time=event.created_at
            )

            timeline.append(
                {
                    "sequence": event.id,
                    "event_type": event.event_type,
                    "timestamp": event.created_at.isoformat(),
                    "amount": float(event.amount) if event.amount else None,
                    "state_before": state_before,
                    "state_after": state_after,
                    "payload": event.event_payload,
                }
            )

        # Apply pagination
        total = len(timeline)
        timeline = timeline[skip : skip + limit]

        logger.info(f"Built timeline of {total} events for lease {lease_id}")

        return timeline, total

    async def reconstruct_state_at_point(
        self, lease_id: UUID, point_in_time: datetime
    ) -> Dict[str, Any]:
        """
        Reconstruct lease state at specific point in time.

        Args:
            lease_id: ID of the lease
            point_in_time: Timestamp to reconstruct state at

        Returns:
            Reconstructed state object
        """
        # Get all events up to point in time
        all_events = await self.repo.get_lease_history(lease_id, skip=0, limit=10000)

        # Filter events up to point in time
        events_before = [e for e in all_events if e.created_at <= point_in_time]
        events_after = [e for e in all_events if e.created_at > point_in_time]

        # Reconstruct state from events before point
        reconstructor = HistoricalStateReconstructor()
        reconstructed_state = reconstructor.reconstruct_lease_state(
            events_before, point_in_time
        )

        logger.info(
            f"Reconstructed state for lease {lease_id} at {point_in_time} "
            f"using {len(events_before)} events"
        )

        return {
            "lease_id": str(lease_id),
            "point_in_time": point_in_time.isoformat(),
            "reconstructed_state": reconstructed_state,
            "events_before_point": len(events_before),
            "events_after_point": len(events_after),
        }

    async def get_audit_metrics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Compute audit metrics and statistics.

        Args:
            start_date: Metrics period start
            end_date: Metrics period end

        Returns:
            Metrics object with distribution and analytics
        """
        # Get all events (in production, query database directly)
        # For now, using repository - could optimize with aggregation queries
        all_events = await self.repo.get_all(skip=0, limit=100000)

        # Filter by date range
        if start_date:
            all_events = [e for e in all_events if e.created_at >= start_date]
        if end_date:
            all_events = [e for e in all_events if e.created_at <= end_date]

        # Calculate metrics
        calculator = EventMetricsCalculator()
        distribution = calculator.calculate_distribution(all_events)
        time_metrics = calculator.calculate_time_based_metrics(all_events, start_date, end_date)
        top_types = calculator.get_top_event_types(all_events)

        # Group by lease
        events_per_lease: Dict[str, int] = {}
        for event in all_events:
            lease_id = str(event.lease_id)
            events_per_lease[lease_id] = events_per_lease.get(lease_id, 0) + 1

        logger.info(f"Calculated metrics for {len(all_events)} events")

        return {
            "period_start": start_date.isoformat() if start_date else None,
            "period_end": end_date.isoformat() if end_date else None,
            "total_events": len(all_events),
            "event_type_distribution": distribution,
            "event_count_by_date": time_metrics,
            "top_event_types": top_types,
            "events_per_lease": events_per_lease,
        }

    async def export_audit_trail(
        self,
        lease_id: UUID,
        format: str = "json",
        include_payload: bool = True,
        event_types: Optional[List[str]] = None,
    ) -> str:
        """
        Export audit trail in JSON or CSV format.

        Args:
            lease_id: ID of the lease
            format: Export format (json or csv)
            include_payload: Whether to include event payloads
            event_types: Filter by specific event types

        Returns:
            Formatted export data as string
        """
        # Get events for lease
        events = await self.repo.get_lease_history(lease_id, skip=0, limit=10000)

        # Filter by event type if specified
        if event_types:
            events = [e for e in events if e.event_type in event_types]

        # Transform events for export
        export_data = []
        for event in events:
            entry = {
                "event_id": event.id,
                "event_type": event.event_type,
                "timestamp": event.created_at.isoformat(),
                "amount": float(event.amount) if event.amount else None,
            }

            if include_payload:
                entry["payload"] = event.event_payload

            export_data.append(entry)

        # Format as requested
        if format == "json":
            result = json.dumps(export_data, indent=2, default=str)
        elif format == "csv":
            result = self._export_as_csv(export_data, include_payload)
        else:
            raise ValueError(f"Unsupported format: {format}")

        logger.info(f"Exported {len(export_data)} events for lease {lease_id} as {format}")

        return result

    def _export_as_csv(self, data: List[Dict], include_payload: bool) -> str:
        """Convert export data to CSV format."""
        if not data:
            return ""

        output = StringIO()

        # Determine fields
        fieldnames = ["event_id", "event_type", "timestamp", "amount"]
        if include_payload:
            fieldnames.append("payload")

        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for row in data:
            if include_payload and "payload" in row:
                row["payload"] = json.dumps(row["payload"])
            writer.writerow(row)

        return output.getvalue()


class HistoricalStateReconstructor:
    """Reconstructs entity state from event history."""

    def reconstruct_lease_state(
        self,
        events: List[Ledger],
        point_in_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Reconstruct lease state from events.

        Args:
            events: List of ledger events in order
            point_in_time: Optional time boundary

        Returns:
            Reconstructed state
        """
        state = {
            "lease_id": None,
            "customer_id": None,
            "status": "PENDING",
            "principal_amount": Decimal("0"),
            "term_months": 0,
            "total_paid": Decimal("0"),
            "paid_installments": 0,
            "failed_attempts": 0,
            "event_count": 0,
        }

        for event in events:
            if point_in_time and event.created_at > point_in_time:
                break

            state["event_count"] += 1
            payload = event.event_payload

            # Apply state transitions based on event type
            if event.event_type == "LEASE_CREATED":
                state["lease_id"] = str(payload.get("lease_id"))
                state["customer_id"] = payload.get("customer_id")
                state["principal_amount"] = Decimal(str(payload.get("principal_amount", 0)))
                state["term_months"] = payload.get("term_months", 0)
                state["status"] = "ACTIVE"

            elif event.event_type == "PAYMENT_SUCCEEDED":
                state["total_paid"] = Decimal(str(payload.get("amount", 0)))
                state["paid_installments"] += 1

            elif event.event_type == "PAYMENT_FAILED":
                state["failed_attempts"] += 1

            elif event.event_type == "LEASE_COMPLETED":
                state["status"] = "COMPLETED"

            elif event.event_type == "LEASE_DEFAULTED":
                state["status"] = "DEFAULTED"

        # Convert decimals to float for JSON serialization
        state["principal_amount"] = float(state["principal_amount"])
        state["total_paid"] = float(state["total_paid"])

        return state

    def get_state_at_event(
        self, event: Ledger, previous_events: List[Ledger]
    ) -> Dict[str, Any]:
        """
        Compute state after specific event.

        Args:
            event: The event to apply
            previous_events: Events before this one

        Returns:
            State after applying event
        """
        # Get state from all previous events
        state = self.reconstruct_lease_state(previous_events)

        # Apply this event
        all_events = previous_events + [event]
        return self.reconstruct_lease_state(all_events)


class EventMetricsCalculator:
    """Calculates metrics and analytics from events."""

    def calculate_distribution(
        self, events: List[Ledger], group_by: str = "event_type"
    ) -> Dict[str, int]:
        """
        Calculate event distribution by category.

        Args:
            events: List of events
            group_by: Grouping strategy

        Returns:
            Distribution dict
        """
        distribution: Dict[str, int] = {}

        for event in events:
            if group_by == "event_type":
                key = event.event_type
            elif group_by == "lease_id":
                key = str(event.lease_id)
            elif group_by == "date":
                key = event.created_at.date().isoformat()
            else:
                key = event.event_type

            distribution[key] = distribution.get(key, 0) + 1

        return distribution

    def calculate_time_based_metrics(
        self,
        events: List[Ledger],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, int]:
        """
        Calculate metrics grouped by date.

        Args:
            events: List of events
            start_date: Period start
            end_date: Period end

        Returns:
            Metrics by date
        """
        metrics: Dict[str, int] = {}

        for event in events:
            date_key = event.created_at.date().isoformat()
            metrics[date_key] = metrics.get(date_key, 0) + 1

        return metrics

    def get_top_event_types(
        self, events: List[Ledger], limit: int = 10
    ) -> List[Tuple[str, int]]:
        """
        Get top event types by frequency.

        Args:
            events: List of events
            limit: Number of top types to return

        Returns:
            Sorted list of (event_type, count)
        """
        distribution = self.calculate_distribution(events, "event_type")
        sorted_types = sorted(distribution.items(), key=lambda x: x[1], reverse=True)
        return sorted_types[:limit]
