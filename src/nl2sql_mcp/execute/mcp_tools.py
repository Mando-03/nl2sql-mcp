"""MCP tool registration for direct SQL execution (execute_query).

Provides a single tool `execute_query(sql: str)` that validates and transpiles per active dialect,
executes SELECT-only queries with enforced row/cell truncation, and returns a typed result payload
including guidance fields (assist_notes, validation_notes, next_action).
"""

from __future__ import annotations

from typing import Annotated

from fastmcp import Context, FastMCP
from fastmcp.utilities.logging import get_logger
from pydantic import Field

from nl2sql_mcp.execute.models import ExecuteQueryResult
from nl2sql_mcp.execute.runner import ExecutionLimits, run_execute_flow
from nl2sql_mcp.schema_tools.mcp_tools import MAX_QUERY_DISPLAY
from nl2sql_mcp.services.config_service import ConfigService
from nl2sql_mcp.services.schema_service_manager import SchemaServiceManager
from nl2sql_mcp.sqlglot_tools import SqlglotService, map_sqlalchemy_to_sqlglot

_logger = get_logger(__name__)


def register_execute_query_tool(
    mcp: FastMCP, *, sqlglot_service: SqlglotService | None = None
) -> None:
    """Register a safe SQL execution tool.

    Executes SELECT-only statements with automatic dialect validation/transpilation,
    enforces row/cell truncation, and returns typed results with next_action, assist_notes,
    and validation_notes to guide refinement.
    """

    mgr = SchemaServiceManager.get_instance()
    glot = sqlglot_service or SqlglotService()

    @mcp.tool
    async def execute_query(
        ctx: Context,
        sql: Annotated[
            str,
            Field(
                description=(
                    "SELECT-only SQL to execute. Validates and transpiles per active dialect; "
                    "enforces row/cell truncation. On error, results include assist_notes, "
                    "validation_notes, and next_action."
                )
            ),
        ],
    ) -> ExecuteQueryResult:  # pyright: ignore[reportUnusedFunction]
        """Validate and transpile SELECT-only SQL, execute with row/cell truncation, and return typed results.

        On error, use assist_notes, validation_notes, and next_action to refine; if truncated or
        rows reach the limit, paginate or aggregate as appropriate.
        """

        preview = sql[:MAX_QUERY_DISPLAY] + ("..." if len(sql) > MAX_QUERY_DISPLAY else "")
        _logger.info("execute_query: %s", preview)

        # Resolve services
        try:
            schema_service = await mgr.get_schema_service()
        except (RuntimeError, ValueError) as exc:
            await ctx.error(f"Schema service not ready: {exc}")
            raise

        # Result budgets from config
        row_limit = ConfigService.result_row_limit()
        max_cell_chars = ConfigService.result_max_cell_chars()

        # Active dialect resolution
        sa_name = mgr.current_sqlalchemy_dialect_name() or "sql"
        dialect = map_sqlalchemy_to_sqlglot(sa_name)

        return run_execute_flow(
            sql=sql,
            engine=schema_service.engine,
            glot=glot,
            active_dialect=dialect,
            limits=ExecutionLimits(
                row_limit=row_limit,
                max_cell_chars=max_cell_chars,
            ),
        )

    _ = execute_query
