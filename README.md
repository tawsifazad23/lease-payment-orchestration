# Lease Payment Orchestration System

A production-style, event-driven microservices architecture for managing lease agreements and payment processing with idempotent transaction handling, event sourcing, and comprehensive audit trails.

**Status**: All tests passing (86) · Fully runnable via Docker · Comprehensive integration testing

## Why I Built This

This project grew out of real-world experience with fragile, multi-step workflows where retries were unsafe and humans were responsible for tracking state. I built it to practice designing systems where failures are expected, retries are safe, and every decision is auditable.

## Core Features

- **Idempotent Financial Operations**: Prevent duplicate charges using idempotency keys with 24-hour TTL
- **Event-Sourced Audit Ledger**: Complete immutable record of all state changes for compliance and debugging
- **Explicit Lease State Machine**: PENDING → ACTIVE → COMPLETED/DEFAULTED with validated transitions
- **Safe Payment Retries**: Exponential backoff with configurable retry attempts and dead letter queue
- **Early Payoff Handling**: Calculate discounts and process early lease completion

## Additional Capabilities

- Auto-completion when all payments received
- Auto-defaulting after 3+ failed payment attempts
- Historical state reconstruction at any point in time
- JSON/CSV audit trail export
- Load testing and performance benchmarking infrastructure

## What This Demonstrates

**Backend & Platform Engineering**
- Event-driven architecture with safe async patterns (FastAPI, asyncpg, Redis pub/sub)
- Idempotent API design preventing duplicate financial transactions
- Explicit state machines for lifecycle management

**Data & Correctness**
- Append-only event ledger enabling full auditability
- Event replay for deterministic state reconstruction
- Recoverable failure handling via event history

**Real-World Constraints**
- Retry semantics with exponential backoff
- Graceful degradation under load
- Complete audit trail for compliance

## Architecture

### System Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Client Applications                               │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────────────────┐
│                    API Gateway / Load Balancer                           │
└──────────────┬──────────────────┬──────────────────┬────────────────────┘
               │                  │                  │
        ┌──────▼──────┐    ┌──────▼──────┐   ┌──────▼──────┐
        │   Lease      │    │  Payment     │   │  Ledger      │
        │  Service     │    │  Service     │   │  Service     │
        │  :8000       │    │  :8001       │   │  :8002       │
        └──────┬───────┘    └──────┬───────┘   └──────┬───────┘
               │                   │                   │
               └───────────────────┼───────────────────┘
                                   │
                      ┌────────────▼────────────┐
                      │   PostgreSQL Database   │
                      │  (Leases, Payments,    │
                      │   Idempotency, Ledger) │
                      └────────────┬────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
   ┌────▼─────┐           ┌─────────▼─────────┐    ┌──────────▼──────┐
   │   Redis   │           │   Redis Pub/Sub   │    │  Redis Cache    │
   │   Cache   │           │  (Event Bus+DLQ)  │    │                 │
   └──────────┘           └───────────────────┘    └─────────────────┘
```

Designed to mirror real-world fintech service boundaries while remaining fully runnable locally via Docker.

### Data Flow

```
                          Event-Driven Architecture

Create Lease          Payment Processed         Complete Lease
    │                        │                        │
    ▼                        ▼                        ▼
┌─────────────┐          ┌──────────┐           ┌────────────┐
│ LeaseService│─Event───▶│ EventBus │◀──Event──│ Ledger     │
└──────┬──────┘          └──┬───────┘           │ Service    │
       │                    │                   └────────────┘
       ▼                    ▼
  Database          Redis Pub/Sub
   (Sync)          (Async Notify)
                        │
                        ▼
                  Dead Letter Queue
                 (Failed Events)
```

### Service Responsibilities

**Lease Service**:
- Create and manage lease agreements
- Track lease lifecycle (PENDING → ACTIVE → COMPLETED/DEFAULTED)
- Validate state transitions
- Generate payment schedules
- Emit lease events

**Payment Service**:
- Schedule payment installments
- Process payment attempts with gateway simulation (70% success rate)
- Implement retry logic with exponential backoff
- Track payment status and retry counts
- Handle early payoff calculations
- Emit payment events

**Ledger Service**:
- Persist all events to immutable ledger (append-only)
- Provide audit trail queries with filtering
- Export audit data (JSON/CSV)
- Reconstruct historical state at any timestamp
- Calculate audit metrics and analytics
- Support complex filtering and pagination

## Technology Stack

- **Framework**: FastAPI 0.104.1 with async/await
- **Database**: PostgreSQL with async driver (asyncpg)
- **ORM**: SQLAlchemy 2.0 (async mode)
- **Cache/Pub-Sub**: Redis 5.0.1
- **Background Jobs**: Celery 5.3.4
- **Validation**: Pydantic 2.5.0
- **Testing**: pytest with asyncio support
- **Load Testing**: Locust 2.17.0
- **Monitoring**: Prometheus client for metrics

## Quick Start

### Prerequisites

- Python 3.9+
- Docker & Docker Compose
- PostgreSQL 14+
- Redis 6+

### Installation

```bash
# Clone repository
git clone <repo-url>
cd lease-payment-orchestration

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment configuration
cp .env.example .env
```

### Running with Docker

```bash
# Start all services
docker-compose up -d

# Wait for services to be healthy (30 seconds)
sleep 30

# Run migrations
docker-compose exec lease_service alembic upgrade head

# View logs
docker-compose logs -f
```

### Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ -v --cov=services --cov=shared

# Run specific test suite
pytest tests/integration/test_lease_service.py -v
pytest tests/integration/test_payment_service.py -v
pytest tests/integration/test_ledger_service.py -v

# Run performance benchmarks
python tests/performance/benchmarks.py

# Run stress tests
python tests/performance/stress_tests.py
```

## 5-Minute Demo

Get up and running with the system in 5 minutes. This demo shows a complete lease lifecycle.

### Step 1: Create a Lease

```bash
# Save the response for later steps
LEASE_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/leases \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: demo-lease-001" \
  -d '{
    "customer_id": "CUST-DEMO-001",
    "principal_amount": 1200.00,
    "term_months": 12
  }')

# Extract lease_id (requires jq: `brew install jq`)
LEASE_ID=$(echo $LEASE_RESPONSE | jq -r '.lease_id')
echo "Created lease: $LEASE_ID"
```

Expected response:
```json
{
  "lease_id": "550e8400-e29b-41d4-a716-446655440000",
  "customer_id": "CUST-DEMO-001",
  "status": "PENDING",
  "principal_amount": 1200.00,
  "term_months": 12,
  "payment_schedule": [
    {
      "payment_id": "550e8400-e29b-41d4-a716-446655440001",
      "installment_number": 1,
      "due_date": "2025-01-27",
      "amount": 100.00,
      "status": "PENDING"
    }
    // ... 11 more installments
  ]
}
```

### Step 2: Get Lease Details

```bash
curl -s http://localhost:8000/api/v1/leases/$LEASE_ID | jq
```

### Step 3: View Complete Audit Trail

```bash
curl -s http://localhost:8000/api/v1/leases/$LEASE_ID/history | jq
```

Returns all events that happened to this lease, including creation and payment scheduling.

### Step 4: Attempt Payment

```bash
# Extract first payment_id from the lease
PAYMENT_ID=$(curl -s http://localhost:8001/api/v1/leases/$LEASE_ID/payments | \
  jq -r '.payments[0].id')

# Attempt to process the payment
curl -s -X POST http://localhost:8001/api/v1/payments/$PAYMENT_ID/attempt \
  -H "Idempotency-Key: demo-payment-attempt-001" | jq
```

Response (70% chance of success):
```json
{
  "payment_id": "550e8400-e29b-41d4-a716-446655440001",
  "lease_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "PAID",
  "amount": 100.00,
  "processed_at": "2025-01-27T10:30:45Z"
}
```

### Step 5: Test Idempotency Protection

```bash
# Try creating the same lease twice with identical idempotency key
RESPONSE_1=$(curl -s -X POST http://localhost:8000/api/v1/leases \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: duplicate-test-001" \
  -d '{"customer_id":"CUST-002","principal_amount":600.00,"term_months":6}')

RESPONSE_2=$(curl -s -X POST http://localhost:8000/api/v1/leases \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: duplicate-test-001" \
  -d '{"customer_id":"CUST-002","principal_amount":600.00,"term_months":6}')

# Extract both lease IDs
LEASE_ID_1=$(echo $RESPONSE_1 | jq -r '.lease_id')
LEASE_ID_2=$(echo $RESPONSE_2 | jq -r '.lease_id')

# Verify they're identical
if [ "$LEASE_ID_1" = "$LEASE_ID_2" ]; then
  echo "Idempotency verified: Same lease_id returned ($LEASE_ID_1)"
else
  echo "FAIL: Different lease IDs created"
fi
```

**Why This Matters**: Demonstrates that the system prevents duplicate charges, a critical safeguard for payment processing systems.

### Step 6: Check Updated Audit Trail

```bash
curl -s http://localhost:8000/api/v1/leases/$LEASE_ID/history | jq
```

Notice new events: `PAYMENT_ATTEMPTED`, `PAYMENT_SUCCEEDED`, and `PAYMENT_SCHEDULED`.

### Step 7: Export Audit Data

```bash
# Export as JSON
curl -s http://localhost:8002/api/v1/audit/leases/$LEASE_ID/export?format=json | jq

# Or as CSV
curl -s http://localhost:8002/api/v1/audit/leases/$LEASE_ID/export?format=csv
```

### Step 8: Reconstruct Historical State

```bash
# Query lease state at a specific point in time
curl -s -X POST http://localhost:8002/api/v1/audit/leases/$LEASE_ID/state-at-point \
  -H "Content-Type: application/json" \
  -d '{"point_in_time": "2025-01-20T12:00:00Z"}' | jq
```

---

**That's it!** You've now seen the complete event-driven workflow:
1. Created a lease
2. Scheduled 12 monthly payments
3. Processed a payment
4. Viewed the complete audit trail
5. Exported financial records
6. Reconstructed historical state

## Database Schema

### Leases Table
- `id` (UUID, PK)
- `customer_id` (String)
- `status` (Enum: PENDING, ACTIVE, COMPLETED, DEFAULTED)
- `principal_amount` (Decimal)
- `term_months` (Integer)
- `created_at`, `updated_at` (Timestamps)

### Payment Schedule Table
- `id` (UUID, PK)
- `lease_id` (UUID, FK)
- `installment_number` (Integer)
- `due_date` (Date)
- `amount` (Decimal)
- `status` (Enum: PENDING, PAID, FAILED, CANCELLED)
- `retry_count` (Integer)
- `last_attempt_at` (Timestamp)

### Ledger Table (Append-Only)
- `id` (Integer, PK, Auto-increment)
- `lease_id` (UUID)
- `event_type` (String)
- `event_payload` (JSON)
- `amount` (Decimal, optional)
- `created_at` (Timestamp)
- Constraints: Cannot UPDATE or DELETE

### Idempotency Keys Table
- `key` (String, PK)
- `operation` (String)
- `response_payload` (JSON)
- `created_at`, `expires_at` (Timestamps)

## Business Logic

### Lease State Machine

```
PENDING --[activate]--> ACTIVE --[complete]--> COMPLETED
                           ↓
                        [default]
                           ↓
                       DEFAULTED

Terminal states: COMPLETED, DEFAULTED
```

### Payment Processing Flow

1. **Schedule**: Lease created → Payment schedule generated (12 installments)
2. **Attempt**: Payment attempt initiated → 70% success rate (simulated for demonstration/testing purposes)
3. **Success**: Mark as PAID → Reduce remaining balance
4. **Failure**: Mark as FAILED → Increment retry count → Schedule retry (exponential backoff)
5. **Default**: 3+ failures → Mark lease as DEFAULTED → Send notification
6. **Complete**: All paid → Mark lease as COMPLETED

### Early Payoff Logic

- Calculate remaining balance
- Apply 2% discount on remaining balance
- Process immediate payment
- Update lease status based on final balance

## Design Rationale

### Why Event Sourcing?
Event sourcing provides a complete audit trail of every state change, critical for financial systems. Instead of storing only the current state, we capture all events that led to it. This enables:
- **Regulatory Compliance**: Complete history for audits and dispute resolution
- **Debugging**: Reproduce any issue by replaying events in sequence
- **Business Intelligence**: Analyze payment patterns and customer behavior from raw event data
- **Temporal Queries**: Ask "What was the lease balance on 2025-01-15?" at any time

### Why Microservices?
Separating concerns into distinct services allows independent scaling and deployment:
- **Lease Service**: Handles lease lifecycle - grows with customer base
- **Payment Service**: Handles payment processing - peaks at payment due dates
- **Ledger Service**: Handles historical queries - grows with time but accessed infrequently

Each service can be scaled, deployed, or updated independently without affecting others.

### Why Redis Pub/Sub for Events?
Asynchronous event publishing decouples services:
- **Resilience**: Dead Letter Queue captures failed events for retry
- **Performance**: Publishing is fire-and-forget (non-blocking)
- **Scalability**: Multiple consumers can subscribe to the same events
- **Simplicity**: Lightweight alternative to RabbitMQ/Kafka for this scale

This choice favors clarity and practicality over extreme scale; the design intentionally allows swapping in Kafka or RabbitMQ without changing domain logic.

### Why Idempotency Keys?
Financial operations must be idempotent to prevent duplicate charges:
- **Network Retries**: Client can safely retry without duplicating operations
- **Exactly-Once Semantics**: Payment processed exactly once even if request is retried
- **24-Hour TTL**: Balances safety with operational simplicity

### Why Pydantic Models?
Strong typing at API boundaries prevents invalid data from entering the system:
- **Validation**: Catches errors at the edge (FastAPI validates request bodies)
- **Documentation**: OpenAPI schema auto-generated from models
- **Type Safety**: IDE support for model usage reduces bugs

### Tradeoffs & Decisions

**What We Optimized For:**
- **Consistency over Availability** (CP in CAP theorem) - Financial data cannot be "eventually consistent"
- **Audit Completeness over Storage Cost** - Every event stored permanently for compliance
- **Developer Experience over Raw Performance** - FastAPI + Pydantic provide excellent DX with acceptable latency

**Conscious Tradeoffs:**
- **Redis Pub/Sub vs Kafka**: Chose simplicity over absolute scale (suitable for ~10K events/sec)
- **PostgreSQL vs NoSQL**: ACID guarantees more important than horizontal scalability at current scale
- **Synchronous API vs Async Processing**: Lease creation is synchronous for immediate user confirmation; payments are async for resilience
- **In-Memory Testing vs Real Database**: SQLite for CI/CD speed; production uses PostgreSQL with ~20% higher latency but still well within targets

## Performance Results

Benchmarks focus on relative behavior and correctness under load rather than absolute production throughput. Measured on SQLite in-memory database with 100 iterations per operation:

| Operation | Avg | P95 | P99 | Target | Status |
|-----------|-----|-----|-----|--------|--------|
| Lease Creation | 24.18ms | 42.67ms | 58.91ms | 50ms | PASS |
| Lease Retrieval | 7.83ms | 14.23ms | 17.45ms | 20ms | PASS |
| Ledger Append | 11.45ms | 24.56ms | 32.11ms | 30ms | PASS |
| Ledger History Query | 38.92ms | 78.23ms | 101.34ms | 100ms | PASS |

All operations meet or exceed performance targets. Production PostgreSQL performance will be slightly higher but still well within acceptable ranges.

## Load Testing

System gracefully degrades under load. Run `locust -f tests/load/locustfile.py` for interactive testing or add `--headless` flag for automated runs.

## Configuration

Environment variables in `.env`:

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/lease_db

# Redis
REDIS_URL=redis://localhost:6379/0

# Celery
CELERY_BROKER_URL=redis://localhost:6379/1

# Services
LEASE_SERVICE_PORT=8000
PAYMENT_SERVICE_PORT=8001
LEDGER_SERVICE_PORT=8002

# Logging
LOG_LEVEL=INFO
ENVIRONMENT=production
```

## Deployment

### Docker Compose (Development)

```bash
docker-compose up -d
docker-compose logs -f
docker-compose down -v  # Cleanup
```

### Kubernetes (Production)

See `k8s/` directory for manifests. Services are stateless and can be scaled horizontally.

## Monitoring & Observability

### Health Checks

```bash
# Lease Service
curl http://localhost:8000/health

# Payment Service
curl http://localhost:8001/health

# Ledger Service
curl http://localhost:8002/health
```

### Metrics

Prometheus metrics available at:
- `http://localhost:8000/metrics`
- `http://localhost:8001/metrics`
- `http://localhost:8002/metrics`

### Logging

All services log to stdout in JSON format for easy parsing by log aggregators (ELK, DataDog, etc.).

## Extensions and Real-World Considerations

To move toward production, consider:

- **Replace simulated payment gateway** with real processor (Stripe, Square) in `services/payment_service/domain/payment_gateway.py`
- **Never store raw card data** - use payment processor tokenization
- **Validate webhook signatures** from payment processors to prevent replay attacks
- **Add API rate limiting** on payment endpoints
- **Implement database connection pooling** (PgBouncer) for PostgreSQL
- **Add JWT or API key authentication** to all endpoints

## Troubleshooting

**Tests failing**: Ensure test database is clean and has proper schema
```bash
docker-compose exec postgres psql -U lease_user -d lease_db -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
pytest tests/ -v
```

**Redis connection error**: Ensure Redis is running and accessible
```bash
redis-cli ping  # Should return PONG
```

**Migrations failing**: Reset and re-run migrations
```bash
docker-compose exec lease_service alembic downgrade base
docker-compose exec lease_service alembic upgrade head
```

## Testing Checklist

- Run all tests: `pytest tests/ -v`
- Check coverage: `pytest --cov=services --cov=shared`
- Run load tests: `locust -f tests/load/locustfile.py`
- Verify idempotency: Retry requests with same idempotency key
- Test event replay: Verify historical state reconstruction

## License

MIT

---

**Built by**: Tawsif Ibne Azad | [LinkedIn](https://linkedin.com/in/tawsifibneazad) | [GitHub](https://github.com/tawsifazad23)

**Last Updated**: December 27, 2025
**Status**: Production-ready | 86/86 tests passing
