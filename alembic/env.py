"""Alembic migration environment."""

import logging

from alembic import context
from sqlalchemy import engine_from_config, pool

from ai_usage.orm import Base

config = context.config
# Deliberately not calling logging.config.fileConfig(alembic.ini) here: it reconfigures the
# root logger's handlers/level on every migrate() call, clobbering the app's own logging setup
# (and, with disable_existing_loggers=True, silencing every already-created logger). Set only
# what alembic.ini's logging section was actually for.
logging.getLogger("alembic").setLevel(logging.INFO)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
    # end with
# end def


def run_migrations_online() -> None:
    engine = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        # end with
    # end with
    engine.dispose()
# end def


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
# end if
