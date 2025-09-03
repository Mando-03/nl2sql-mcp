"""MCP tool registration for sqlglot helpers.

This module exposes a single function `register_sqlglot_tools` that attaches
LLM-friendly tools to a provided FastMCP instance, delegating logic to
`SqlglotService` and auto-selecting the target dialect via a provided callable.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastmcp import Context, FastMCP
from pydantic import Field

from .models import (
    Dialect,
    SqlAutoTranspileRequest,
    SqlAutoTranspileResult,
    SqlErrorAssistRequest,
    SqlErrorAssistResult,
    SqlMetadataRequest,
    SqlMetadataResult,
    SqlOptimizeRequest,
    SqlOptimizeResult,
    SqlTranspileRequest,
    SqlTranspileResult,
    SqlValidationRequest,
    SqlValidationResult,
)
from .service import SqlglotService


def register_sqlglot_tools(
    mcp: FastMCP,
    service: SqlglotService,
    dialect_provider: Callable[[], Dialect],
) -> None:
    """Register sqlglot MCP tools on the given FastMCP instance.

    Args:
        mcp: The FastMCP server instance.
        service: SqlglotService instance that performs the work.
        dialect_provider: Callable returning the database dialect to use.
    """

    @mcp.tool
    async def sql_validate(
        _ctx: Context,
        sql: Annotated[str, Field(description="SQL string to validate")],
    ) -> SqlValidationResult:  # pyright: ignore[reportUnusedFunction]
        """Validate SQL syntax for the current database dialect.

        Designed for pre-execution checks to ensure an LLM's SQL parses
        for the active database. Returns pretty-printed SQL when valid.
        """
        dialect = dialect_provider()
        req = SqlValidationRequest(sql=sql, dialect=dialect)
        return service.validate(req)

    @mcp.tool
    async def sql_transpile_to_database(
        _ctx: Context,
        sql: Annotated[str, Field(description="SQL to transpile")],
        source_dialect: Annotated[Dialect, Field(description="Source dialect")],
    ) -> SqlTranspileResult:  # pyright: ignore[reportUnusedFunction]
        """Transpile SQL from a given source dialect into the active database dialect."""
        target = dialect_provider()
        req = SqlTranspileRequest(sql=sql, source_dialect=source_dialect, target_dialect=target)
        return service.transpile(req)

    @mcp.tool
    async def sql_optimize_for_database(
        _ctx: Context,
        sql: Annotated[str, Field(description="SQL to optimize")],
        schema_map: Annotated[
            dict[str, dict[str, str]] | None,
            Field(description="Optional schema map: table -> column -> type"),
        ] = None,
    ) -> SqlOptimizeResult:  # pyright: ignore[reportUnusedFunction]
        """Optimize and normalize SQL for the active database dialect.

        Provide an optional lightweight schema map (table -> column -> type)
        to enable more effective sqlglot optimizations.
        """
        dialect = dialect_provider()
        req = SqlOptimizeRequest(sql=sql, dialect=dialect, schema_map=schema_map)
        return service.optimize(req)

    @mcp.tool
    async def sql_extract_metadata(
        _ctx: Context,
        sql: Annotated[str, Field(description="SQL to analyze")],
    ) -> SqlMetadataResult:  # pyright: ignore[reportUnusedFunction]
        """Extract structural metadata (tables, columns, joins) for the active database dialect."""
        dialect = dialect_provider()
        req = SqlMetadataRequest(sql=sql, dialect=dialect)
        return service.metadata(req)

    @mcp.tool
    async def sql_assist_from_error(
        _ctx: Context,
        sql: Annotated[str, Field(description="The SQL that failed at execution time")],
        error_message: Annotated[
            str, Field(description="The database error text returned by the server")
        ],
    ) -> SqlErrorAssistResult:  # pyright: ignore[reportUnusedFunction]
        """Suggest fixes based on a database execution error.

        Accepts the failing SQL and the error text from the database server
        and returns likely causes plus concrete fix ideas (e.g., dialect-specific
        replacements like LIMIT vs TOP). This is a post-execution helper.
        """
        dialect = dialect_provider()
        req = SqlErrorAssistRequest(sql=sql, error_message=error_message, dialect=dialect)
        return service.assist_error(req)

    # Hint to static analyzers that nested functions are intentionally used
    _ = (
        sql_validate,
        sql_transpile_to_database,
        sql_optimize_for_database,
        sql_extract_metadata,
        sql_assist_from_error,
    )

    @mcp.tool
    async def sql_auto_transpile_for_database(
        _ctx: Context,
        sql: Annotated[str, Field(description="SQL to analyze and possibly transpile")],
    ) -> SqlAutoTranspileResult:  # pyright: ignore[reportUnusedFunction]
        """Auto-detect source dialect and transpile to the active database dialect."""
        dialect = dialect_provider()
        req = SqlAutoTranspileRequest(sql=sql, target_dialect=dialect)
        return service.auto_transpile_for_database(req)

    # Keep analyzers aware this nested function is intentionally used
    _ = (sql_auto_transpile_for_database,)
