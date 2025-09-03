"""MCP tool registration for schema_tools (schema/query) features.

Matches the registration style used by sqlglot tools: exposes a
`register_intelligence_tools` function that attaches tools to a FastMCP
instance while delegating actual logic to services obtained via
`SchemaServiceManager`.
"""

from __future__ import annotations

import os

from fastmcp import Context, FastMCP
from fastmcp.utilities.logging import get_logger

from nl2sql_mcp.models import (
    ColumnSearchHit,
    DatabaseOverviewRequest,
    DatabaseSummary,
    FindColumnsRequest,
    FindTablesRequest,
    InitStatus,
    PlanQueryRequest,
    QuerySchemaResult,
    SubjectAreaItem,
    TableInfo,
    TableInfoRequest,
    TableSearchHit,
)
from nl2sql_mcp.schema_tools.constants import RetrievalApproach
from nl2sql_mcp.services.schema_service_manager import SchemaServiceManager

_logger = get_logger(__name__)
MAX_QUERY_DISPLAY = 100


def register_intelligence_tools(mcp: FastMCP, manager: SchemaServiceManager | None = None) -> None:
    """Register intent-first database intelligence tools.

    Provides planning and orientation tools designed for LLM agents to
    understand a database and produce correct SQL with minimal roundtrips.
    """

    mgr = manager or SchemaServiceManager.get_instance()

    @mcp.tool
    async def plan_query_for_intent(  # pyright: ignore[reportUnusedFunction]
        ctx: Context, req: PlanQueryRequest
    ) -> QuerySchemaResult:
        """Plan a SQL solution for a natural-language request.

        Returns minimal schema context, a join plan, and a draft query so an LLM
        can proceed directly to execution or ask for clarifications.
        """

        preview = req.request[:MAX_QUERY_DISPLAY] + (
            "..." if len(req.request) > MAX_QUERY_DISPLAY else ""
        )
        _logger.info("Planning query for intent: %s", preview)
        try:
            schema_service = await mgr.get_schema_service()
        except (RuntimeError, ValueError) as exc:
            await ctx.error(f"Schema service not ready: {exc}")
            raise

        # Internal defaults; map optional budget to internal caps
        budget = req.budget or {}
        max_tables = int(budget.get("tables", 5))
        max_columns_per_table = int(budget.get("columns_per_table", 20))
        max_sample_values = int(budget.get("sample_values", 3))
        join_limit = 8

        # Acknowledge constraints for future rule application and telemetry
        if req.constraints:
            _logger.info("Constraints keys provided: %s", ",".join(sorted(req.constraints.keys())))

        result = schema_service.analyze_query_schema(
            req.request,
            max_tables,
            approach=RetrievalApproach.COMBINED,
            alpha=0.7,
            detail_level=req.detail_level,
            include_samples=False,
            max_sample_values=max_sample_values,
            max_columns_per_table=max_columns_per_table,
            join_limit=join_limit,
        )
        _logger.info("Planned query; selected %d tables", len(result.relevant_tables))
        return result

    @mcp.tool
    async def get_database_overview(  # pyright: ignore[reportUnusedFunction]
        ctx: Context, req: DatabaseOverviewRequest
    ) -> DatabaseSummary:
        """Summarize schemas and key areas to orient query planning."""
        _logger.info("Retrieving database overview")
        try:
            schema_service = await mgr.get_schema_service()
        except (RuntimeError, ValueError) as exc:
            await ctx.error(f"Schema service not ready: {exc}")
            raise

        result = schema_service.get_database_overview(
            include_subject_areas=req.include_subject_areas, area_limit=req.area_limit
        )
        _logger.info("Retrieved database overview with %d total tables", result.total_tables)
        return result

    @mcp.tool
    async def get_table_info(  # pyright: ignore[reportUnusedFunction]
        ctx: Context, req: TableInfoRequest
    ) -> TableInfo:
        """Explain a table's purpose, columns, relationships, and representative values."""
        _logger.info("Retrieving table information for: %s", req.table_key)
        try:
            schema_service = await mgr.get_schema_service()
        except (RuntimeError, ValueError) as exc:
            await ctx.error(f"Schema service not ready: {exc}")
            raise

        try:
            result: TableInfo = schema_service.get_table_information(
                req.table_key,
                include_samples=req.include_samples,
                column_role_filter=req.column_role_filter,  # type: ignore[arg-type]
                max_sample_values=req.max_sample_values,
                relationship_limit=req.relationship_limit,
            )
        except KeyError as exc:
            await ctx.error(f"Table not found: {exc}")
            raise

        _logger.info(
            "Retrieved table information for %s (%d columns)", req.table_key, len(result.columns)
        )
        return result

    # Optionally register debug discovery tools
    debug_flag = os.getenv("NL2SQL_MCP_DEBUG_TOOLS", "").lower() in {"1", "true", "yes"}
    if debug_flag:

        @mcp.tool
        async def find_tables(  # pyright: ignore[reportUnusedFunction]
            ctx: Context, req: FindTablesRequest
        ) -> list[TableSearchHit]:
            """Find relevant tables quickly by intent/keywords (debug)."""
            preview = req.query[:MAX_QUERY_DISPLAY] + (
                "..." if len(req.query) > MAX_QUERY_DISPLAY else ""
            )
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
            }[req.approach]
            hits = schema_service.find_tables(
                req.query, req.limit, approach=approach_enum, alpha=req.alpha
            )
            _logger.info("Found %d table hits", len(hits))
            return hits

        @mcp.tool
        async def find_columns(  # pyright: ignore[reportUnusedFunction]
            ctx: Context, req: FindColumnsRequest
        ) -> list[ColumnSearchHit]:
            """Locate columns for SELECT/WHERE scaffolding (debug)."""
            _logger.info("Finding columns for keyword: %s", req.keyword)
            try:
                schema_service = await mgr.get_schema_service()
            except (RuntimeError, ValueError) as exc:
                await ctx.error(f"Schema service not ready: {exc}")
                raise

            hits = schema_service.find_columns(req.keyword, req.limit, by_table=req.by_table)
            _logger.info("Found %d column hits", len(hits))
            return hits

    @mcp.tool
    async def get_init_status(_ctx: Context) -> InitStatus:  # pyright: ignore[reportUnusedFunction]
        """Get initialization status with descriptive progression for LLMs/UIs."""
        state = mgr.status()
        deep = mgr.enrichment_status()

        # Build a concise, LLM-friendly description
        phase = state.phase.name
        if phase in {"IDLE", "STARTING"}:
            desc = "Starting: creating engine and launching background reflection."
        elif phase == "RUNNING":
            desc = "Initializing: reflecting schemas, sampling tables, and building initial graph."
        elif phase == "READY":
            if deep.get("in_progress"):
                desc = "Ready; background enrichment in progress (relationships, communities)."
            elif deep.get("completed_at"):
                desc = "Ready; enrichment complete (relationships, communities)."
            else:
                desc = "Ready for queries."
        elif phase == "FAILED":
            desc = "Initialization failed; see error_message."
        else:
            desc = "Stopped."

        return InitStatus(
            phase=phase,
            attempts=state.attempts,
            started_at=state.started_at,
            completed_at=state.completed_at,
            error_message=state.error_message,
            description=desc,
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
    if debug_flag:
        _ = (
            plan_query_for_intent,
            get_database_overview,
            get_table_info,
            get_init_status,
            get_subject_areas,
        )
    else:
        _ = (
            plan_query_for_intent,
            get_database_overview,
            get_table_info,
            get_init_status,
            get_subject_areas,
        )
