import sqlalchemy as sa
from sqlalchemy import text

from app.core.logging import logger

# Column additions/removals that pre-date Base.metadata.create_all on existing databases.
# create_all only creates missing tables, never alters existing ones.
# (table, column, postgres_type, sqlite_type)
TABLE_COLUMNS = [
    ("users", "bank_id", "UUID", "CHAR(32)"),
    ("farmer_profiles", "registered_by_bank_id", "UUID", "CHAR(32)"),
    ("bank_partners", "interest_rate", "NUMERIC(5,2)", "NUMERIC"),
    ("loan_applications", "interest_rate_applied", "NUMERIC(5,2)", "NUMERIC"),
    ("loan_applications", "repayment_amount", "NUMERIC(12,2)", "NUMERIC"),
]

DROP_COLUMNS = [
    # API-key authentication was removed; banks log in with accounts only.
    ("bank_partners", "api_key_hash"),
]

# Data backfills for columns added to pre-existing tables.
BACKFILLS = [
    ("bank_partners", "interest_rate", "UPDATE bank_partners SET interest_rate = 12.0 WHERE interest_rate IS NULL"),
]


def _column_exists(sync_conn, table: str, column: str) -> bool:
    res = sync_conn.execute(
        text(
            "SELECT count(*) FROM pragma_table_info(:table) WHERE name = :col"
            if sync_conn.dialect.name == "sqlite"
            else "SELECT count(*) FROM information_schema.columns "
                 "WHERE table_name = :table AND column_name = :col"
        ),
        {"table": table, "col": column},
    )
    return (res.scalar() or 0) > 0


def _run_isolated(sync_conn, fn, description: str) -> bool:
    """Run a migration step inside a SAVEPOINT so a failure (e.g. duplicate
    column on Postgres) rolls back cleanly instead of poisoning the whole
    startup transaction with InFailedSQLTransactionError."""
    try:
        with sync_conn.begin_nested():
            fn()
        logger.info("Startup migration applied: %s", description)
        return True
    except Exception as exc:
        logger.debug("Startup migration skipped (%s): %s", description, exc)
        return False


def run_startup_migrations(sync_conn) -> None:
    is_postgres = sync_conn.dialect.name == "postgresql"

    for table, column, pg_type, sqlite_type in TABLE_COLUMNS:
        if _column_exists(sync_conn, table, column):
            continue
        col_type = pg_type if is_postgres else sqlite_type
        _run_isolated(
            sync_conn,
            lambda t=table, c=column, ct=col_type: sync_conn.execute(
                text(f"ALTER TABLE {t} ADD COLUMN {c} {ct}")
            ),
            f"add {table}.{column}",
        )

    for table, column in DROP_COLUMNS:
        if not _column_exists(sync_conn, table, column):
            continue
        _run_isolated(
            sync_conn,
            lambda t=table, c=column: sync_conn.execute(text(f"ALTER TABLE {t} DROP COLUMN {c}")),
            f"drop {table}.{column}",
        )

    for table, column, stmt in BACKFILLS:
        if _column_exists(sync_conn, table, column):
            _run_isolated(sync_conn, lambda s=stmt: sync_conn.execute(text(s)), stmt[:60])

    # Farmer accounts no longer require an email — relax NOT NULL on users.email.
    def _relax_email_not_null():
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        ctx = MigrationContext.configure(sync_conn)
        ops = Operations(ctx)
        with ops.batch_alter_table("users", schema=None) as batch_op:
            batch_op.alter_column("email", existing_type=sa.String(255), nullable=True)

    _run_isolated(sync_conn, _relax_email_not_null, "users.email nullable")
