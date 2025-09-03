"""MCP tool registration for the ask_database agent.

Exposes a single tool `ask_database(question: str)` that plans, generates,
validates, executes, and returns a concise, structured response.
"""

from __future__ import annotations

from fastmcp import Context, FastMCP
from fastmcp.utilities.logging import get_logger

from nl2sql_mcp.agent.agent import run_ask_flow
from nl2sql_mcp.agent.models import AgentDeps, AskDatabaseResult
from nl2sql_mcp.schema_tools.mcp_tools import MAX_QUERY_DISPLAY
from nl2sql_mcp.services.config_service import ConfigService
from nl2sql_mcp.services.schema_service_manager import SchemaServiceManager
from nl2sql_mcp.sqlglot_tools import SqlglotService, map_sqlalchemy_to_sqlglot

_logger = get_logger(__name__)


def register_ask_database_tool(
    mcp: FastMCP, *, sqlglot_service: SqlglotService | None = None
) -> None:
    """Register the `ask_database` MCP tool on the given server instance."""

    mgr = SchemaServiceManager.get_instance()
    glot = sqlglot_service or SqlglotService()

    @mcp.tool
    async def ask_database(ctx: Context, question: str) -> AskDatabaseResult:  # pyright: ignore[reportUnusedFunction]
        """Answer a natural language database question with structured results.

        This tool:
        - Analyzes the schema to focus context
        - Uses an LLM to propose a single, safe SELECT
        - Validates/normalizes against the active dialect
        - Executes the query with limits and truncation
        - Returns concise results and next-step recommendations
        """

        preview = question[:MAX_QUERY_DISPLAY] + (
            "..." if len(question) > MAX_QUERY_DISPLAY else ""
        )
        _logger.info("ask_database: %s", preview)

        # Resolve services
        try:
            schema_service = await mgr.get_schema_service()
        except (RuntimeError, ValueError) as exc:
            await ctx.error(f"Schema service not ready: {exc}")
            raise

        # LLM & result budgets from config
        llm = ConfigService.get_llm_config()
        row_limit = ConfigService.result_row_limit()
        max_cell_chars = ConfigService.result_max_cell_chars()
        max_payload_bytes = ConfigService.result_max_payload_bytes()

        # Active dialect resolution
        sa_name = mgr.current_sqlalchemy_dialect_name() or "sql"
        dialect = map_sqlalchemy_to_sqlglot(sa_name)

        # Plan schema
        schema = schema_service.analyze_query_schema(
            question,
            max_tables=5,
            include_samples=True,
            max_sample_values=0,
            detail_level="standard",
            join_limit=8,
        )

        deps = AgentDeps(
            active_dialect=dialect,
            row_limit=row_limit,
            max_cell_chars=max_cell_chars,
            max_payload_bytes=max_payload_bytes,
        )

        # Execute end-to-end flow
        return run_ask_flow(
            question=question,
            schema=schema,
            engine=schema_service.engine,
            glot=glot,
            deps=deps,
            llm=llm,
        )

    _ = ask_database
