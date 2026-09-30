"""Settings, read from the environment in exactly one place.

Why a single place
------------------
`os.environ` read at the point of use scatters the answer to "what does this
deployment need to be told" across the codebase, and makes a missing variable
fail wherever it happens to be touched first. That is not hypothetical here: a
missing `DATABASE_URL` used to surface as a bare `KeyError` from whichever module
happened to be imported first, with nothing to say about what to do next.

No settings library
-------------------
`pydantic-settings` would be a dependency for what a frozen dataclass and one
function already do. This project has preferred the standard library wherever it
is enough, and this is a case where it is.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

__all__ = ["Settings", "load_settings", "settings"]


_MISSING_DATABASE_URL = (
    "DATABASE_URL is not set. Nothing falls back to a built-in connection "
    "string: a default is how a deployment ends up pointing at the wrong "
    "database, and it fails silently when it does."
)


@dataclass(frozen=True)
class Settings:
    """Everything the application reads from its environment."""

    # The schema owner. Alembic uses it, because migrations need DDL rights.
    database_url: str

    # A non-superuser login role, which the application itself uses so that row
    # level security on tenant.* actually applies -- a superuser bypasses it
    # entirely, which is what once made the tenant policies inert.
    #
    # Falls back to the owner so a single-credential setup and the SQLite test
    # suite keep working unchanged.
    app_database_url: str

    @property
    def uses_separate_app_role(self) -> bool:
        """Whether row level security is actually in force for the application."""

        return self.app_database_url != self.database_url


def load_settings() -> Settings:
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError(_MISSING_DATABASE_URL)

    return Settings(
        database_url=database_url,
        app_database_url=os.environ.get("APP_DATABASE_URL") or database_url,
    )


# Read once at import, which is where a missing variable should fail: at startup,
# with a message, rather than on the first request that needs it.
settings = load_settings()
