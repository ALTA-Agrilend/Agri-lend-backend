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


def run_startup_migrations(sync_conn) -> None:
    is_postgres = sync_conn.dialect.name == "postgresql"
    for table, column, pg_type, sqlite_type in TABLE_COLUMNS:
        stmt = text(f"ALTER TABLE {table} ADD COLUMN {column} {pg_type if is_postgres else sqlite_type}")
        try:
            sync_conn.execute(stmt)
            logger.info("Startup migration applied: %s", stmt)
        except Exception as exc:  # column already exists
            logger.debug("Startup migration skipped (%s.%s): %s", table, column, exc)

    for table, column in DROP_COLUMNS:
        if not _column_exists(sync_conn, table, column):
            continue
        try:
            sync_conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))
            logger.info("Startup migration applied: dropped %s.%s", table, column)
        except Exception as exc:  # SQLite pre-3.35 or permission issue
            logger.warning("Could not drop %s.%s (legacy column kept): %s", table, column, exc)

    for table, column, stmt in BACKFILLS:
        if _column_exists(sync_conn, table, column):
            sync_conn.execute(text(stmt))
