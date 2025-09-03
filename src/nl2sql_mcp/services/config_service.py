"""Configuration service for nl2sql-mcp.

This module provides configuration management and database connection utilities
for the nl2sql-mcp application. It centralizes environment variable handling
and database engine creation.
"""

from __future__ import annotations

import os

import sqlalchemy as sa

from nl2sql_mcp.schema_tools.models import SchemaExplorerConfig


class ConfigService:
    """Service for managing configuration and database connections."""

    @staticmethod
    def get_database_url() -> str:
        """Get database URL from environment variable.

        Returns:
            Database URL string

        Raises:
            ValueError: If NL2SQL_MCP_DATABASE_URL environment variable is not set
        """
        database_url = os.getenv("NL2SQL_MCP_DATABASE_URL")
        if not database_url:
            error_msg = "NL2SQL_MCP_DATABASE_URL environment variable not set"
            raise ValueError(error_msg)
        return database_url

    @staticmethod
    def create_database_engine(url: str) -> sa.Engine:
        """Create SQLAlchemy database engine.

        Args:
            url: Database connection URL

        Returns:
            SQLAlchemy Engine instance
        """
        return sa.create_engine(url)

    @staticmethod
    def create_schema_explorer_config_default() -> SchemaExplorerConfig:
        """Return a default `SchemaExplorerConfig`.

        Prefer the specific helper `get_query_analysis_config` for tuned values
        used by query-time operations.
        """
        return SchemaExplorerConfig()

    @staticmethod
    def get_query_analysis_config() -> SchemaExplorerConfig:
        """Get configuration optimized for query analysis.

        Returns:
            SchemaExplorerConfig optimized for query analysis operations
        """
        return SchemaExplorerConfig(
            per_table_rows=50,  # Enough for good samples
            sample_timeout=15,
            build_column_index=True,
            max_cols_for_embeddings=20,
            expander="fk_following",
            min_area_size=2,
            merge_archive_areas=True,
            value_constraint_threshold=20,
        )

    # Unused specialized config helpers removed to reduce API surface
