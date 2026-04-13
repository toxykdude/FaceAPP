"""Initial database schema

Revision ID: 001
Revises: 
Create Date: 2026-01-29 18:20:00.000000

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
    # Create users table
    op.create_table('users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('username', sa.String(length=50), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('last_login', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
        sa.UniqueConstraint('email')
    )
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=False)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=False)

    # Create members table
    op.create_table('members',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('first_name', sa.String(length=100), nullable=False),
        sa.Column('last_name', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('facial_data_enrolled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('biometric_template_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('consent_given_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('last_seen', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )
    op.create_index(op.f('ix_members_email'), 'members', ['email'], unique=False)
    op.create_index(op.f('ix_members_created_at'), 'members', ['created_at'], unique=False)

    # Create biometric_templates table
    op.create_table('biometric_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('member_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('template_data', sa.LargeBinary(), nullable=False),
        sa.Column('encryption_key_id', sa.String(length=50), nullable=False, server_default='v1'),
        sa.Column('quality_score', sa.Float(), nullable=False),
        sa.Column('enrolled_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['member_id'], ['members.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('member_id')
    )
    op.create_index(op.f('ix_biometric_templates_member_id'), 'biometric_templates', ['member_id'], unique=False)

    # Add foreign key to members table
    op.create_foreign_key('fk_members_biometric_template_id', 'members', 'biometric_templates', ['biometric_template_id'], ['id'])

    # Create memberships table
    op.create_table('memberships',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('member_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('access_rules', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['member_id'], ['members.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_memberships_member_id'), 'memberships', ['member_id'], unique=False)
    op.create_index(op.f('ix_memberships_start_date'), 'memberships', ['start_date'], unique=False)
    op.create_index(op.f('ix_memberships_end_date'), 'memberships', ['end_date'], unique=False)
    op.create_index(op.f('ix_memberships_status'), 'memberships', ['status'], unique=False)

    # Create cameras table
    op.create_table('cameras',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('rtsp_url', sa.String(length=500), nullable=False),
        sa.Column('location', sa.String(length=200), nullable=True),
        sa.Column('location_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('fps', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('resolution_width', sa.Integer(), nullable=False, server_default='1280'),
        sa.Column('resolution_height', sa.Integer(), nullable=False, server_default='720'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('confidence_threshold', sa.Float(), nullable=False, server_default='0.85'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('last_seen', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_cameras_name'), 'cameras', ['name'], unique=False)

    # Create sales_transactions table
    op.create_table('sales_transactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('member_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('membership_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('payment_method', sa.String(length=20), nullable=False),
        sa.Column('transaction_date', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('invoice_number', sa.String(length=50), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.ForeignKeyConstraint(['membership_id'], ['memberships.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('invoice_number')
    )
    op.create_index(op.f('ix_sales_transactions_member_id'), 'sales_transactions', ['member_id'], unique=False)
    op.create_index(op.f('ix_sales_transactions_transaction_date'), 'sales_transactions', ['transaction_date'], unique=False)
    op.create_index(op.f('ix_sales_transactions_invoice_number'), 'sales_transactions', ['invoice_number'], unique=False)

    # Create access_events table
    op.create_table('access_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('camera_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('member_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('access_granted', sa.Boolean(), nullable=False),
        sa.Column('denial_reason', sa.String(length=100), nullable=True),
        sa.Column('frame_snapshot_path', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['camera_id'], ['cameras.id']),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_access_events_timestamp'), 'access_events', ['timestamp'], unique=False)
    op.create_index(op.f('ix_access_events_camera_id'), 'access_events', ['camera_id'], unique=False)
    op.create_index(op.f('ix_access_events_member_id'), 'access_events', ['member_id'], unique=False)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('access_events')
    op.drop_table('sales_transactions')
    op.drop_table('cameras')
    op.drop_table('memberships')
    
    # Remove foreign key from members before dropping biometric_templates
    op.drop_constraint('fk_members_biometric_template_id', 'members', type_='foreignkey')
    
    op.drop_table('biometric_templates')
    op.drop_table('members')
    op.drop_table('users')
