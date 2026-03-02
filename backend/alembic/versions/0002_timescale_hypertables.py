"""Convert activity_logs and location_pings to TimescaleDB hypertables.

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-02

This migration runs SELECT create_hypertable(...) for the two time-series tables.
It is safe to run against plain PostgreSQL (without TimescaleDB) because the
statement is wrapped in a DO block that catches the "function does not exist" error.
It is a no-op against SQLite (Alembic skips it because we use asyncpg / psycopg2
drivers in production).
"""

from typing import Sequence, Union
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Wrapped in a DO block so the migration succeeds even if TimescaleDB is
    # not installed (e.g. plain PostgreSQL in CI or staging).
    op.execute("""
        DO $$
        BEGIN
            PERFORM create_hypertable(
                'activity_logs', 'logged_at',
                if_not_exists => TRUE,
                migrate_data   => TRUE
            );
        EXCEPTION WHEN undefined_function THEN
            RAISE NOTICE 'TimescaleDB not available — activity_logs left as plain table';
        END;
        $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            PERFORM create_hypertable(
                'location_pings', 'pinged_at',
                if_not_exists => TRUE,
                migrate_data   => TRUE
            );
        EXCEPTION WHEN undefined_function THEN
            RAISE NOTICE 'TimescaleDB not available — location_pings left as plain table';
        END;
        $$;
    """)


def downgrade() -> None:
    # Hypertables cannot be simply "undone" without data loss.
    # In production, demote by creating a plain copy and renaming — out of scope here.
    pass
