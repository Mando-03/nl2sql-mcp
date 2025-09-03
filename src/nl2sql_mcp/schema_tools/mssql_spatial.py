"""MSSQL spatial type support for reflection.

This module provides minimal SQLAlchemy ``TypeEngine`` implementations for
SQL Server's native spatial types (``GEOGRAPHY`` and ``GEOMETRY``) and a
helper to register them with the active MSSQL dialect so that reflection
does not emit warnings like:

    SAWarning: Did not recognize type 'geography' of column '...'

The goal is portability and clean metadata reflection; no spatial operations
are implemented here. If your application needs server-side spatial
functions, prefer PostGIS with GeoAlchemy2 or a dedicated SQL Server
spatial extension.
"""

from __future__ import annotations

from fastmcp.utilities.logging import get_logger
import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.sql.type_api import TypeEngine

_logger = get_logger("schema_explorer.mssql_spatial")


class MSSQLGeography(sa.types.UserDefinedType[bytes]):
    """Placeholder type for SQL Server ``GEOGRAPHY``.

    This type is designed for reflection correctness. It renders as
    ``GEOGRAPHY`` in DDL and stringification and does not attempt to
    implement Python-side bind/result processing.
    """

    cache_ok = True

    def get_col_spec(self, **_: object) -> str:
        """Return the DDL column specification (``GEOGRAPHY``)."""
        return "GEOGRAPHY"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.get_col_spec()


class MSSQLGeometry(sa.types.UserDefinedType[bytes]):
    """Placeholder type for SQL Server ``GEOMETRY``.

    Same intent as ``MSSQLGeography``: eliminate reflection warnings and
    provide a stable, typed handle for column metadata.
    """

    cache_ok = True

    def get_col_spec(self, **_: object) -> str:
        """Return the DDL column specification (``GEOMETRY``)."""
        return "GEOMETRY"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.get_col_spec()


def register_mssql_spatial_types(engine: Engine) -> None:
    """Register MSSQL spatial types with an engine's dialect for reflection.

    This function safely augments the dialect's internal ``ischema_names``
    mapping used during ``Inspector.get_columns`` so that SQLAlchemy maps
    the server types ``geography`` and ``geometry`` to placeholder Python
    types instead of emitting warnings and using ``NullType``.

    The function is idempotent and a no-op for non-MSSQL dialects.

    Args:
        engine: An initialized SQLAlchemy engine.
    """

    dialect_name = engine.dialect.name
    if dialect_name != "mssql":
        return

    # Many dialects expose an ``ischema_names`` dict mapping lower-case
    # database type names to TypeEngine classes used during reflection.
    # We augment it if present.
    mapping: dict[str, TypeEngine[bytes] | type[TypeEngine[bytes]]] | None = getattr(
        engine.dialect, "ischema_names", None
    )

    if mapping is None:
        # Be conservative: if the dialect does not expose the mapping, we do
        # not attempt any monkey-patching. Reflection will continue to work
        # but may warn on spatial columns.
        _logger.debug("MSSQL dialect has no ischema_names; skipping spatial registration.")
        return

    # Register only if not already provided by the environment.
    if "geography" not in mapping:
        mapping["geography"] = MSSQLGeography
        _logger.debug("Registered MSSQL 'geography' type for reflection.")

    if "geometry" not in mapping:
        mapping["geometry"] = MSSQLGeometry
        _logger.debug("Registered MSSQL 'geometry' type for reflection.")
