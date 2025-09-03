"""Configuration service for nl2sql-mcp.

This module provides configuration management and database connection utilities
for the nl2sql-mcp application. It centralizes environment variable handling
and database engine creation.
"""

from __future__ import annotations

import importlib.util
import os

import sqlalchemy as sa

from nl2sql_mcp.schema_tools.models import SchemaExplorerConfig
from nl2sql_mcp.schema_tools.mssql_spatial import register_mssql_spatial_types

# Optional plugin detection at import time to avoid runtime try/except.
_HAS_GEOALCHEMY2 = importlib.util.find_spec("geoalchemy2") is not None


class LLMConfig:
    """Typed configuration for the LLM provider and model.

    Values are sourced from environment variables and validated at startup.
    """

    # Keep the initializer small to satisfy lint; set attributes afterwards.
    def __init__(self, *, provider: str, model: str) -> None:
        self.provider = provider
        self.model = model
        self.temperature = 0.2
        self.top_p = 1.0
        self.top_k = 50
        self.max_output_tokens = 800


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
        # Attach optional engine plugins when available.
        # - geoalchemy2: enables reflection of PostGIS (geometry/geography) and other
        #   spatial types via SQLAlchemy's plugin hook without importing in reflection code.
        plugins: list[str] = ["geoalchemy2"] if _HAS_GEOALCHEMY2 else []

        create_kwargs: dict[str, object] = {}
        if plugins:
            create_kwargs["plugins"] = plugins

        engine = sa.create_engine(url, **create_kwargs)

        # Dialect-specific enhancements (kept minimal and testable):
        # - On SQL Server, register placeholder spatial types so reflection
        #   recognizes GEOGRAPHY/GEOMETRY columns instead of warning.
        if engine.dialect.name == "mssql":
            register_mssql_spatial_types(engine)

        return engine

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
            # Startup performance knobs
            fast_startup=True,
            max_tables_at_startup=300,
            max_sampled_columns=15,
        )

    # Unused specialized config helpers removed to reduce API surface

    # ---- LLM configuration -----------------------------------------------
    @staticmethod
    def get_llm_config() -> LLMConfig:
        """Return LLM configuration from environment variables.

        Required variables:
            - NL2SQL_MCP_LLM_PROVIDER
            - NL2SQL_MCP_LLM_MODEL

        Optional tunables with sane defaults:
            - NL2SQL_MCP_LLM_TEMPERATURE (default 0.2)
            - NL2SQL_MCP_LLM_TOP_P (default 1.0)
            - NL2SQL_MCP_LLM_TOP_K (default 50)
            - NL2SQL_MCP_LLM_MAX_OUTPUT_TOKENS (default 800)
        """
        provider = os.getenv("NL2SQL_MCP_LLM_PROVIDER")
        model = os.getenv("NL2SQL_MCP_LLM_MODEL")
        if not provider or not model:
            msg = "LLM configuration missing: set NL2SQL_MCP_LLM_PROVIDER and NL2SQL_MCP_LLM_MODEL"
            raise ValueError(msg)

        def _f(env: str, default: str) -> str:
            val = os.getenv(env)
            return val if val is not None else default

        cfg = LLMConfig(provider=provider, model=model)
        cfg.temperature = float(_f("NL2SQL_MCP_LLM_TEMPERATURE", "0.2"))
        cfg.top_p = float(_f("NL2SQL_MCP_LLM_TOP_P", "1.0"))
        cfg.top_k = int(_f("NL2SQL_MCP_LLM_TOP_K", "50"))
        cfg.max_output_tokens = int(_f("NL2SQL_MCP_LLM_MAX_OUTPUT_TOKENS", "800"))
        return cfg

    # ---- Result size budgets ---------------------------------------------
    @staticmethod
    def result_row_limit() -> int:
        """Maximum number of rows to return in results."""
        val = os.getenv("NL2SQL_MCP_ROW_LIMIT", "200")
        try:
            limit = int(val)
        except ValueError:
            limit = 200
        return max(1, limit)

    @staticmethod
    def result_max_cell_chars() -> int:
        """Maximum characters per cell value in results."""
        val = os.getenv("NL2SQL_MCP_MAX_CELL_CHARS", "200")
        try:
            n = int(val)
        except ValueError:
            n = 200
        return max(10, n)

    @staticmethod
    def result_max_payload_bytes() -> int:
        """Soft cap for serialized result payload size (bytes)."""
        val = os.getenv("NL2SQL_MCP_MAX_RESULT_BYTES", "200000")
        try:
            n = int(val)
        except ValueError:
            n = 200000
        return max(50000, n)
