"""MCP tool registration for schema_tools (schema/query) features.

Matches the registration style used by sqlglot tools: exposes a
`register_intelligence_tools` function that attaches tools to a FastMCP
instance while delegating actual logic to services obtained via
`SchemaServiceManager`.
"""

from __future__ import annotations

import os
from typing import Annotated, Literal

from fastmcp import Context, FastMCP
from fastmcp.utilities.logging import get_logger
from pydantic import Field

from nl2sql_mcp.models import (
    ColumnSearchHit,
    DatabaseSummary,
    InitStatus,
    QuerySchemaResult,
    SubjectAreaItem,
    TableInfo,
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
        ctx: Context,
        request: Annotated[
            str,
            Field(
                description=(
                    "Before calling, rewrite the user's question into a concise request optimized "
                    "for schema vector searching: focus on the analytical intent and key entities "
                    "or metrics, omitting superfluous details or context not beneficial for "
                    "matching tables, columns, or values."
                )
            ),
        ],
        *,
        full_detail: Annotated[
            bool,
            Field(
                description=(
                    "Default is false. When true, return an expanded plan: more relevant tables, "
                    "more columns per table, a longer join plan with alternatives, broader "
                    "group_by and filter candidates, and richer clarifications. When false, "
                    "return a compact plan focused on top tables and a minimal join plan. Raw "
                    "sample values are not included; use get_table_info for samples."
                )
            ),
        ] = False,
        constraints: Annotated[
            dict[str, str | int | float | bool] | None,
            Field(
                description=(
                    "Pass user-supplied constraints exactly (e.g., time_range, region, metric). "
                    "Do not invent or infer values; ask for clarification if uncertain."
                )
            ),
        ] = None,
        budget: Annotated[
            dict[str, int] | None,
            Field(
                description=(
                    "Optional response-size caps. Keys: tables, columns_per_table, sample_values. "
                    "Recommended defaults: full_detail=false and "
                    "budget={tables:5, columns_per_table:20, sample_values:0}."
                )
            ),
        ] = None,
    ) -> QuerySchemaResult:
        """Plan a SQL solution for a natural-language request.

        Produces relevant tables, join plan, filter candidates, selected columns, draft SQL,
        clarifications, assumptions, confidence, and next action. If clarifications exist or
        confidence < 0.6, surface those questions to the user before proceeding to execution.
        """

        preview = request[:MAX_QUERY_DISPLAY] + ("..." if len(request) > MAX_QUERY_DISPLAY else "")
        _logger.info("Planning query for intent: %s", preview)
        try:
            schema_service = await mgr.get_schema_service()
        except (RuntimeError, ValueError) as exc:
            await ctx.error(f"Schema service not ready: {exc}")
            raise

        # Internal defaults; map optional budget to internal caps
        budget = budget or {}
        max_tables = int(budget.get("tables", 5))
        max_columns_per_table = int(budget.get("columns_per_table", 20))
        max_sample_values = int(budget.get("sample_values", 3))
        join_limit = 8

        # Acknowledge constraints for future rule application and telemetry
        if constraints:
            _logger.info("Constraints keys provided: %s", ",".join(sorted(constraints.keys())))

        result = schema_service.analyze_query_schema(
            request,
            max_tables,
            approach=RetrievalApproach.COMBINED,
            alpha=0.7,
            detail_level=("full" if full_detail else "standard"),
            include_samples=False,
            max_sample_values=max_sample_values,
            max_columns_per_table=max_columns_per_table,
            join_limit=join_limit,
        )
        _logger.info("Planned query; selected %d tables", len(result.relevant_tables))
        return result

    @mcp.tool
    async def get_database_overview(  # pyright: ignore[reportUnusedFunction]
        ctx: Context,
        *,
        include_subject_areas: Annotated[
            bool,
            Field(description="Include structured subject area data when true", default=False),
        ] = False,
        area_limit: Annotated[
            int, Field(ge=1, description="Maximum number of subject areas to include", default=8)
        ] = 8,
    ) -> DatabaseSummary:
        """Provides high-level critical information (database dialect, schemas, subject areas,
        important tables, and patterns) to help orient query planning."""
        _logger.info("Retrieving database overview")
        try:
            schema_service = await mgr.get_schema_service()
        except (RuntimeError, ValueError) as exc:
            await ctx.error(f"Schema service not ready: {exc}")
            raise

        result = schema_service.get_database_overview(
            include_subject_areas=include_subject_areas, area_limit=area_limit
        )
        _logger.info("Retrieved database overview with %d total tables", result.total_tables)
        return result

    @mcp.tool
    async def get_table_info(  # pyright: ignore[reportUnusedFunction]
        ctx: Context,
        *,
        table_key: Annotated[str, Field(description="Fully qualified table name 'schema.table'")],
        include_samples: Annotated[
            bool,
            Field(
                description=(
                    "Include representative sample values for columns (useful for WHERE filters); "
                    "limited by max_sample_values."
                ),
                default=True,
            ),
        ] = True,
        column_role_filter: Annotated[
            list[Literal["metric", "date", "key", "category", "text"]] | None,
            Field(
                description=(
                    "If provided, only return columns with these business roles. Prefer "
                    "['key','date','metric','category'] to keep results focused and payload small."
                )
            ),
        ] = None,
        max_sample_values: Annotated[
            int,
            Field(
                ge=0,
                description="Maximum sample values per column when include_samples is true",
                default=5,
            ),
        ] = 5,
        relationship_limit: Annotated[
            int | None,
            Field(ge=0, description="Limit the number of relationships returned (PK/FK hints)"),
        ] = None,
    ) -> TableInfo:
        """Explain a table's purpose, columns, relationships, and representative values.

        Use on the top 1-2 tables to confirm columns, datatypes, PK/FK joins, relationship
        hints, and sample values for WHERE clauses.
        """
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

    # Optionally register debug discovery tools
    debug_flag = os.getenv("NL2SQL_MCP_DEBUG_TOOLS", "").lower() in {"1", "true", "yes"}
    if debug_flag:

        @mcp.tool
        async def find_tables(  # pyright: ignore[reportUnusedFunction]
            ctx: Context,
            query: Annotated[
                str, Field(description="Concise intent/keywords optimized for schema search")
            ],
            limit: Annotated[
                int, Field(default=10, ge=1, le=50, description="Maximum number of hits")
            ] = 10,
            approach: Annotated[
                Literal["combo", "lexical", "emb_table", "emb_column"],
                Field(description="Retrieval strategy"),
            ] = "combo",
            alpha: Annotated[
                float, Field(default=0.7, ge=0.0, le=1.0, description="Blend weight for combo")
            ] = 0.7,
        ) -> list[TableSearchHit]:
            """Find relevant tables quickly by intent/keywords (debug-only)."""
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
            ctx: Context,
            keyword: Annotated[
                str, Field(description="Keyword to match column names and descriptions")
            ],
            limit: Annotated[
                int, Field(default=25, ge=1, le=200, description="Maximum number of hits")
            ] = 25,
            by_table: Annotated[
                str | None, Field(description="Restrict search to a specific 'schema.table'")
            ] = None,
        ) -> list[ColumnSearchHit]:
            """Locate columns for SELECT/WHERE scaffolding (debug-only)."""
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
        """Initialization status for first-step readiness checks.

        Use this as your first action. If phase != READY, relay the description to the user and
        instruct them to retry later.
        """
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
        ctx: Context,
        *,
        limit: Annotated[
            int, Field(ge=1, default=12, description="Maximum number of areas to return")
        ] = 12,
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
