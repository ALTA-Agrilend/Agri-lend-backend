from sqlalchemy import text

from app.core.logging import logger

# Column additions that pre-date Base.metadata.create_all on existing databases.
# create_all only creates missing tables, never new columns.
TABLE_COLUMNS = [
    ("users", "bank_id"),
    ("farmer_profiles", "registered_by_bank_id"),
]


def run_startup_migrations(sync_conn) -> None:
    col_type = "UUID" if sync_conn.dialect.name == "postgresql" else "CHAR(32)"
    for table, column in TABLE_COLUMNS:
        stmt = text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        try:
            sync_conn.execute(stmt)
            logger.info("Startup migration applied: %s", stmt)
        except Exception as exc:  # column already exists
            logger.debug("Startup migration skipped (%s.%s): %s", table, column, exc)
