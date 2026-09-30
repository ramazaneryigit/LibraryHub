import os
import sys
from pathlib import Path
from logging.config import fileConfig

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from alembic import context
from sqlalchemy import create_engine, pool

from app.db.base import Base

# Imported for its side effect: every model module registers its tables on
# `Base.metadata`, and autogenerate compares that metadata against the database.
# Without this, Alembic would believe every table should be dropped.
from app.db import models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    """Resolve the URL migrations connect with.

    Only the environment is trusted, and there is no fallback. `alembic.ini` used
    to carry a development connection string with a password in it, which is a
    credential committed to the repository; worse, a fallback can silently win or
    silently lose, and that is how migrations end up running against the wrong
    database. Refusing to guess is better than guessing wrong.
    """
    url = os.environ.get("DATABASE_URL")

    if url:
        return url

    raise RuntimeError(
        "DATABASE_URL is not set. Alembic will not fall back to a built-in "
        "connection string: set DATABASE_URL to the database you intend to "
        "migrate."
    )


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Built directly rather than through engine_from_config: that path reads the
    # URL back out of the ini file and escapes '%' characters, which a password
    # can legitimately contain.
    connectable = create_engine(
        database_url(),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Architecture v2 puts the Control Plane in the `control` schema
            # and the Tenant Data Plane in `tenant`. Without this, autogenerate
            # only reflects the default schema, does not see those tables in
            # the database, and reports every model in them as a brand new
            # table -- so `alembic check` fails even when nothing drifted.
            include_schemas=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()