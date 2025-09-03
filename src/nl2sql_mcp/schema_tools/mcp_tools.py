"""MCP tool registration for schema_tools (schema/query) features.

Matches the registration style used by sqlglot tools: exposes a
`register_intelligence_tools` function that attaches tools to a FastMCP
instance while delegating actual logic to services obtained via
`SchemaServiceManager`.
"""

from __future__ import annotations

from typing import Literal

from fastmcp import Context, FastMCP
from fastmcp.utilities.logging import get_logger

from nl2sql_mcp.intelligence.constants import RetrievalApproach
from nl2sql_mcp.models import (
    ColumnSearchHit,
    DatabaseSummary,
    InitStatus,
    QuerySchemaResult,
    SubjectAreaItem,
    TableInfo,
    TableSearchHit,
)
from nl2sql_mcp.services.schema_service_manager import SchemaServiceManager

_logger = get_logger(__name__)
MAX_QUERY_DISPLAY = 100


def register_intelligence_tools(mcp: FastMCP, manager: SchemaServiceManager | None = None) -> None:
    """Register intelligence MCP tools on the given FastMCP instance.

    Args:
        mcp: The FastMCP server to attach tools to.
        manager: Optional explicit `SchemaServiceManager`. If not provided,
            the singleton instance is used.
    """

    mgr = manager or SchemaServiceManager.get_instance()

    @mcp.tool
    async def analyze_query_schema(  # pyright: ignore[reportUnusedFunction]  # noqa: PLR0913
        ctx: Context,
        query: str,
        max_tables: int = 5,
        *,
        approach: Literal["combo", "lexical", "emb_table", "emb_column"] = "combo",
        alpha: float = 0.7,
        detail_level: Literal["minimal", "standard", "full"] = "standard",
        include_samples: bool = False,
        max_sample_values: int = 3,
        max_columns_per_table: int = 20,
        join_limit: int = 8,
    ) -> QuerySchemaResult:
        """Find relevant tables and provide clear schema information for a query."""

        query_display = query[:MAX_QUERY_DISPLAY] + (
            "..." if len(query) > MAX_QUERY_DISPLAY else ""
        )
        _logger.info("Analyzing query schema for: %s", query_display)
        try:
            schema_service = await mgr.get_schema_service()
        except (RuntimeError, ValueError) as exc:
            await ctx.error(f"Schema service not ready: {exc}")
            raise

        approach_enum = {
            "combo": RetrievalApproach.COMBINED,
            "lexical": RetrievalApproach.LEXICAL,
            "emb_table": RetrievalApproach.EMBEDDING_TABLE,
            "emb_column": RetrievalApproach.EMBEDDING_COLUMN,
        }[approach]

        result = schema_service.analyze_query_schema(
            query,
            max_tables,
            approach=approach_enum,
            alpha=alpha,
            detail_level=detail_level,
            include_samples=include_samples,
            max_sample_values=max_sample_values,
            max_columns_per_table=max_columns_per_table,
            join_limit=join_limit,
        )
        _logger.info(
            "Analyzed query schema; found %d relevant tables", len(result.relevant_tables)
        )
        return result

    @mcp.tool
    async def get_database_overview(  # pyright: ignore[reportUnusedFunction]
        ctx: Context,
        *,
        include_subject_areas: bool = False,
        area_limit: int = 8,
    ) -> DatabaseSummary:
        """Get high-level database overview with business context."""
        _logger.info("Retrieving database overview")
        try:
            schema_service = await mgr.get_schema_service()
        except (RuntimeError, ValueError) as exc:
            await ctx.error(f"Schema service not ready: {exc}")
            raise

        result = schema_service.get_database_overview(
            include_subject_areas=include_subject_areas,
            area_limit=area_limit,
        )
        _logger.info("Retrieved database overview with %d total tables", result.total_tables)
        return result

    @mcp.tool
    async def get_table_info(  # pyright: ignore[reportUnusedFunction]
        ctx: Context,
        table_key: str,
        *,
        include_samples: bool = True,
        column_role_filter: list[Literal["metric", "date", "key", "category", "text"]]
        | None = None,
        max_sample_values: int = 5,
        relationship_limit: int | None = None,
    ) -> TableInfo:
        """Get detailed table information for SQL development."""
        _logger.info("Retrieving table information for: %s", table_key)
        try:
            schema_service = await mgr.get_schema_service()
        except (RuntimeError, ValueError) as exc:
            await ctx.error(f"Schema service not ready: {exc}")
            raise

        try:
            result: TableInfo = schema_service.get_table_information(
                table_key,
                include_samples=include_samples,
                column_role_filter=column_role_filter,  # type: ignore[arg-type]
                max_sample_values=max_sample_values,
                relationship_limit=relationship_limit,
            )
        except KeyError as exc:
            await ctx.error(f"Table not found: {exc}")
            raise

        _logger.info(
            "Retrieved table information for %s (%d columns)", table_key, len(result.columns)
        )
        return result

    @mcp.tool
    async def find_tables(  # pyright: ignore[reportUnusedFunction]
        ctx: Context,
        query: str,
        limit: int = 10,
        *,
        approach: Literal["combo", "lexical", "emb_table", "emb_column"] = "combo",
        alpha: float = 0.7,
    ) -> list[TableSearchHit]:
        """Find relevant tables quickly by intent/keywords."""
        preview = query[:MAX_QUERY_DISPLAY] + ("..." if len(query) > MAX_QUERY_DISPLAY else "")
        _logger.info("Finding tables for query: %s", preview)
        try:
            schema_service = await mgr.get_schema_service()
        except (RuntimeError, ValueError) as exc:
            await ctx.error(f"Schema service not ready: {exc}")
            raise

        approach_enum = {
            "combo": RetrievalApproach.COMBINED,
            "lexical": RetrievalApproach.LEXICAL,
            "emb_table": RetrievalApproach.EMBEDDING_TABLE,
            "emb_column": RetrievalApproach.EMBEDDING_COLUMN,
        }[approach]
        hits = schema_service.find_tables(query, limit, approach=approach_enum, alpha=alpha)
        _logger.info("Found %d table hits", len(hits))
        return hits

    @mcp.tool
    async def find_columns(  # pyright: ignore[reportUnusedFunction]
        ctx: Context, keyword: str, limit: int = 25, by_table: str | None = None
    ) -> list[ColumnSearchHit]:
        """Locate columns for SELECT/WHERE scaffolding."""
        _logger.info("Finding columns for keyword: %s", keyword)
        try:
            schema_service = await mgr.get_schema_service()
        except (RuntimeError, ValueError) as exc:
            await ctx.error(f"Schema service not ready: {exc}")
            raise

        hits = schema_service.find_columns(keyword, limit, by_table=by_table)
        _logger.info("Found %d column hits", len(hits))
        return hits

    @mcp.tool
    async def get_init_status(_ctx: Context) -> InitStatus:  # pyright: ignore[reportUnusedFunction]
        """Get initialization status for schema service."""
        state = mgr.status()
        return InitStatus(
            phase=state.phase.name,
            attempts=state.attempts,
            started_at=state.started_at,
            completed_at=state.completed_at,
            error_message=state.error_message,
        )

    @mcp.tool
    async def get_subject_areas(  # pyright: ignore[reportUnusedFunction]
        ctx: Context, limit: int = 12
    ) -> list[SubjectAreaItem]:
        """List subject areas detected in the database."""
        _logger.info("Retrieving subject areas (limit=%d)", limit)
        try:
            schema_service = await mgr.get_schema_service()
        except (RuntimeError, ValueError) as exc:
            await ctx.error(f"Schema service not ready: {exc}")
            raise

        explorer = schema_service.explorer
        if not explorer.card:
            msg = "Schema card not available"
            await ctx.error(msg)
            raise RuntimeError(msg)

        card = explorer.card
        sorted_ids = sorted(
            card.subject_areas.keys(),
            key=lambda aid: len(card.subject_areas[aid].tables),
            reverse=True,
        )
        items: list[SubjectAreaItem] = []
        for aid in sorted_ids[: max(1, limit)]:
            data = card.subject_areas[aid]
            items.append(
                SubjectAreaItem(id=aid, name=data.name, tables=data.tables, summary=data.summary)
            )
        _logger.info("Returned %d subject areas", len(items))
        return items

    # Hint to static analyzers that nested functions are intentionally used
    _ = (
        analyze_query_schema,
        get_database_overview,
        get_table_info,
        find_tables,
        find_columns,
        get_init_status,
        get_subject_areas,
    )
