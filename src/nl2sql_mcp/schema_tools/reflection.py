"""Database schema reflection adapter.

This module provides the ReflectionAdapter class that handles database
schema reflection using SQLAlchemy. It abstracts the complexity of
querying database metadata and provides a consistent interface for
schema discovery across different database dialects.

Classes:
- ReflectionAdapter: Main class for database schema reflection
"""

from __future__ import annotations

from typing import Any

from fastmcp.utilities.logging import get_logger
import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.engine.reflection import Inspector

from .exceptions import ReflectionError
from .utils import default_excluded_schemas

# Logger
_logger = get_logger("schema_explorer.reflection")


class ReflectionAdapter:
    """Adapter for database schema reflection using SQLAlchemy.

    This class handles the complexity of reflecting database schema metadata
    across different database dialects. It provides schema filtering capabilities
    and handles common edge cases in metadata retrieval.

    Attributes:
        engine: SQLAlchemy engine for database connections
        inspector: SQLAlchemy inspector for metadata queries
        include_schemas: Optional list of schemas to include (whitelist)
        exclude_schemas: Optional list of schemas to exclude (blacklist)
    """

    def __init__(
        self,
        engine: Engine,
        include_schemas: list[str] | None = None,
        exclude_schemas: list[str] | None = None,
        *,
        fast_startup: bool = False,
        max_tables_at_startup: int | None = None,
        reflect_timeout_sec: int | None = None,
    ) -> None:
        """Initialize the reflection adapter.

        Args:
            engine: SQLAlchemy engine connected to the database
            include_schemas: Optional whitelist of schema names to include
            exclude_schemas: Optional blacklist of schema names to exclude
        """
        self.engine = engine
        self.inspector: Inspector = sa.inspect(engine)
        self.include_schemas = include_schemas
        self.exclude_schemas = exclude_schemas
        self.fast_startup = fast_startup
        self.max_tables_at_startup = max_tables_at_startup
        self._reflect_timeout_sec = reflect_timeout_sec

    def list_schemas(self, *, inspector: Inspector | None = None) -> list[str]:
        """List database schemas with filtering applied.

        Retrieves all available schema names from the database and applies
        include/exclude filtering. System schemas are excluded by default
        based on the database dialect.

        Returns:
            List of schema names to process

        Raises:
            ReflectionError: If schema listing fails critically
        """
        insp = inspector or self.inspector
        try:
            schemas = insp.get_schema_names()
        except Exception as e:  # noqa: BLE001 - Fallback on any database error
            _logger.warning("Could not list schemas, falling back to 'public': %s", e)
            schemas = ["public"]

        # Build exclusion set with system schemas
        excluded_set = {
            schema.lower()
            for schema in (
                self.exclude_schemas or default_excluded_schemas(self.engine.dialect.name)
            )
        }

        # Filter out system schemas and custom exclusions
        filtered_schemas = [
            schema
            for schema in schemas
            if (schema.lower() not in excluded_set and not schema.lower().startswith("db_"))
        ]

        # Apply include filter if specified
        if self.include_schemas:
            allowed_set = {schema.lower() for schema in self.include_schemas}
            filtered_schemas = [
                schema for schema in filtered_schemas if schema.lower() in allowed_set
            ]

        return filtered_schemas

    def reflect(self) -> dict[str, Any]:
        """Reflect complete database schema metadata.

        Performs comprehensive schema reflection, gathering information about
        tables, columns, primary keys, foreign keys, and comments across
        all included schemas.

        Returns:
            Dictionary containing complete schema metadata with structure:
            {
                "dialect": str,
                "schemas": {
                    "schema_name": {
                        "tables": {
                            "table_name": {
                                "columns": [...],
                                "pk": [...],
                                "fks": [...],
                                "comment": str | None
                            }
                        }
                    }
                }
            }

        Raises:
            ReflectionError: If reflection fails completely
        """
        payload: dict[str, Any] = {"schemas": {}, "dialect": str(self.engine.dialect)}

        # Comments are disabled by default for speed and portability
        get_comments = False

        try:
            # Use a dedicated connection to apply per-session timeouts
            with self.engine.connect() as conn:
                self._apply_reflection_timeout(conn)
                local_insp: Inspector = sa.inspect(conn)

                _logger.info("Listing schemas for reflection…")
                schemas_to_process = self.list_schemas(inspector=local_insp)
        except Exception as e:
            error_msg = f"Failed to list database schemas: {e}"
            raise ReflectionError(error_msg) from e

        processed_tables = 0
        max_tables = self.max_tables_at_startup if self.max_tables_at_startup else None

        _logger.info("Found %d candidate schemas", len(schemas_to_process))

        # Re-open a connection for the heavy loop to ensure timeout remains applied
        with self.engine.connect() as conn:
            self._apply_reflection_timeout(conn)
            local_insp = sa.inspect(conn)

            for schema in schemas_to_process:
                _logger.info("Fetching tables for schema: %s", schema)

                try:
                    tables = local_insp.get_table_names(schema=schema)
                except Exception as e:  # noqa: BLE001 - Skip schema on any database error
                    _logger.warning("Cannot list tables for schema %s: %s", schema, e)
                    continue

                _logger.info("%s: %d tables", schema, len(tables))
                payload["schemas"][schema] = {"tables": {}}

                for table in tables:
                    _logger.debug("Reflecting table: %s.%s", schema, table)

                    # Respect global startup cap on number of tables reflected
                    if max_tables is not None and processed_tables >= max_tables:
                        _logger.info(
                            "Reached reflection cap (max_tables_at_startup=%s); stopping early",
                            max_tables,
                        )
                        return payload

                    # Get column information
                    try:
                        columns_metadata = local_insp.get_columns(table, schema=schema)
                    except Exception as e:  # noqa: BLE001 - Skip table on any database error
                        _logger.warning("Cannot get columns for %s.%s: %s", schema, table, e)
                        continue

                    # Get primary key constraint
                    try:
                        pk_constraint = local_insp.get_pk_constraint(table, schema=schema)
                        primary_key_columns = pk_constraint.get("constrained_columns", []) or []
                    except Exception as e:  # noqa: BLE001 - Continue without PK info
                        _logger.debug("Cannot get PK for %s.%s: %s", schema, table, e)
                        primary_key_columns = []

                    # Get foreign key constraints (skip on fast startup for speed)
                    foreign_keys: list[tuple[str, str, str]] = []
                    if not self.fast_startup:
                        foreign_keys = self._get_foreign_keys(schema, table, inspector=local_insp)

                    # Get table comment if enabled
                    table_comment = None
                    if get_comments:
                        try:
                            comment_info = local_insp.get_table_comment(table, schema=schema)
                            table_comment = comment_info.get("text")
                        except Exception as e:  # noqa: BLE001 - Continue without comment
                            _logger.debug("Cannot get comment for %s.%s: %s", schema, table, e)

                    # Build table metadata
                    payload["schemas"][schema]["tables"][table] = {
                        "columns": [
                            {
                                "name": col["name"],
                                "type": str(col["type"]),
                                "nullable": col.get("nullable", True),
                                "comment": col.get("comment"),
                            }
                            for col in columns_metadata
                        ],
                        "pk": primary_key_columns,
                        "fks": foreign_keys,
                        "comment": table_comment,
                    }

                    processed_tables += 1

        return payload

    # ---- internals ---------------------------------------------------------
    def _get_foreign_keys(
        self, schema: str, table: str, *, inspector: Inspector | None = None
    ) -> list[tuple[str, str, str]]:
        """Fetch foreign key relationships for a table with robust fallbacks."""
        insp = inspector or self.inspector
        try:
            fk_constraints = insp.get_foreign_keys(table, schema=schema)
        except Exception as e:  # noqa: BLE001 - Continue without FK info
            _logger.debug("Cannot get FKs for %s.%s: %s", schema, table, e)
            return []

        fks: list[tuple[str, str, str]] = []
        for fk in fk_constraints:
            ref_schema = fk.get("referred_schema") or schema
            ref_table = fk.get("referred_table")
            constrained_cols = fk.get("constrained_columns", [])
            referred_cols = fk.get("referred_columns", [])
            for local_col, ref_col in zip(constrained_cols, referred_cols, strict=False):
                fks.append((local_col, f"{ref_schema}.{ref_table}", ref_col))
        return fks

    def _apply_reflection_timeout(self, conn: Connection) -> None:
        """Apply a per-connection timeout suitable for metadata reflection.

        Best-effort, dialect-specific:
        - PostgreSQL: SET statement_timeout = <ms>
        - MySQL:      SET SESSION MAX_EXECUTION_TIME = <ms>
        - SQL Server: SET LOCK_TIMEOUT <ms>
        """
        timeout_sec = self._reflect_timeout_sec
        if not timeout_sec or timeout_sec <= 0:
            return
        try:
            dialect = self.engine.dialect.name
            ms = max(1, int(timeout_sec * 1000))
            if dialect == "postgresql":
                conn.execute(sa.text("SET statement_timeout = :ms"), {"ms": ms})
            elif dialect in {"mysql", "mariadb"}:
                # MySQL 5.7+ / MariaDB: MAX_EXECUTION_TIME (may be ignored if unsupported)
                conn.execute(sa.text("SET SESSION MAX_EXECUTION_TIME = :ms"), {"ms": ms})
            elif dialect == "mssql":
                # Reduces lock wait time; not a full statement timeout but helps avoid hangs
                conn.execute(sa.text(f"SET LOCK_TIMEOUT {ms}"))
        except Exception as e:  # noqa: BLE001 - best-effort guard
            _logger.debug("Could not apply reflection timeout: %s", e)
