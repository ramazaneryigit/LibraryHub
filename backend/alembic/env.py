import os
import sys
from pathlib import Path
from logging.config import fileConfig

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from alembic import context
from sqlalchemy import create_engine, pool

from app.db import Base
from app import models

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    """Resolve the URL migrations connect with.

    DATABASE_URL wins over the value committed in alembic.ini. That ini value is
    kept only as a development fallback so offline SQL generation works without
    an environment; the running configuration should come from the environment
    like every other credential. Until this precedence existed, a deployment
    that changed DATABASE_URL still ran migrations against whatever alembic.ini
    happened to say.
    """
    return os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url")


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