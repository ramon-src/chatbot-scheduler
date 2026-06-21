"""Initial migration

Revision ID: 0001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create schema
    op.execute('CREATE SCHEMA IF NOT EXISTS simplificapsi')
    
    # Create extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
    
    # Create users table
    op.create_table('users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('phone'),
        schema='simplificapsi'
    )
    
    # Create clients table
    op.create_table('clients',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('birth_date', sa.Date(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['simplificapsi.users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema='simplificapsi'
    )
    
    # Create calendars table
    op.create_table('calendars',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('google_calendar_id', sa.String(length=255), nullable=True),
        sa.Column('is_primary', sa.Boolean(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['simplificapsi.users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('google_calendar_id'),
        schema='simplificapsi'
    )
    
    # Create events table
    op.create_table('events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('client_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('calendar_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_recurring', sa.Boolean(), nullable=False),
        sa.Column('recurrence_rule', sa.String(length=255), nullable=True),
        sa.Column('google_event_id', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('payment_status', sa.String(length=50), nullable=False),
        sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['calendar_id'], ['simplificapsi.calendars.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['client_id'], ['simplificapsi.clients.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['simplificapsi.users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('google_event_id'),
        schema='simplificapsi'
    )
    
    # Create chat_sessions table
    op.create_table('chat_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', sa.String(length=255), nullable=False),
        sa.Column('phone_number', sa.String(length=20), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['simplificapsi.users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'session_id'),
        schema='simplificapsi'
    )
    
    # Create chat_messages table
    op.create_table('chat_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('message_type', sa.String(length=50), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['simplificapsi.chat_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema='simplificapsi'
    )
    
    # Create indexes
    op.create_index('idx_users_email', 'users', ['email'], unique=False, schema='simplificapsi')
    op.create_index('idx_users_phone', 'users', ['phone'], unique=False, schema='simplificapsi')
    op.create_index('idx_users_active', 'users', ['is_active'], unique=False, schema='simplificapsi')
    
    op.create_index('idx_clients_user_id', 'clients', ['user_id'], unique=False, schema='simplificapsi')
    op.create_index('idx_clients_phone', 'clients', ['phone'], unique=False, schema='simplificapsi')
    op.create_index('idx_clients_email', 'clients', ['email'], unique=False, schema='simplificapsi')
    op.create_index('idx_clients_name', 'clients', ['name'], unique=False, schema='simplificapsi')
    op.create_index('idx_clients_active', 'clients', ['is_active'], unique=False, schema='simplificapsi')
    
    op.create_index('idx_calendars_user_id', 'calendars', ['user_id'], unique=False, schema='simplificapsi')
    op.create_index('idx_calendars_google_id', 'calendars', ['google_calendar_id'], unique=False, schema='simplificapsi')
    op.create_index('idx_calendars_primary', 'calendars', ['is_primary'], unique=False, schema='simplificapsi')
    
    op.create_index('idx_events_user_id', 'events', ['user_id'], unique=False, schema='simplificapsi')
    op.create_index('idx_events_client_id', 'events', ['client_id'], unique=False, schema='simplificapsi')
    op.create_index('idx_events_calendar_id', 'events', ['calendar_id'], unique=False, schema='simplificapsi')
    op.create_index('idx_events_start_time', 'events', ['start_time'], unique=False, schema='simplificapsi')
    op.create_index('idx_events_end_time', 'events', ['end_time'], unique=False, schema='simplificapsi')
    op.create_index('idx_events_google_id', 'events', ['google_event_id'], unique=False, schema='simplificapsi')
    op.create_index('idx_events_status', 'events', ['status'], unique=False, schema='simplificapsi')
    op.create_index('idx_events_payment_status', 'events', ['payment_status'], unique=False, schema='simplificapsi')
    op.create_index('idx_events_recurring', 'events', ['is_recurring'], unique=False, schema='simplificapsi')
    
    op.create_index('idx_chat_sessions_user_id', 'chat_sessions', ['user_id'], unique=False, schema='simplificapsi')
    op.create_index('idx_chat_sessions_session_id', 'chat_sessions', ['session_id'], unique=False, schema='simplificapsi')
    op.create_index('idx_chat_sessions_phone', 'chat_sessions', ['phone_number'], unique=False, schema='simplificapsi')
    op.create_index('idx_chat_sessions_active', 'chat_sessions', ['is_active'], unique=False, schema='simplificapsi')
    
    op.create_index('idx_chat_messages_session_id', 'chat_messages', ['session_id'], unique=False, schema='simplificapsi')
    op.create_index('idx_chat_messages_type', 'chat_messages', ['message_type'], unique=False, schema='simplificapsi')
    op.create_index('idx_chat_messages_created_at', 'chat_messages', ['created_at'], unique=False, schema='simplificapsi')
    
    # Create triggers for updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)
    
    op.execute("""
        CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON simplificapsi.users
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)
    
    op.execute("""
        CREATE TRIGGER update_clients_updated_at BEFORE UPDATE ON simplificapsi.clients
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)
    
    op.execute("""
        CREATE TRIGGER update_calendars_updated_at BEFORE UPDATE ON simplificapsi.calendars
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)
    
    op.execute("""
        CREATE TRIGGER update_events_updated_at BEFORE UPDATE ON simplificapsi.events
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)
    
    op.execute("""
        CREATE TRIGGER update_chat_sessions_updated_at BEFORE UPDATE ON simplificapsi.chat_sessions
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)


def downgrade() -> None:
    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS update_chat_sessions_updated_at ON simplificapsi.chat_sessions")
    op.execute("DROP TRIGGER IF EXISTS update_events_updated_at ON simplificapsi.events")
    op.execute("DROP TRIGGER IF EXISTS update_calendars_updated_at ON simplificapsi.calendars")
    op.execute("DROP TRIGGER IF EXISTS update_clients_updated_at ON simplificapsi.clients")
    op.execute("DROP TRIGGER IF EXISTS update_users_updated_at ON simplificapsi.users")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")
    
    # Drop tables
    op.drop_table('chat_messages', schema='simplificapsi')
    op.drop_table('chat_sessions', schema='simplificapsi')
    op.drop_table('events', schema='simplificapsi')
    op.drop_table('calendars', schema='simplificapsi')
    op.drop_table('clients', schema='simplificapsi')
    op.drop_table('users', schema='simplificapsi')
    
    # Drop schema
    op.execute('DROP SCHEMA IF EXISTS simplificapsi')

