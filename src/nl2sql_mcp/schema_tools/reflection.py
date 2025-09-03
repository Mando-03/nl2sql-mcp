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
from geoalchemy2 import Geometry
import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.engine.reflection import Inspector

from .exceptions import ReflectionError
from .utils import default_excluded_schemas

# Logger
_logger = get_logger("schema_explorer.reflection")

# Not used directlybut must be imported for geoalchemy2
_ = Geometry


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

    def list_schemas(self) -> list[str]:
        """List database schemas with filtering applied.

        Retrieves all available schema names from the database and applies
        include/exclude filtering. System schemas are excluded by default
        based on the database dialect.

        Returns:
            List of schema names to process

        Raises:
            ReflectionError: If schema listing fails critically
        """
        try:
            schemas = self.inspector.get_schema_names()
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
            schemas_to_process = self.list_schemas()
        except Exception as e:
            error_msg = f"Failed to list database schemas: {e}"
            raise ReflectionError(error_msg) from e

        for schema in schemas_to_process:
            _logger.debug("Reflecting schema: %s", schema)

            try:
                tables = self.inspector.get_table_names(schema=schema)
            except Exception as e:  # noqa: BLE001 - Skip schema on any database error
                _logger.warning("Cannot list tables for schema %s: %s", schema, e)
                continue

            payload["schemas"][schema] = {"tables": {}}

            for table in tables:
                _logger.debug("Reflecting table: %s.%s", schema, table)

                # Get column information
                try:
                    columns_metadata = self.inspector.get_columns(table, schema=schema)
                except Exception as e:  # noqa: BLE001 - Skip table on any database error
                    _logger.warning("Cannot get columns for %s.%s: %s", schema, table, e)
                    continue

                # Get primary key constraint
                try:
                    pk_constraint = self.inspector.get_pk_constraint(table, schema=schema)
                    primary_key_columns = pk_constraint.get("constrained_columns", []) or []
                except Exception as e:  # noqa: BLE001 - Continue without PK info
                    _logger.debug("Cannot get PK for %s.%s: %s", schema, table, e)
                    primary_key_columns = []

                # Get foreign key constraints
                foreign_keys = []
                try:
                    fk_constraints = self.inspector.get_foreign_keys(table, schema=schema)
                    for fk in fk_constraints:
                        ref_schema = fk.get("referred_schema") or schema
                        ref_table = fk.get("referred_table")

                        # Process each column in the foreign key
                        constrained_cols = fk.get("constrained_columns", [])
                        referred_cols = fk.get("referred_columns", [])

                        for local_col, ref_col in zip(
                            constrained_cols, referred_cols, strict=False
                        ):
                            foreign_keys.append((local_col, f"{ref_schema}.{ref_table}", ref_col))
                except Exception as e:  # noqa: BLE001 - Continue without FK info
                    _logger.debug("Cannot get FKs for %s.%s: %s", schema, table, e)

                # Get table comment if enabled
                table_comment = None
                if get_comments:
                    try:
                        comment_info = self.inspector.get_table_comment(table, schema=schema)
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

        return payload
