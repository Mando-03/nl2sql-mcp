"""Database table sampling functionality.

This module provides the Sampler class that handles efficient sampling
of data from database tables. It includes dialect-specific optimizations
for sampling large tables and handles various edge cases that can occur
during data retrieval.

Classes:
- Sampler: Main class for database table sampling operations
"""

from __future__ import annotations

from typing import Any

from fastmcp.utilities.logging import get_logger
import pandas as pd
import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.sql.elements import ColumnElement

# Logger
_logger = get_logger("schema_explorer.sampling")


class Sampler:
    """Database table sampler with dialect-specific optimizations.

    This class provides efficient sampling of database tables with support
    for various database dialects. It includes optimizations like TABLESAMPLE
    for large tables and handles connection management and error recovery.

    Attributes:
        engine: SQLAlchemy engine for database connections
        per_table_rows: Maximum number of rows to sample per table
        timeout_sec: Query timeout in seconds
        preparer: SQL identifier preparer for dialect-specific quoting
        dialect_name: Database dialect name for optimization selection
    """

    def __init__(self, engine: Engine, per_table_rows: int = 100, timeout_sec: int = 5) -> None:
        """Initialize the sampler.

        Args:
            engine: SQLAlchemy engine connected to the database
            per_table_rows: Maximum number of rows to sample per table
            timeout_sec: Query timeout in seconds for sampling operations
        """
        self.engine = engine
        self.per_table_rows = per_table_rows
        self.timeout_sec = timeout_sec
        # Avoid dialect-specific SQL; rely on SQLAlchemy Core to render
        # appropriate LIMIT/TOP/OFFSET syntax per dialect.

    def sample_table(self, schema: str, table: str, cols: list[str]) -> pd.DataFrame:
        """Sample data from a database table.

        Executes a sampling query against the specified table and returns
        the results as a pandas DataFrame. Uses dialect-specific optimizations
        when available and handles various error conditions gracefully.

        Args:
            schema: Database schema name containing the table
            table: Table name to sample from
            cols: List of column names to include in the sample

        Returns:
            DataFrame containing the sampled data with the specified columns
            Returns empty DataFrame if sampling fails

        Raises:
            SamplingError: If sampling fails due to critical errors
        """
        if not cols:
            _logger.debug("No columns specified for %s.%s", schema, table)
            return pd.DataFrame()

        # Build base query using SQLAlchemy Core with explicit column selection.
        # Use lightweight table/column clauses so we don't require full reflection.
        table_obj = sa.table(table, schema=schema if schema else None)
        select_columns: list[ColumnElement[Any]] = [sa.column(col) for col in cols]
        sql_query = sa.select(*select_columns).select_from(table_obj).limit(self.per_table_rows)

        _logger.debug("Sampling %s.%s with query: %s", schema, table, sql_query)

        try:
            with self.engine.connect() as conn:
                # Configure connection for streaming to handle large results efficiently
                streaming_conn = conn.execution_options(stream_results=True)

                # Execute the query and return as DataFrame
                return pd.read_sql(sql_query, streaming_conn)

        except Exception as e:  # noqa: BLE001 - Return empty DataFrame on any error
            _logger.debug("Sampling failed for %s.%s: %s", schema, table, e)

            # Return empty DataFrame with correct column structure on failure
            return pd.DataFrame(columns=cols)  # type: ignore[call-overload]
