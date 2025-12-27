"""Initial schema creation

Revision ID: 001
Revises:
Create Date: 2025-12-27 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create leases table
    op.create_table(
        'leases',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('customer_id', sa.String(255), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'ACTIVE', 'COMPLETED', 'DEFAULTED', name='leasestatus'), nullable=False),
        sa.Column('principal_amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('term_months', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_customer_status', 'leases', ['customer_id', 'status'])
    op.create_index('idx_customer', 'leases', ['customer_id'])
    op.create_index('idx_status', 'leases', ['status'])

    # Create payment_schedule table
    op.create_table(
        'payment_schedule',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('lease_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('installment_number', sa.Integer(), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'PAID', 'FAILED', 'CANCELLED', name='paymentstatus'), nullable=False),
        sa.Column('retry_count', sa.Integer(), nullable=False),
        sa.Column('last_attempt_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['lease_id'], ['leases.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_lease_status', 'payment_schedule', ['lease_id', 'status'])
    op.create_index('idx_due_date_status', 'payment_schedule', ['due_date', 'status'])
    op.create_index('idx_lease', 'payment_schedule', ['lease_id'])
    op.create_index('idx_due_date', 'payment_schedule', ['due_date'])
    op.create_index('idx_status', 'payment_schedule', ['status'])

    # Create ledger table
    op.create_table(
        'ledger',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('lease_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('event_payload', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('amount', sa.Numeric(10, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['lease_id'], ['leases.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_lease_events', 'ledger', ['lease_id', 'created_at'])
    op.create_index('idx_event_type_created', 'ledger', ['event_type', 'created_at'])
    op.create_index('idx_event_type', 'ledger', ['event_type'])

    # Create idempotency_keys table
    op.create_table(
        'idempotency_keys',
        sa.Column('key', sa.String(255), nullable=False),
        sa.Column('operation', sa.String(100), nullable=False),
        sa.Column('response_payload', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('key')
    )
    op.create_index('idx_operation_created', 'idempotency_keys', ['operation', 'created_at'])
    op.create_index('idx_expires', 'idempotency_keys', ['expires_at'])


def downgrade() -> None:
    op.drop_index('idx_expires', table_name='idempotency_keys')
    op.drop_index('idx_operation_created', table_name='idempotency_keys')
    op.drop_table('idempotency_keys')

    op.drop_index('idx_event_type', table_name='ledger')
    op.drop_index('idx_event_type_created', table_name='ledger')
    op.drop_index('idx_lease_events', table_name='ledger')
    op.drop_table('ledger')

    op.drop_index('idx_status', table_name='payment_schedule')
    op.drop_index('idx_due_date', table_name='payment_schedule')
    op.drop_index('idx_lease', table_name='payment_schedule')
    op.drop_index('idx_due_date_status', table_name='payment_schedule')
    op.drop_index('idx_lease_status', table_name='payment_schedule')
    op.drop_table('payment_schedule')

    op.drop_index('idx_status', table_name='leases')
    op.drop_index('idx_customer', table_name='leases')
    op.drop_index('idx_customer_status', table_name='leases')
    op.drop_table('leases')
