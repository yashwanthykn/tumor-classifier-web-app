"""Alembic migration environment.

Imports our SQLAlchemy Base so autogenerate can detect model changes.
Reads DATABASE_URL from environment so we never hardcode credentials.
"""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import create_engine, pool
from alembic import context

# Ensure the app package is importable when running from /app/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Import our app's metadata ────────────────────────────────────────
from app.database.database import DATABASE_URL, Base
from app.database import models  # noqa: F401 — registers models on Base.metadata

# ── Alembic Config ───────────────────────────────────────────────────
config = context.config

# NOTE: We do NOT use config.set_main_option("sqlalchemy.url", ...)
# because configparser chokes on % characters in passwords.
# Instead we pass DATABASE_URL directly to create_engine below.

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Tell Alembic what our models look like
target_metadata = Base.metadata

# ── Tables managed by create_all(), not Alembic ─────────────────────
EXISTING_TABLES = {"users", "predictions"}


def include_object(object, name, type_, reflected, compare_to):
    """Skip tables that are managed by Base.metadata.create_all()."""
    if type_ == "table" and name in EXISTING_TABLES:
        return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — generates SQL without a DB connection."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — connects to DB and applies changes."""
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
